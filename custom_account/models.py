from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.conf import settings
import uuid



class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email must be set')
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(username, email, password, **extra_fields)
    

class UserModel(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    role = models.CharField(max_length=20, 
                            choices=[('student', 'Student'), 
                                     ('instructor', 'Instructor'), 
                                     ('admin', 'Admin')], 
                            default='student')
    phone = models.CharField(max_length=15, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        app_label = 'custom_account'
        indexes = [models.Index(fields=['role'])]
        verbose_name = ('User')
        verbose_name_plural = ('Users')
        ordering = ['email']

    def __str__(self):
        return self.email
    

class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        primary_key=True, 
        related_name='profile'
    )
    
    # --- Basic Info ---
    display_name = models.CharField(max_length=150, blank=True, null=True)
    avatar_id = models.TextField(blank=True, null=True) 
    dob = models.DateField(blank=True, null=True)
    gender = models.CharField(
        max_length=16,
        choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')],
        blank=True, null=True
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Profile'
        verbose_name_plural = 'Profiles'

    def __str__(self):
        return f"{self.display_name or self.user.email}"
    

class BiometricCredential(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True, related_name='biometric')
    
    rfid_card_id = models.CharField(max_length=50, blank=True, null=True, unique=True, help_text="Mã thẻ cứng RFID")
    qr_code_secret = models.CharField(max_length=100, blank=True, null=True, help_text="Mã bí mật tạo QR động")
    
    face_vector_1 = models.JSONField(blank=True, null=True, help_text="Vector khuôn mặt chính (128 hoặc 512 chiều)")
    face_vector_2 = models.JSONField(blank=True, null=True, help_text="Vector dự phòng (đeo kính, v.v.)")
    face_vector_3 = models.JSONField(blank=True, null=True, help_text="Vector mặt trái (nếu có)")
    face_vector_4 = models.JSONField(blank=True, null=True, help_text="Vector mặt phải (nếu có)")

    is_active = models.BooleanField(default=True, help_text="Khóa thẻ/mặt nếu báo mất")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Biometric for: {self.user.email}"
    

class StudentProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True, related_name='student_profile')
    student_code = models.CharField(max_length=50, unique=True, help_text="Mã số học sinh (VD: HS2024001)")
    # class_room = models.ForeignKey('ClassRoom', on_delete=models.SET_NULL, null=True) # Mở ra khi bạn tạo bảng ClassRoom

    def __str__(self):
        return f"Student: {self.student_code}"
    


