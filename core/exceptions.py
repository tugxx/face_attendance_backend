class DomainError(Exception):
    """
    Base class cho tất cả các exception thuộc về nghiệp vụ (Domain) của dự án.
    Giúp phân biệt lỗi của Python (KeyError, IndexError) và lỗi do logic app.
    """
    pass