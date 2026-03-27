import uuid

from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email must be set")
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(username, email, password, **extra_fields)


class UserModel(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    role = models.CharField(
        max_length=20,
        choices=[
            ("student", "Student"),
            ("instructor", "Instructor"),
            ("admin", "Admin"),
        ],
        default="student",
    )
    phone = models.CharField(max_length=15, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        app_label = "custom_account"
        indexes = [models.Index(fields=["role"])]
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["email"]

    def __str__(self):
        return self.email


class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="profile",
    )

    identity_code = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        help_text="Mã định danh vật lý (VD: HS0001, GV0002). Dùng làm tên folder ảnh.",
    )

    # --- Basic Info ---
    display_name = models.CharField(max_length=150, blank=True, null=True)
    avatar_id = models.TextField(blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    gender = models.CharField(
        max_length=16,
        choices=[("male", "Male"), ("female", "Female"), ("other", "Other")],
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Profile"
        verbose_name_plural = "Profiles"

    def __str__(self):
        return f"{self.display_name or self.user.email}"


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
        BiometricCredential,
        on_delete=models.CASCADE,
        related_name="face_templates",  # Lát nữa gọi user.biometric.face_templates.all()
    )

    # Tên model AI (Ví dụ: 'mobilefacenet_tflite', 'arcface_r100')
    model_name = models.CharField(max_length=50, db_index=True)

    # Phân loại (primary, with_glasses, no_makeup...)
    template_type = models.CharField(max_length=30, default="primary")

    # Chứa mảng float
    vector = models.JSONField()
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
        unique_together = ("biometric", "model_name", "template_type")
        verbose_name = "Face Template"

    def __str__(self):
        return f"{self.biometric.user.email} - {self.model_name} ({self.template_type})"


class StudentProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="student_profile",
    )

    # class_room = models.ForeignKey('ClassRoom', on_delete=models.SET_NULL, null=True) # Mở ra khi bạn tạo bảng ClassRoom
    parent_name = models.CharField(
        max_length=150, blank=True, null=True, help_text="Tên phụ huynh"
    )
    parent_phone = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        help_text="Số điện thoại phụ huynh để báo điểm danh",
    )
    enrollment_year = models.IntegerField(default=0, help_text="Năm nhập học")

    def __str__(self):
        return f"Student Data: {self.user.email}"
