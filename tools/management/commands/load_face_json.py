import csv
import io
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from offline_sync.models import BiometricCredential, EnrollmentSample, FaceTemplate

User = get_user_model()


class Command(BaseCommand):
    help = "Nạp vector khuôn mặt từ file JSON bằng cơ chế COPY siêu tốc của PostgreSQL"

    def handle(self, *args, **options):
        json_file_path = "tools/management/data/exports/dataset_face_vectors.json"

        self.stdout.write("📂 Đang đọc file JSON...")
        try:
            with open(json_file_path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(f"Không tìm thấy file: {json_file_path}")
            )
            return

        if not data:
            self.stdout.write(self.style.WARNING("File JSON rỗng!"))
            return

        self.stdout.write("🔗 Đang map Identity Code sang Biometric ID...")
        # 1. Lấy mapping identity_code -> user_id
        identity_codes = [item["identity_code"] for item in data]
        users = User.objects.filter(identity_code__in=identity_codes).values(
            "identity_code", "id"
        )
        user_map = {p["identity_code"]: p["id"] for p in users}
        if not user_map:
            self.stdout.write(
                self.style.ERROR(
                    "🚨 TOANG! Không tìm thấy user nào trong Database khớp với JSON! Bạn đã tạo User chưa?"
                )
            )
            return

        # 2. Đảm bảo BiometricCredential tồn tại
        user_ids = list(user_map.values())
        existing_uids = BiometricCredential.objects.filter(
            user_id__in=user_ids
        ).values_list("user_id", flat=True)
        existing_uids_set = set(existing_uids)

        # Tạo cho những user chưa có
        missing_uids = set(user_ids) - existing_uids_set
        if missing_uids:
            BiometricCredential.objects.bulk_create(
                [BiometricCredential(user_id=uid) for uid in missing_uids]
            )

        # 3. Chuẩn bị dữ liệu CSV trên RAM (In-memory) để bơm qua COPY
        self.stdout.write(
            "🚀 Đang chuyển đổi dữ liệu sang luồng I/O (Memory Buffer)..."
        )
        csv_buffer = io.StringIO()
        writer = csv.writer(
            csv_buffer, delimiter="\t"
        )  # Dùng Tab làm phân cách cho an toàn

        total_count = len(data)
        valid_count = 0
        for item in data:
            code = item["identity_code"]
            if code not in user_map:
                continue

            bio_id = user_map[code]

            def get_val(val):
                return val if val is not None else "\\N"

            # Ghi từng dòng vào buffer (Thứ tự phải khớp với bảng tạm ở dưới)
            # vector phải được dump thành chuỗi JSON để PostgreSQL hiểu đó là kiểu JSONB
            writer.writerow(
                [
                    bio_id,
                    get_val(item.get("quality_assessor")),
                    get_val(item.get("detector_model")),
                    get_val(item.get("extractor_model")),
                    item.get("vector_dimension", 0),
                    item.get("template_type", "default"),
                    json.dumps(item["vector_json"]),
                    json.dumps(item["vector_json"]),
                    get_val(item.get("image_ref")),
                    get_val(item.get("face_quality_score")),
                    item.get("is_active", True),
                    item.get("sample_count", 0),
                    get_val(item.get("intra_sim_score")),
                    get_val(item.get("soft_margin")),
                    item.get("source", "unknown"),
                    get_val(item.get("extracted_at")),
                ]
            )
            valid_count += 1

        if valid_count == 0:
            self.stdout.write(
                self.style.WARNING("Không có bản ghi nào hợp lệ để map với hệ thống.")
            )
            return

        # Đưa con trỏ buffer về đầu file để chuẩn bị đọc
        csv_buffer.seek(0)

        # ====================================================================
        # 4. KÍCH HOẠT SỨC MẠNH RAW POSTGRESQL (TEMP TABLE + COPY + UPSERT)
        # ====================================================================
        table_name = FaceTemplate._meta.db_table

        with transaction.atomic():
            with connection.cursor() as cursor:
                # BƯỚC A: Tạo một bảng tạm (UNLOGGED để bỏ qua cơ chế ghi log của DB -> Siêu nhanh)
                cursor.execute("""
                    CREATE TEMP TABLE tmp_face (
                        biometric_id uuid,
                        quality_assessor varchar(50),
                        detector_model varchar(50),
                        extractor_model varchar(50),
                        vector_dimension integer,
                        template_type varchar(30),
                        vector_json jsonb,
                        vector_text text,
                        image_ref varchar(255),
                        face_quality_score double precision,
                        is_active boolean,
                        sample_count integer,
                        intra_sim_score double precision,
                        soft_margin double precision,
                        source varchar(50),
                        extracted_at timestamp with time zone
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
                        biometric_id, quality_assessor, detector_model, extractor_model,
                        vector_dimension, template_type, vector_json, 
                        vector_128, vector_192, vector_512,
                        image_ref, face_quality_score, is_active, sample_count, 
                        intra_sim_score, soft_margin, source, created_at
                    )
                    SELECT 
                        biometric_id, quality_assessor, detector_model, extractor_model, 
                        vector_dimension, template_type, vector_json, 
                        CASE WHEN vector_dimension = 128 THEN vector_text::vector ELSE NULL END,
                        CASE WHEN vector_dimension = 192 THEN vector_text::vector ELSE NULL END,
                        CASE WHEN vector_dimension = 512 THEN vector_text::vector ELSE NULL END,
                        image_ref, face_quality_score, is_active, sample_count, intra_sim_score, soft_margin, source, COALESCE(extracted_at, NOW())
                    FROM tmp_face
                    ON CONFLICT (biometric_id, detector_model, extractor_model, template_type)
                    DO UPDATE SET
                        quality_assessor = EXCLUDED.quality_assessor,
                        vector_dimension = EXCLUDED.vector_dimension,
                        vector_json = EXCLUDED.vector_json,
                        vector_128 = EXCLUDED.vector_128,
                        vector_192 = EXCLUDED.vector_192,
                        vector_512 = EXCLUDED.vector_512,
                        image_ref = EXCLUDED.image_ref,
                        face_quality_score = EXCLUDED.face_quality_score,
                        is_active = EXCLUDED.is_active,
                        sample_count = EXCLUDED.sample_count,
                        intra_sim_score = EXCLUDED.intra_sim_score,
                        soft_margin = EXCLUDED.soft_margin,
                        source = EXCLUDED.source,
                        last_used_at = NULL;
                """)

        self.stdout.write(
            self.style.SUCCESS(
                f"🏆 THÀNH CÔNG! Đã Upsert {valid_count}/{total_count} template vào FaceTemplates"
            )
        )

        self.stdout.write("📸 Đang nạp EnrollmentSamples (Raw Data)...")

        updated_templates = FaceTemplate.objects.filter(
            biometric_id__in=user_map.values()
        ).values(
            "id", "biometric_id", "detector_model", "extractor_model", "template_type"
        )

        template_id_map = {
            (
                t["biometric_id"],
                t["detector_model"],
                t["extractor_model"],
                t["template_type"],
            ): t["id"]
            for t in updated_templates
        }

        samples_to_create = []
        template_ids_to_clear = set()

        total_raw_samples = sum(len(item.get("raw_samples", [])) for item in data)

        for item in data:
            code = item["identity_code"]
            if code not in user_map:
                continue

            bio_id = user_map[code]
            lookup_key = (
                bio_id,
                item.get("detector_model"),
                item.get("extractor_model"),
                item.get("template_type", "primary"),
            )

            template_id = template_id_map.get(lookup_key)
            if not template_id:
                continue

            template_ids_to_clear.add(template_id)

            raw_samples = item.get("raw_samples", [])
            for sample in raw_samples:
                samples_to_create.append(
                    EnrollmentSample(
                        template_id=template_id,
                        raw_image=sample["image_filename"],
                        quality_score=sample.get("quality_score"),
                        is_best_shot=sample.get("is_best_shot", False),
                        vector_json=sample.get("vector_json"),
                    )
                )

        if template_ids_to_clear:
            EnrollmentSample.objects.filter(
                template_id__in=template_ids_to_clear
            ).delete()

        if samples_to_create:
            EnrollmentSample.objects.bulk_create(samples_to_create, batch_size=1000)

        self.stdout.write(
            self.style.SUCCESS(
                f"🏆 HOÀN TẤT! Đã nạp {valid_count}/{total_count} Templates và {len(samples_to_create)}/{total_raw_samples} Raw Samples!"
            )
        )
