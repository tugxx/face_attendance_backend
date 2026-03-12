from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
import logging

from core.api.mixins import RoleBasedOutputMixin, PaginationMixin
from offline_sync.api.dtos.sync_dto import SyncResultOutput
from offline_sync.services import sync_service 
from offline_sync.domains.user_sync_domain import UserSyncDomain



logger = logging.getLogger(__name__)

class SyncUsersView(RoleBasedOutputMixin, PaginationMixin, APIView):
    """
    GET /api/sync/users/?last_sync=...&page=1&page_size=500
    """
    permission_classes = [permissions.IsAuthenticated]

    output_dto_public = SyncResultOutput
    output_dto_admin = SyncResultOutput

    def get(self, request, *args, **kwargs):
        try:
            # Lấy mốc thời gian trước khi bất kỳ lệnh DB nào được chạy
            current_server_time = timezone.now()

            # 1. INPUT VALIDATION
            last_sync_str = request.query_params.get('last_sync')

            # 2. GET QUERYSET (Lazy Loading)
            queryset = sync_service.get_incremental_sync_queryset(last_sync_str)

            # 3. PAGINATION & EXECUTION
            # Mixin của bạn sẽ lo việc tính tổng số trang, giới hạn limit/offset
            paginated_result = self.paginate_queryset(queryset, request)

            # 4. DOMAIN MAPPING
            domain_items = []
            for model_instance in paginated_result['items']:
                domain_obj = UserSyncDomain.from_model(model_instance)
                if domain_obj:
                    domain_items.append(domain_obj)

            paginated_result['items'] = domain_items
            
            # 5. INJECT SERVER TIME (Đặc thù của API Sync)
            # Thêm thời gian server vào cục response để App Flutter lấy làm mốc cho lần sau
            paginated_result['server_time'] = current_server_time

            # 6. RETURN
            return Response(paginated_result, status=status.HTTP_200_OK)

        except ValueError as ve:
            return Response({"detail": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error syncing users: {e}", exc_info=True)
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)