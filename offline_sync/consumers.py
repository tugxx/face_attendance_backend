import json

from channels.generic.websocket import AsyncWebsocketConsumer


class SyncConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Khi Flutter kết nối, cho nó vào một nhóm chung tên là 'sync_devices'
        self.group_name = "sync_devices"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        # Khi máy tính bảng mất mạng/rút điện, xóa nó khỏi nhóm
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def sync_signal(self, event):
        # Hàm này được gọi khi Django nhận thấy có data mới (từ DB)
        # Bắn chữ "SYNC_NOW" qua ống WebSocket xuống Flutter
        await self.send(text_data=json.dumps({"action": event["action"]}))
