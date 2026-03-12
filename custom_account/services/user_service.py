from uuid import UUID

from django.db import transaction
from django.utils import timezone

from core.exceptions import DomainError, UserNotFoundError
from custom_account.domains.user_domain import UserDomain
from custom_account.models import (
    BiometricCredential,
    Profile,
    StudentProfile,
    UserModel,
)


@transaction.atomic
def register_user(data: dict):  # Thêm type hint -> UserDomain tuỳ ý bạn
    """Register a new user and route to appropriate profile creation."""

    # profile_data = data.pop("profile", {})

    # 1. Enforce business invariants (uniqueness)
    if UserModel.objects.filter(username=data["username"]).exists():
        raise DomainError("Username đã tồn tại.")
    if UserModel.objects.filter(email=data["email"]).exists():
        raise DomainError("Email đã tồn tại.")
    if data.get("phone") and UserModel.objects.filter(phone=data["phone"]).exists():
        raise DomainError("Số điện thoại đã tồn tại.")

    # 2. Map sang Domain Object
    user_domain = UserDomain(
        username=data["username"],
        email=data["email"],
        raw_password=data["password"],
        role=data["role"],
        phone=data.get("phone"),
    )

    # 3. Lưu vào Database
    user = user_domain.to_model()
    user.save()

    # 4. TẠO PROFILE THEO ROLE (NEW LOGIC)
    # Tạo Profile cơ bản chung cho tất cả mọi người (chứa Tên hiển thị, Avatar, Ngày sinh)
    Profile.objects.create(user=user)

    if data["role"] in ["student", "teacher", "driver"]:
        BiometricCredential.objects.create(user=user)

    # Nếu là học sinh, tự động cấp phát một bản ghi StudentProfile để hứng dữ liệu Điểm danh sau này
    if data["role"] == "student":
        # Sinh mã học sinh ngẫu nhiên tạm thời (VD: HS + 6 ký tự cuối của UUID)
        temp_student_code = f"HS{str(user.id).split('-')[-1][:6].upper()}"

        StudentProfile.objects.create(
            user=user,
            student_code=temp_student_code,
            # Các trường face_vector, rfid_card_id sẽ để trống, chờ cập nhật sau qua App
        )
    # TODO: Sau này có thể mở rộng: if data['role'] == 'driver': BusDriverProfile.objects.create(...)

    user_domain.id = user.id
    return UserDomain.from_model(user)


def soft_delete_user(user_id: UUID | str) -> bool:
    """
    Xóa mềm (Soft Delete) User thay vì xóa cứng khỏi Database.
    Hỗ trợ cơ chế Tombstone để đồng bộ Offline xuống App Flutter.
    """
    try:
        # Lấy user kèm theo biometric để xử lý trong 1 transaction an toàn
        user = UserModel.objects.select_related("biometric").get(id=user_id)

        if not user.is_active:
            # Nếu đã bị xóa mềm từ trước, không cần làm gì thêm
            return True

        with transaction.atomic():
            # 1. Vô hiệu hóa User
            user.is_active = False
            user.updated_on = timezone.now()  # Ép cập nhật giờ để API Sync quét trúng
            user.save(update_fields=["is_active", "updated_on"])

            # 2. Vô hiệu hóa luôn Khóa sinh trắc học (nếu có)
            # Tránh trường hợp User bị khóa nhưng thẻ RFID vẫn còn active ở đâu đó
            if hasattr(user, "biometric") and user.biometric:
                user.biometric.is_active = False
                user.biometric.updated_at = timezone.now()
                user.biometric.save(update_fields=["is_active", "updated_at"])

        return True

    except UserModel.DoesNotExist as error:
        raise UserNotFoundError(
            f"Không tìm thấy người dùng với ID: {user_id}"
        ) from error
