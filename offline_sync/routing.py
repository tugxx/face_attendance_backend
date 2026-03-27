from django.urls import re_path

from offline_sync import consumers

websocket_urlpatterns = [
    # App Flutter sẽ connect vào địa chỉ: ws://domain.com/ws/sync/
    re_path(r"ws/sync/$", consumers.SyncConsumer.as_asgi()),
]
