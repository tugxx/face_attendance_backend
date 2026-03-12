from django.db import IntegrityError
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.exceptions import DomainError
from custom_account.services import user_service


class SoftDeleteUserView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, user_id):
        try:
            result = user_service.soft_delete_user(user_id=user_id)

            return Response(
                {
                    "success": result,
                    "message": "User đã được xóa mềm thành công",
                    "user_id": user_id,
                },
                status=status.HTTP_200_OK,
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
