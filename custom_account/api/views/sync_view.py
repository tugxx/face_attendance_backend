from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from core.api.mixins import RoleBasedOutputMixin
from custom_account.services import sync_service 
from custom_account.serializers import UserSyncSerializer 
from custom_account.api.dtos.sync_dto import SyncResultOutput



class SyncUsersAPIView(RoleBasedOutputMixin, APIView):
    """
    GET /api/sync/users/?last_sync=2024-03-09T10:00:00Z
    """
    permission_classes = [permissions.IsAuthenticated]

    output_dto_public = SyncResultOutput
    output_dto_admin = SyncResultOutput

    def get(self, request):
        last_sync_str = request.query_params.get('last_sync')

        try:
            # 1. Chuyển việc nặng cho Service xử lý
            sync_result_domain = sync_service.get_incremental_sync_data(last_sync_str)
            
            return Response({"instance": sync_result_domain}, status=status.HTTP_200_OK)
        except ValueError as e:
            # Xử lý lỗi từ Service ném ra
            return Response(
                {"detail": str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )