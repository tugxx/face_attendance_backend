import logging
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.utils import timezone
from pydantic import ValidationError

from core.exceptions import DomainError, UserNotFoundError
from custom_account.api.dtos.user_dto import UserInput
from custom_account.domains.user_domain import UserDomain
from custom_account.models import (
    Profile,
    StudentProfile,
    UserModel,
)
from offline_sync.models import BiometricCredential
from utils.profiler import TimeProfiler

logger = logging.getLogger(__name__)


def _hash_dto_password(item):
    item["hashed"] = make_password(item["dto"].password)
    return item


@transaction.atomic
def register_user(data: UserInput):  # Thêm type hint -> UserDomain tuỳ ý bạn
    """Register a new user and route to appropriate profile creation."""
    # 1. Enforce business invariants (uniqueness)
    if UserModel.objects.filter(username=data["username"]).exists():
        raise DomainError("Username đã tồn tại.")
    if UserModel.objects.filter(email=data["email"]).exists():
        raise DomainError("Email đã tồn tại.")
    if data.get("phone") and UserModel.objects.filter(phone=data["phone"]).exists():
        raise DomainError("Số điện thoại đã tồn tại.")

    # 2. Map sang Domain Object
    user_domain = UserDomain(
        username=data.username,
        email=data.email,
        raw_password=data.password,
        phone=data.phone,
    )

    # 3. Lưu vào Database
    user = user_domain.to_model()
    user.save()

    # ==========================================
    # 4. CẤP PHÁT MÃ ĐỊNH DANH (IDENTITY_CODE) & TẠO PROFILE CHUNG
    # ==========================================
    # Cấu hình tiền tố theo Role
    prefix = "HS"
    max_retries = 3

    for attempt in range(max_retries):
        # Tìm mã identity_code lớn nhất hiện tại của prefix này
        last_profile = (
            Profile.objects.filter(identity_code__startswith=prefix)
            .order_by("-identity_code")
            .first()
        )

        next_number = (
            int(last_profile.identity_code[len(prefix) :]) + 1 if last_profile else 1
        )
        temp_identity_code = f"{prefix}{next_number:05d}"

        try:
            with transaction.atomic():
                Profile.objects.create(
                    user=user,
                    identity_code=temp_identity_code,
                    display_name=data.get("display_name", ""),
                    # Thêm các trường cơ bản khác nếu API có truyền lên
                )
            # Lưu thành công -> Thoát vòng lặp
            break

        except IntegrityError as error:
            if attempt == max_retries - 1:
                logger.error(f"Không thể tạo identity_code sau {max_retries} lần thử.")
                raise DomainError(
                    "Hệ thống đang bận, không thể cấp phát mã định danh. Vui lòng thử lại."
                ) from error

            logger.warning(
                f"Va chạm mã {temp_identity_code}, đang thử lại lần {attempt + 1}..."
            )

    # ==========================================
    # 5. TẠO CÁC BẢNG NGHIỆP VỤ MỞ RỘNG
    # ==========================================
    BiometricCredential.objects.create(user=user)
    StudentProfile.objects.create(
        user=user,
        # Sau này có thể truyền thêm: parent_name=data.get("parent_name")
    )

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


