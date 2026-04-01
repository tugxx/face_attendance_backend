import uuid

from django.conf import settings
from django.db import models
from pgvector.django import HnswIndex, VectorField


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


class BiometricCredential(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="biometric",
    )

    # Dùng để quét thẻ
    rfid_card_id = models.CharField(
        max_length=50, blank=True, null=True, unique=True, help_text="Mã thẻ cứng RFID"
    )

    # Dùng để quét QR động (nếu có)
    qr_code_secret = models.CharField(
        max_length=100, blank=True, null=True, help_text="Mã bí mật tạo QR động"
    )

    is_active = models.BooleanField(default=True, help_text="Khóa thẻ/mặt nếu báo mất")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Biometric for: {self.user.email}"


class FaceTemplate(models.Model):
    biometric = models.ForeignKey(
        "BiometricCredential",
        on_delete=models.CASCADE,
        related_name="face_templates",  # Lát nữa gọi user.biometric.face_templates.all()
    )

    quality_assessor = models.CharField(
        max_length=50,
        default="unknown",
        help_text="Model chấm điểm chất lượng (VD: lightqnet, opencv_math)",
        null=True,
        blank=True,
    )
    detector_model = models.CharField(
        max_length=50,
        default="unknown",
        help_text="Model cắt mặt (VD: retinaface, scrfd)",
        null=True,
        blank=True,
    )
    extractor_model = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Model tạo vector (VD: mobilefacenet, arcface_r100)",
        null=True,
        blank=True,
    )
    vector_dimension = models.PositiveIntegerField(
        default=0, help_text="Kích thước vector (128, 512...)"
    )

    # Phân loại (primary, with_glasses, no_makeup...)
    template_type = models.CharField(max_length=30, default="primary")
    vector_json = models.JSONField(
        default=list, help_text="Mảng float lưu dạng JSON cho offline sync"
    )

    # 1. Cột dành cho model nhẹ (VD: MobileFaceNet)
    vector_128 = VectorField(
        dimensions=128, null=True, blank=True, help_text="Trường vector 128 chiều"
    )
    vector_192 = VectorField(
        dimensions=192, null=True, blank=True, help_text="Dành cho 192 chiều"
    )
    # 2. Cột dành cho model nặng/chính xác cao (VD: ArcFace_r100)
    vector_512 = VectorField(
        dimensions=512, null=True, blank=True, help_text="Trường vector 512 chiều"
    )

    image_ref = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Đường dẫn tới ảnh gốc đã crop để debug AI",
    )
    face_quality_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Điểm đánh giá chất lượng ảnh lúc đăng ký (độ sáng, rõ nét)",
    )

    is_active = models.BooleanField(
        default=True, help_text="Tắt đi nếu template này hay gây nhận vơ"
    )

    # Metadata thêm (Tùy chọn)
    sample_count = models.PositiveIntegerField(
        default=1, help_text="Số ảnh tạo nên vector này"
    )
    intra_sim_score = models.FloatField(
        null=True, blank=True, help_text="Độ đồng nhất của các ảnh gốc"
    )
    soft_margin = models.FloatField(
        null=True, blank=True, help_text="Độ an toàn cá nhân lúc khởi tạo"
    )

    # Audit
    source = models.CharField(max_length=50, default="unknown")
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # Một người không nên có 2 cái 'primary' của cùng 1 model
        unique_together = (
            "biometric",
            "detector_model",
            "extractor_model",
            "template_type",
        )
        verbose_name = "Face Template"

        indexes = [
            HnswIndex(
                name="hnsw_128_idx",
                fields=["vector_128"],
                m=16,  # Số lượng liên kết tối đa cho mỗi node (chuẩn thực tế)
                ef_construction=64,  # Kích thước danh sách ứng viên lúc build
                opclasses=["vector_cosine_ops"],  # Ép dùng thuật toán Cosine Similarity
            ),
            HnswIndex(
                name="hnsw_192_idx",
                fields=["vector_192"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
            HnswIndex(
                name="hnsw_512_idx",
                fields=["vector_512"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self):
        return f"{self.biometric.user.email} - {self.model_name} ({self.template_type})"


class EnrollmentSample(models.Model):
    # Trỏ về vector chính đã được gộp
    template = models.ForeignKey(
        "FaceTemplate", on_delete=models.CASCADE, related_name="raw_samples"
    )

    # QUAN TRỌNG NHẤT: Lưu lại ảnh gốc để sau này đổi Model AI thì có cái mà trích xuất lại
    raw_image = models.ImageField(
        upload_to="enrollment_raw_samples/%Y/%m/", help_text="Ảnh gốc lúc đăng ký"
    )

    # Lưu vector lẻ dạng JSON (Chỉ để debug hoặc test thuật toán gộp mới)
    # Không dùng pgvector ở đây để đỡ tốn tài nguyên DB
    vector_json = models.JSONField(
        null=True, blank=True, help_text="Vector đơn lẻ của bức ảnh này"
    )

    # Metadata của từng bức ảnh (VD: Điểm chất lượng ảnh này là bao nhiêu)
    quality_score = models.FloatField(null=True, blank=True)
    is_best_shot = models.BooleanField(
        default=False,
        help_text="Đánh dấu đây có phải bức ảnh đẹp nhất để làm image_ref không",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Raw Enrollment Sample"
