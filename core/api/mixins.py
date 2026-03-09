import logging
from pydantic import BaseModel
from typing import Type, Any, Optional
from django.db.models.query import QuerySet
from rest_framework.exceptions import APIException
from rest_framework.views import APIView



logger = logging.getLogger(__name__)

class DtoMappingError(APIException):
    status_code = 500
    default_detail = 'DTO mapping failed.'
    default_code = 'dto_mapping_error'
    
class RoleBasedOutputMixin:
    """
    Mixin tự động chọn DTO output dựa trên vai trò user và quan hệ với object.
    
    Priority:
    1. Admin/Staff -> output_dto_admin
    2. Owner (Instructor) -> output_dto_instructor (Kiểm tra instance.owner_id == user.id)
    3. Self (User Profile) -> output_dto_self (Kiểm tra instance.id == user.id)
    4. Public -> output_dto_public
    """

    output_dto_public: Type[BaseModel]
    output_dto_admin: Optional[Type[BaseModel]] = None
    output_dto_instructor: Optional[Type[BaseModel]] = None # NEW: DTO cho chủ sở hữu resource
    output_dto_self: Optional[Type[BaseModel]] = None       # DTO cho chính bản thân user (Profile)

    def _select_dto_class(self, instance: Any, request) -> Type[BaseModel]:
        """Chọn DTO class phù hợp."""
        user = request.user
        is_auth = user.is_authenticated

        # 1. Admin / Staff -> Admin DTO
        if is_auth and user.is_staff and self.output_dto_admin:
            return self.output_dto_admin

        # 2. Instructor / Owner -> Instructor DTO (NEW LOGIC)
        # Logic: Nếu user là người tạo ra instance này (owner_id khớp)
        if self.output_dto_instructor and is_auth:
            # Lấy owner_id từ instance (Domain Object hoặc Model đều thường có field này)
            # Dùng getattr để tránh lỗi nếu object không có field owner
            obj_owner_id = getattr(instance, 'owner_id', getattr(instance, 'owner', None))
            
            # Nếu owner là object User, lấy ID của nó
            if hasattr(obj_owner_id, 'id'):
                obj_owner_id = obj_owner_id.id

            # So sánh ID (chuyển về string hoặc uuid để so sánh an toàn)
            if str(obj_owner_id) == str(user.id):
                return self.output_dto_instructor

        # 3. Self -> Self DTO (Dùng cho User Profile)
        # Logic: instance chính là user đang login
        if (self.output_dto_self 
            and is_auth
            and str(getattr(instance, "id", "")) == str(user.id)):
            return self.output_dto_self

        # 4. Fallback -> Public DTO
        return self.output_dto_public

    def _to_dto(self, instance: Any, request) -> BaseModel:
        """Convert a domain object → selected DTO."""
        dto_cls = self._select_dto_class(instance, request)
        
        # `from_orm` works with Django models, SQLAlchemy, etc.
        return dto_cls.model_validate(instance) # Pydantic v2

    def finalize_response(self, request, response, *args, **kwargs):
        """
        DRF calls this *after* the view returns a Response.
        We intercept and replace the payload if it contains {"instance": ...}
        """
        if isinstance(response.data, dict):
            
            # --- CASE A: PAGINATION RESPONSE ({items, meta}) ---
            if "items" in response.data and "meta" in response.data:
                items_data = response.data["items"]
                meta_data = response.data["meta"]

                try:  
                    # Tối ưu: Nếu items_data rỗng thì khỏi map
                    if not items_data:
                        dtos = []
                    else:
                        dtos = [
                            self._to_dto(item, request).model_dump()
                            for item in items_data
                        ]
                    
                    # Cập nhật lại response data
                    response.data = {
                        "items": dtos,
                        "meta": meta_data
                    }

                except Exception as e:
                    # (Thêm exc_info=True để debug dễ hơn)
                    logger.error(f"DTO mapping/serialization failed: {e}", exc_info=True) 
                    raise DtoMappingError(f"DTO mapping/serialization failed: {e}")
            
            # --- CASE B: STANDARD RESPONSE ({instance}) ---
            elif "instance" in response.data:
                instance_data = response.data["instance"]

                try:
                    if isinstance(instance_data, (list, QuerySet)):
                        response.data = [
                            self._to_dto(item, request).model_dump()
                            for item in instance_data
                        ]
                    else:
                        response.data = self._to_dto(instance_data, request).model_dump()
                except Exception as e:
                    logger.error(f"DTO mapping failed: {e}", exc_info=True)
                    raise DtoMappingError(f"DTO mapping failed: {e}")    

        # Gọi hàm finalize_response gốc của APIView
        return APIView.finalize_response(self, request, response, *args, **kwargs)
    