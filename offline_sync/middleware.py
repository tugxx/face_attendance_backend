from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken

UserModel = get_user_model()


@database_sync_to_async
def get_user(user_id):
    """Hàm truy vấn DB phải được bọc trong database_sync_to_async"""
    try:
        return UserModel.objects.get(id=user_id, is_active=True)
    except UserModel.DoesNotExist:
        return AnonymousUser()


class JWTAuthWebSocketMiddleware(BaseMiddleware):
    """
    Middleware chặn các kết nối WebSocket.
    Lấy token từ Query String, giải mã và gắn User vào scope.
    """

    async def __call__(selscopef, scope, receive, send):
        # 1. Lấy query string (VD: b'token=eyJhbG...')
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = parse_qs(query_string)

        # 2. Bóc tách token
        token = query_params.get("token", [None])[0]

        if token:
            try:
                # 3. Dùng SimpleJWT để giải mã và kiểm tra độ hợp lệ của Token
                valid_data = UntypedToken(token)
                user_id = valid_data["user_id"]

                # 4. Gắn User vào  để Consumer lấy ra xài
                scope["user"] = await get_user(user_id)
            except (InvalidToken, TokenError, Exception):
                # Token hết hạn hoặc sai định dạng
                scope["user"] = AnonymousUser()
        else:
            scope["user"] = AnonymousUser()

        return await super().__call__(scope, receive, send)
