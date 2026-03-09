from django.urls import path, re_path
from rest_framework_simplejwt.views import TokenRefreshView  # For token refresh endpoint
from dj_rest_auth.views import LoginView # , LogoutView, PasswordResetView

from custom_account.api.views.auth_view import RegisterView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="account-register"),
    path('login/', LoginView.as_view(), name='account_login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]