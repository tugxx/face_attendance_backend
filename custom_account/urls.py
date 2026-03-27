from dj_rest_auth.views import LoginView  # , LogoutView, PasswordResetView
from django.urls import path
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)

from custom_account.api.views.auth_view import BulkRegisterStudentView, RegisterView
from custom_account.api.views.user_view import SoftDeleteUserView

urlpatterns = [
    path("register", RegisterView.as_view(), name="account-register"),
    path("login", LoginView.as_view(), name="account_login"),
    path("token/refresh", TokenRefreshView.as_view(), name="token_refresh"),
    #
    path("delete/<uuid:user_id>", SoftDeleteUserView.as_view(), name="soft-delete"),
    #
    path("register/bulk", BulkRegisterStudentView.as_view(), name="register-bulk"),
]
