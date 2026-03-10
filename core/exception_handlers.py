import logging
import traceback
from django.conf import settings
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

# Import các lỗi cần xử lý
from pydantic import ValidationError as PydanticValidationError
from core.exceptions import DomainValidationError, ResourceNotFound, BusinessLogicError, AccessDeniedError


logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    """
    Global exception handler:
    1. Bắt lỗi DRF chuẩn.
    2. Bắt lỗi Pydantic & Domain Error (chuyển thành 400/404/403).
    3. Catch-all: Log lỗi 500 và trả về thông báo an toàn.
    """
    
    # --- BƯỚC 1: Gọi handler mặc định của DRF ---
    # (Xử lý AuthenticationFailed, NotAuthenticated, PermissionDenied...)
    response = exception_handler(exc, context)

    if response is not None:
        return response

    # --- BƯỚC 2: Xử lý lỗi Nghiệp vụ & Validation (Logic Errors) ---
    # Những lỗi này là "Expected" (biết trước sẽ xảy ra), không cần log traceback 500
    
    # 2.1. Pydantic Validation Error
    if isinstance(exc, PydanticValidationError):
        errors = {}
        for error in exc.errors():
            field = error['loc'][-1] if error['loc'] else 'non_field_errors'
            errors[field] = [error['msg']]
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    # 2.2. Domain Validation (Lỗi logic service)
    if isinstance(exc, DomainValidationError):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # 2.3. Resource Not Found (Lỗi 404 từ Service)
    if isinstance(exc, ResourceNotFound):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        
    # 2.4. Business/Access Logic
    if isinstance(exc, (BusinessLogicError, AccessDeniedError)):
        # Mapping status code tùy logic, mặc định là 400 hoặc 403
        code = status.HTTP_403_FORBIDDEN if isinstance(exc, AccessDeniedError) else status.HTTP_400_BAD_REQUEST
        return Response({"detail": str(exc)}, status=code)


    # --- BƯỚC 3: Xử lý lỗi hệ thống (System Errors - 500) ---
    # Đây là phần code CỦA BẠN - Rất quan trọng để debug
    
    view = context.get('view', None)
    view_name = view.__class__.__name__ if view else 'unknown_view'

    # Log đầy đủ traceback để dev sửa bug
    logger.error(
        f"[{view_name}] Unhandled exception: {exc}\n{traceback.format_exc()}"
    )

    # Trả về JSON an toàn cho Client
    error_payload = {
        "error": "Internal Server Error",
        "detail": "An unexpected error occurred. Please contact support."
    }
    
    # Nếu đang Dev, hiện luôn lỗi ra để dễ nhìn (giống chế độ Debug của Moodle)
    if settings.DEBUG:
        error_payload["detail"] = str(exc)
        error_payload["trace"] = traceback.format_exc().splitlines()

    return Response(error_payload, status=status.HTTP_500_INTERNAL_SERVER_ERROR)