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
    #
    identity_code = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        help_text="Mã định danh vật lý (VD: HS0001, GV0002). Dùng làm tên folder ảnh.",
    )
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