def register_students_bulk(rows: list[dict]) -> dict:
    """
    Xử lý danh sách học sinh từ file Excel.
    Tham số `rows` có dạng:
    [
        {"username": "tung1", "email": "t@t.com", "password": "123", "phone": "0123456789"},
        {"username": "hai2", "email": "h@h.com", "password": "123", "phone": "0123456780"}
    ]
    """
    errors = []
    valid_dtos = []

    blank_rows = 0

    # ==========================================
    # PASS 1: VALIDATE CÚ PHÁP VÀ GOM DỮ LIỆU
    # ==========================================
    with TimeProfiler("Pass 1: Validate Pydantic DTOs"):
        for index, row_data in enumerate(rows, start=2):
            try:
                if not any(str(val).strip() for val in row_data.values()):
                    blank_rows += 1
                    continue

                user_dto = UserInput(**row_data)
                valid_dtos.append({"index": index, "dto": user_dto})

            except ValidationError as e:
                # Bắt lỗi từ Pydantic
                field_name = e.errors()[0]["loc"][0]
                error_msg = e.errors()[0]["msg"]

                # Pydantic V2 thường tự gắn thêm chữ "Value error, " ở đầu câu, ta cắt nó đi cho đẹp
                clean_msg = error_msg.replace("Value error, ", "")

                errors.append(f"Dòng {index} - Cột '{field_name}': {clean_msg}")

    # ==========================================
    # PASS 2: VALIDATE NGHIỆP VỤ (Bulk Check Database)
    # Lấy 1 phát toàn bộ email/username để đối chiếu trên RAM (Cực nhanh)
    # ==========================================
    with TimeProfiler("Pass 2: Hash Password Song Song"):
        with ThreadPoolExecutor() as executor:
            valid_dtos = list(executor.map(_hash_dto_password, valid_dtos))

    with TimeProfiler("Pass 3: Khớp DB và Hash Password"):
        incoming_emails = [item["dto"].email for item in valid_dtos]
        incoming_usernames = [item["dto"].username for item in valid_dtos]
        incoming_phones = [
            item["dto"].phone for item in valid_dtos if item["dto"].phone
        ]

        existing_emails = set(
            UserModel.objects.filter(email__in=incoming_emails).values_list(
                "email", flat=True
            )
        )
        existing_usernames = set(
            UserModel.objects.filter(username__in=incoming_usernames).values_list(
                "username", flat=True
            )
        )
        existing_phones = set(
            UserModel.objects.filter(phone__in=incoming_phones).values_list(
                "phone", flat=True
            )
        )

        users_to_create = []

        for item in valid_dtos:
            idx = item["index"]
            dto = item["dto"]

            # Lọc ra những ông bị trùng
            if dto.email in existing_emails:
                errors.append(f"Dòng {idx}: Email '{dto.email}' đã tồn tại.")
                continue
            if dto.username in existing_usernames:
                errors.append(f"Dòng {idx}: Username '{dto.username}' đã tồn tại.")
                continue
            if dto.phone and dto.phone in existing_phones:
                errors.append(f"Dòng {idx}: Số điện thoại '{dto.phone}' đã tồn tại.")
                continue

            # Tạo object UserModel (BẮT BUỘC DÙNG make_password VÌ BULK_CREATE KHÔNG TỰ BĂM)
            user = UserModel(
                username=dto.username,
                email=dto.email,
                password=item["hashed"],
                role="student",
                phone=dto.phone,
            )
            users_to_create.append(user)

        if not users_to_create:
            return {
                "total_processed": len(rows) - blank_rows,
                "success_count": 0,
                "error_count": len(errors),
                "errors": errors,
            }

    # ==========================================
    # PASS 3: BULK CREATE (Thực thi siêu tốc vào DB)
    # ==========================================
    with TimeProfiler("Pass 4: Bulk Create Database"):
        with transaction.atomic():
            # 1. Bắn 1 cục vào bảng UserModel
            created_users = UserModel.objects.bulk_create(
                users_to_create, batch_size=500
            )

            # 2. Xử lý cấp phát identity_code trên RAM
            prefix = "HS"
            last_profile = (
                Profile.objects.filter(identity_code__startswith=prefix)
                .order_by("-identity_code")
                .first()
            )
            start_number = (
                int(last_profile.identity_code[len(prefix) :]) + 1
                if last_profile
                else 1
            )

            profiles_to_create = []
            bios_to_create = []
            students_to_create = []

            for i, user in enumerate(created_users):
                # Tính toán mã tiếp theo tịnh tiến dần
                new_code = f"{prefix}{start_number + i:05d}"

                # PostgreSQL trả về user.id sau khi bulk_create, nên ta gán vào Profile vô tư
                profiles_to_create.append(Profile(user=user, identity_code=new_code))
                bios_to_create.append(BiometricCredential(user=user))
                students_to_create.append(StudentProfile(user=user))

            # 3. Bắn 1 cục vào các bảng vệ tinh
            Profile.objects.bulk_create(profiles_to_create, batch_size=500)
            BiometricCredential.objects.bulk_create(bios_to_create, batch_size=500)
            StudentProfile.objects.bulk_create(students_to_create, batch_size=500)

            if True:
                # Ép PostgreSQL hoàn tác toàn bộ các lệnh bulk_create vừa chạy ở trên!
                transaction.set_rollback(True)

    # Trả về một bản báo cáo chi tiết để View hiển thị cho người dùng
    return {
        "total_processed": len(rows) - blank_rows,
        "success_count": len(created_users),
        "error_count": len(errors),
        "errors": errors,  # Mảng chứa các câu thông báo lỗi
    }
