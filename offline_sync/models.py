import uuid

from django.conf import settings
from django.db import models


class AttendanceLog(models.Model):
    # 1. Khóa chính: PHẢI DÙNG UUID
    # Lý do: App Flutter có thể tự tạo UUID ngay lúc offline để lưu vào Hive,
    # khi đẩy lên Server sẽ không bao giờ bị trùng ID với các máy điểm danh khác.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # 2. Người điểm danh
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,  # Nếu xóa user (xóa cứng), xóa luôn log (dù ta đã khuyên dùng xóa mềm)
        related_name="attendance_logs",
    )

    # 3. Thông tin thiết bị
    device_id = models.CharField(
        max_length=100, help_text="Mã thiết bị điểm danh (VD: GATE_01_GATEWAY)"
    )

    # 4. Thời gian điểm danh: TUYỆT ĐỐI KHÔNG DÙNG auto_now_add
    # Lý do: auto_now_add sẽ lấy giờ Server lúc nhận được API (VD: 3h chiều).
    # Trong khi sự kiện điểm danh thực tế diễn ra lúc 7h sáng offline.
    check_in_time = models.DateTimeField(db_index=True)

    # 5. Phương thức điểm danh
    method = models.CharField(
        max_length=20,
        choices=[
            ("face", "Khuôn mặt"),
            ("rfid", "Thẻ từ / RFID"),
            ("qr", "Mã QR"),
            ("manual", "Thủ công (Giáo viên thêm)"),
        ],
        default="face",
    )

    # 6. Metadata phụ trợ
    confidence_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Độ tự tin của AI khi nhận diện (VD: 0.98 là 98% giống)",
    )
    liveness_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Điểm chống giả mạo (Spoofing) (VD: 0.99 là người thật)",
    )

    evidence_image = models.ImageField(
        upload_to="attendance_evidence/%Y-%m-%d/",  # Tự chia thư mục theo năm/tháng/ngày
        null=True,
        blank=True,
        help_text="Ảnh chụp lại khuôn mặt lúc điểm danh để đối chứng",
    )

    is_offline_log = models.BooleanField(
        default=False,
        help_text="True nếu điểm danh lúc rớt mạng và được đồng bộ đẩy lên sau",
    )

    # 7. Thời gian thực tế Server nhận được bản ghi này (Audit tracking)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Lịch sử điểm danh"
        verbose_name_plural = "Lịch sử điểm danh"
        ordering = ["-check_in_time"]  # Sắp xếp mặc định: Mới nhất lên đầu

        # ---------------------------------------------------------
        # TỐI ƯU HÓA DATABASE (Cực kỳ quan trọng)
        # ---------------------------------------------------------
        constraints = [
            # Chống Spam/Duplicate: 1 user không thể có 2 log trong cùng 1 tích tắc.
            # Rất cần thiết để lệnh bulk_create(ignore_conflicts=True) hoạt động.
            models.UniqueConstraint(
                fields=["user", "check_in_time"], name="unique_attendance_per_user_time"
            )
        ]

        indexes = [
            # Index kép: Cực kỳ hữu ích khi sau này bạn làm tính năng:
            # "Lọc lịch sử điểm danh của sinh viên A trong tháng 3"
            models.Index(fields=["user", "check_in_time"]),
        ]

    def __str__(self):
        return f"[{self.device_id}] {self.user.email} - {self.check_in_time.strftime('%Y-%m-%d %H:%M:%S')} ({self.method})"
