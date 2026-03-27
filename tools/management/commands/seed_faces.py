import json
import os

from django.core.management.base import BaseCommand

from custom_account.models import (
    BiometricCredential,
    UserModel,
)


class Command(BaseCommand):
    help = "Nạp dữ liệu khuôn mặt (Vector Embeddings) từ file JSON vào Database"

    def add_arguments(self, parser):
        # Truyền đường dẫn file JSON khi gõ lệnh
        parser.add_argument(
            "json_path",
            type=str,
            help="Đường dẫn tới file db_mobilefacenet_tflite.json",
        )

    def handle(self, *args, **kwargs):
        json_path = kwargs["json_path"]

        if not os.path.exists(json_path):
            self.stdout.write(self.style.ERROR(f"Không tìm thấy file: {json_path}"))
            return

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        success_count = 0
        fail_count = 0

        # Duyệt qua từng username và vector trong file JSON
        for username, vector_list in data.items():
            try:
                # Tìm User bằng username (App của bạn đang lấy tên thư mục làm username)
                user = UserModel.objects.get(username=username)

                # Lấy hoặc tạo BiometricCredential cho user này
                bio, created = BiometricCredential.objects.get_or_create(user=user)

                # Format lại data theo chuẩn của model (List các dict)
                formatted_embedding = [{"type": "primary", "vector": vector_list}]

                bio.face_embeddings = formatted_embedding
                bio.save()

                success_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"✅ Đã cập nhật vector cho: {username}")
                )

            except UserModel.DoesNotExist:
                fail_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f'⚠️ Bỏ qua: Username "{username}" không có trong Database.'
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"\n🎉 XONG! Thành công: {success_count} - Bỏ qua: {fail_count}"
            )
        )
