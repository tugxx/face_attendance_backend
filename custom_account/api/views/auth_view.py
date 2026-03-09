from django.db import IntegrityError
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from custom_account.api.dtos.user_dto import UserInput, UserPublicOutput, UserAdminOutput
from core.api.mixins import RoleBasedOutputMixin
from custom_account.serializers import RegisterSerializer
from custom_account.services import user_service
from core.exceptions import DomainError



class RegisterView(RoleBasedOutputMixin, APIView):
    permission_classes = [permissions.AllowAny]

    output_dto_public = UserPublicOutput
    output_dto_admin = UserAdminOutput

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_input_dto = UserInput(**serializer.validated_data)

        try:
            # call service with domain object
            user_domain = user_service.register_user(data=user_input_dto.to_dict()) # Pass the domain object

        except DomainError as e: # <-- Catch DomainError
            # Catch the custom domain error from your service
            return Response(
                {"error": str(e)}, # Use the error message from the exception
                status=status.HTTP_400_BAD_REQUEST
            )

        except IntegrityError:
            # Catch the database error when a unique constraint fails
            return Response(
                {"error": "A user with that username or email already exists."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Put the domain object in the response so the mixin can pick it up
        return Response({"instance": user_domain}, status=status.HTTP_201_CREATED)