import csv
import io
import json

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from custom_account.models import (
    BiometricCredential,
    Profile,
)


class Command(BaseCommand):
    help = "Nạp vector khuôn mặt từ file JSON bằng cơ chế COPY siêu tốc của PostgreSQL"

    def handle(self, *args, **options):
        json_file_path = "tools/management/data/export/face_vectors_export.json"

        self.stdout.write("📂 Đang đọc file JSON...")
        with open(json_file_path, encoding="utf-8") as f:
            data = json.load(f)

        if not data:
            self.stdout.write(self.style.WARNING("File JSON rỗng!"))
            return

        self.stdout.write("🔗 Đang map Identity Code sang Biometric ID...")
        # 1. Lấy mapping identity_code -> user_id
        identity_codes = [item["identity_code"] for item in data]
        profiles = Profile.objects.filter(identity_code__in=identity_codes).values(
            "identity_code", "user_id"
        )
        profile_map = {p["identity_code"]: p["user_id"] for p in profiles}

        # 2. Đảm bảo BiometricCredential tồn tại
        user_ids = list(profile_map.values())
        existing_bios = BiometricCredential.objects.filter(user_id__in=user_ids).values(
            "user_id", "id"
        )
        bio_map = {b["user_id"]: b["id"] for b in existing_bios}

        # Tạo BiometricCredential cho những user chưa có (dùng ORM đoạn này cho lẹ vì số lượng ít)
        missing_uids = set(user_ids) - set(bio_map.keys())
        if missing_uids:
            BiometricCredential.objects.bulk_create(
                [BiometricCredential(user_id=uid) for uid in missing_uids]
            )
            new_bios = BiometricCredential.objects.filter(
                user_id__in=missing_uids
            ).values("user_id", "id")
            for b in new_bios:
                bio_map[b["user_id"]] = b["id"]

        # 3. Chuẩn bị dữ liệu CSV trên RAM (In-memory) để bơm qua COPY
        self.stdout.write(
            "🚀 Đang chuyển đổi dữ liệu sang luồng I/O (Memory Buffer)..."
        )
        csv_buffer = io.StringIO()
        writer = csv.writer(
            csv_buffer, delimiter="\t"
        )  # Dùng Tab làm phân cách cho an toàn

        valid_count = 0
        for item in data:
            code = item["identity_code"]
            if code not in profile_map:
                continue

            user_id = profile_map[code]
            bio_id = bio_map[user_id]

            # Ghi từng dòng vào buffer (Thứ tự phải khớp với bảng tạm ở dưới)
            # vector phải được dump thành chuỗi JSON để PostgreSQL hiểu đó là kiểu JSONB
            writer.writerow(
                [
                    bio_id,
                    item["model_name"],
                    item["template_type"],
                    json.dumps(item["vector"]),
                    item["is_active"],
                    item["sample_count"],
                    (
                        item["intra_sim_score"]
                        if item["intra_sim_score"] is not None
                        else "\\N"
                    ),  # PostgreSQL hiểu \N là NULL
                    item["soft_margin"] if item["soft_margin"] is not None else "\\N",
                    item["source"],
                ]
            )
            valid_count += 1

        # Đưa con trỏ buffer về đầu file để chuẩn bị đọc
        csv_buffer.seek(0)

        # ====================================================================
        # 4. KÍCH HOẠT SỨC MẠNH RAW POSTGRESQL (TEMP TABLE + COPY + UPSERT)
        # ====================================================================
        self.stdout.write(
            f"⚡ Đang bơm {valid_count} bản ghi vào PostgreSQL qua cổng COPY..."
        )

        # Lưu ý: Thay 'appname_facetemplate' bằng tên bảng thật của bạn trong DB (thường là tên_app_tên_model)
        # Ví dụ app của bạn tên là 'core', thì bảng là 'core_facetemplate'
        table_name = "custom_account_facetemplate"

        with transaction.atomic():
            with connection.cursor() as cursor:
                # BƯỚC A: Tạo một bảng tạm (UNLOGGED để bỏ qua cơ chế ghi log của DB -> Siêu nhanh)
                cursor.execute("""
                    CREATE TEMP TABLE tmp_face (
                        biometric_id integer,
                        model_name varchar(50),
                        template_type varchar(30),
                        vector jsonb,
                        is_active boolean,
                        sample_count integer,
                        intra_sim_score double precision,
                        soft_margin double precision,
                        source varchar(50)
                    ) ON COMMIT DROP;
                """)

                # BƯỚC B: Dùng lệnh COPY nạp thẳng từ RAM vào bảng tạm
                # copy_expert cho phép truyền thẳng lệnh raw COPY của Postgres
                cursor.copy_expert(
                    "COPY tmp_face FROM STDIN WITH (FORMAT CSV, DELIMITER '\t', NULL '\\N')",
                    csv_buffer,
                )

                # BƯỚC C: Upsert từ bảng tạm sang bảng thật (Sử dụng ON CONFLICT)
                cursor.execute(f"""
                    INSERT INTO {table_name} (
                        biometric_id, model_name, template_type, vector, 
                        is_active, sample_count, intra_sim_score, soft_margin, source, created_at
                    )
                    SELECT 
                        biometric_id, model_name, template_type, vector, 
                        is_active, sample_count, intra_sim_score, soft_margin, source, NOW()
                    FROM tmp_face
                    ON CONFLICT (biometric_id, model_name, template_type)
                    DO UPDATE SET
                        vector = EXCLUDED.vector,
                        is_active = EXCLUDED.is_active,
                        sample_count = EXCLUDED.sample_count,
                        intra_sim_score = EXCLUDED.intra_sim_score,
                        soft_margin = EXCLUDED.soft_margin,
                        source = EXCLUDED.source,
                        last_used_at = NULL;
                """)

        self.stdout.write(
            self.style.SUCCESS(
                f"🏆 THÀNH CÔNG! Đã Upsert {valid_count} template vào Database với tốc độ bàn thờ!"
            )
        )
