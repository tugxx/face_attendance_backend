import logging

from pydantic import ValidationError
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.mixins import RoleBasedOutputMixin
from offline_sync.api.dtos.attendance_dto import (
    OfflineAttendanceUploadInput,
    OfflineAttendanceUploadOutput,
)
from offline_sync.models import AttendanceLog
from offline_sync.services.attendance_service import (
    process_offline_attendance_logs,
    upload_evidence_image,
)

logger = logging.getLogger(__name__)


class PushAttendanceBulkView(RoleBasedOutputMixin, APIView):
    """
    API nhận danh sách điểm danh offline và trả về kết quả đồng bộ.
    """

    permission_classes = [permissions.IsAuthenticated]

    output_dto_public = OfflineAttendanceUploadOutput
    output_dto_admin = OfflineAttendanceUploadOutput

    def post(self, request, *args, **kwargs):
        try:
            input_dto = OfflineAttendanceUploadInput(**request.data)
        except ValidationError as e:
            return Response(e.errors(), status=status.HTTP_400_BAD_REQUEST)

        try:
            result_stats = process_offline_attendance_logs(input_dto, request.FILES)

            response_data = {
                "inserted": result_stats.get("inserted", 0),
                "ignored": result_stats.get("invalid_users_ignored", 0),
                "synced_log_ids": [log.id for log in input_dto.logs if log.id],
            }

            return Response({"instance": response_data}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PushAttendanceImageView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, log_id):
        evidence_image = request.FILES.get("evidence_image")
        if not evidence_image:
            return Response(
                {"error": "Thiếu file ảnh đính kèm (evidence_image)"}, status=400
            )

        try:
            # 2. Gọi Service xử lý logic
            upload_evidence_image(log_id, evidence_image)
            return Response(
                {"message": "Upload ảnh thành công", "log_id": log_id}, status=200
            )

        # 3. Chụp các Exception cụ thể từ Service văng lên
        except AttendanceLog.DoesNotExist:
            logger.warning(f"Upload ảnh thất bại: Log ID {log_id} không tồn tại.")
            return Response(
                {"error": f"Log ID {log_id} chưa được tạo trong Database."}, status=404
            )

        except Exception as e:
            logger.error(f"Lỗi hệ thống khi lưu ảnh {log_id}: {str(e)}")
            return Response({"error": "Lỗi hệ thống máy chủ."}, status=500)
