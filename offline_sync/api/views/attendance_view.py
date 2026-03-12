from pydantic import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import permissions, status
import logging

from core.api.mixins import RoleBasedOutputMixin, PaginationMixin
from offline_sync.api.dtos.attendance_dto import OfflineAttendanceUploadInput, OfflineAttendanceUploadOutput
from offline_sync.services.attendance_service import process_offline_attendance_logs    



logger = logging.getLogger(__name__)

class AttendanceLogView(RoleBasedOutputMixin, APIView):
    """ 
    API nhận danh sách điểm danh offline và trả về kết quả đồng bộ.
    """
    permission_classes = [permissions.IsAuthenticated]

    output_dto_public = OfflineAttendanceUploadOutput
    output_dto_admin = OfflineAttendanceUploadOutput

    def post(self, request):
        try:
            input_dto = OfflineAttendanceUploadInput(**request.data)
        except ValidationError as e:
            return Response(e.errors(), status=status.HTTP_400_BAD_REQUEST)
    
        try:
            result_stats = process_offline_attendance_logs(input_dto)

            response_data = {
                "inserted": result_stats.get("inserted", 0),
                "ignored": result_stats.get("invalid_users_ignored", 0),
                "synced_log_ids": [log.id for log in input_dto.logs if log.id] 
            }

            return Response({"instance": response_data}, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    