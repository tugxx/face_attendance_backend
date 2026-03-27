from django.core.files.storage import default_storage
from django.db import IntegrityError
from pydantic import ValidationError
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.mixins import RoleBasedOutputMixin
from core.exceptions import DomainError
from custom_account.api.dtos.user_dto import (
    UserAdminOutput,
    UserInput,
    UserPublicOutput,
)
from custom_account.services import user_service
from custom_account.tasks import process_bulk_upload_task


class RegisterView(RoleBasedOutputMixin, APIView):
    permission_classes = [permissions.AllowAny]

    output_dto_public = UserPublicOutput
    output_dto_admin = UserAdminOutput

    def post(self, request):
        try:
            user_input_dto = UserInput(**request.data)

            # call service with domain object
            user_domain = user_service.register_user(data=user_input_dto)

        except ValidationError as e:
            # 3. Bắt lỗi cú pháp từ Pydantic (Sai email, pass ngắn, sai regex phone...)
            # e.errors() sẽ trả về một mảng JSON báo lỗi rất chi tiết chỉ rõ sai ở trường nào
            return Response(
                {"validation_errors": e.errors()}, status=status.HTTP_400_BAD_REQUEST
            )

        except DomainError as e:  # <-- Catch DomainError
            # Catch the custom domain error from your service
            return Response(
                {"error": str(e)},  # Use the error message from the exception
                status=status.HTTP_400_BAD_REQUEST,
            )

        except IntegrityError:
            # Catch the database error when a unique constraint fails
            return Response(
                {"error": "A user with that username or email already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Put the domain object in the response so the mixin can pick it up
        return Response({"instance": user_domain}, status=status.HTTP_201_CREATED)


class BulkRegisterStudentView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, *args, **kwargs):
        excel_file = request.FILES.get("file")

        if not excel_file:
            return Response(
                {"error": "Vui lòng đính kèm file Excel trong trường 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Kiểm tra đuôi file
        if not excel_file.name.endswith((".xlsx", ".xls")):
            return Response(
                {"error": "Định dạng file không hợp lệ. Vui lòng dùng .xlsx hoặc .xls"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_name = default_storage.save(f"tmp/{excel_file.name}", excel_file)
        file_path = default_storage.path(file_name)

        # 2. GIAO VIỆC CHO CELERY (Dùng method .delay)
        # Lệnh này mất 0.01 giây. Celery nhận lệnh xong Django sẽ đi tiếp.
        process_bulk_upload_task.delay(file_path)

        # 3. TRẢ VỀ NGAY LẬP TỨC CHO FRONTEND
        return Response(
            {
                "message": "Đã tiếp nhận file Excel. Hệ thống đang xử lý ngầm.",
                "status": "processing",
            },
            status=status.HTTP_202_ACCEPTED,  # Dùng 202 Accepted là chuẩn nhất cho tác vụ ngầm
        )
