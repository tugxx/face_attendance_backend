"""
ASGI config for core_system project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

from offline_sync.middleware import JWTAuthWebSocketMiddleware
from offline_sync.routing import websocket_urlpatterns

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core_system.settings")

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        # 1. Khách đi cổng HTTP (API Login, CRUD...) -> Đẩy cho Django xử lý như bình thường
        "http": django_asgi_app,
        # 2. Khách đi cổng WebSocket -> Đẩy vào Routing của thư mục offline_sync
        "websocket": JWTAuthWebSocketMiddleware(URLRouter(websocket_urlpatterns)),
    }
)
