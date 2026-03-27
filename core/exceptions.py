class DomainError(Exception):
    """
    Base class cho tất cả các exception thuộc về nghiệp vụ (Domain) của dự án.
    Giúp phân biệt lỗi của Python (KeyError, IndexError) và lỗi do logic app.
    """

    pass


# =============================================================================
# 1. NHÓM LỖI KHÔNG TÌM THẤY (RESOURCE NOT FOUND)
# Thường map về HTTP 404 Not Found
# =============================================================================


class ResourceNotFound(DomainError):
    """Base class cho các lỗi không tìm thấy dữ liệu."""

    pass


class UserNotFoundError(Exception):
    pass


class AttendanceLogNotFound(Exception):
    pass


# =============================================================================
# 2. NHÓM LỖI LOGIC & VALIDATION (BUSINESS LOGIC ERRORS)
# Thường map về HTTP 400 Bad Request hoặc 403 Forbidden
# =============================================================================


class BusinessLogicError(DomainError):
    """Base class cho các lỗi vi phạm quy tắc nghiệp vụ."""

    pass


class DomainValidationError(BusinessLogicError):
    """Lỗi khi validate dữ liệu đầu vào không thỏa mãn logic domain."""

    pass


# =============================================================================
# 3. NHÓM LỖI QUYỀN TRUY CẬP & TRẠNG THÁI (ACCESS & STATE)
# Thường map về HTTP 403 Forbidden
# =============================================================================


class AccessDeniedError(DomainError):
    """Base class cho các lỗi từ chối truy cập."""

    pass
