import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from offline_sync.models import AttendanceLog

logger = logging.getLogger(__name__)


@database_sync_to_async
def save_attendance_log_from_socket(log_data):
    try:
        checkin_id = log_data.get("id")

        # Lấy value từ payload của App gửi lên
        student_id_val = log_data.get("student_id")
        device_id_val = log_data.get("device_id")
        timestamp_val = log_data.get("timestamp")
        confidence_val = log_data.get("confidence")
        liveness_score_val = log_data.get("liveness_score")

        # Gán vào đúng tên field của Model Django
        AttendanceLog.objects.update_or_create(
            id=checkin_id,
            defaults={
                "user_id": student_id_val,
                "device_id": device_id_val,
                "check_in_time": timestamp_val,
                "confidence_score": confidence_val,
                "liveness_score": liveness_score_val,
                "method": "face",  # Bổ sung thêm cho giống HTTP bulk
                "is_offline_log": False,  # Điểm danh real-time thì là online
            },
        )
        return True
    except Exception as e:
        logger.error(f"🔴 Lỗi lưu Database từ WebSocket: {str(e)}")
        return False


class SyncConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # 1. Lấy user từ scope (do JWT Middleware truyền vào)
        user = self.scope.get("user")

        # 2. Kiểm tra xác thực
        if user and user.is_authenticated:
            # Khi Flutter kết nối, cho nó vào một nhóm chung tên là 'sync_devices'
            self.group_name = "sync_devices"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            logger.info(
                f"Thiết bị kết nối thành công: {self.channel_name} (Tài khoản: {user.email})"
            )
        else:
            # Token sai, hết hạn, hoặc không có token -> Đuổi thẳng cổ
            logger.warning(
                f"Từ chối kết nối WebSocket: Token không hợp lệ hoặc thiếu (IP: {self.scope['client']})"
            )
            # Đóng kết nối với mã lỗi 4001 (Unauthorized) để App Flutter biết mà xin lại Token mới
            await self.close(code=4001)

    async def disconnect(self, close_code):
        # Khi máy tính bảng mất mạng/rút điện, xóa nó khỏi nhóm
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info(f"Thiết bị ngắt kết nối (Mã: {close_code}): {self.channel_name}")

    async def sync_signal(self, event):
        """
        Hàm này sẽ được gọi khi bạn lưu học sinh mới trong DB.
        Redis sẽ kích hoạt hàm này.
        """
        action_type = event["action"]  # VD: "SYNC_NOW"
        payload = event.get("payload", {})

        # Gửi cục JSON xuống App Flutter thông qua ống WebSocket
        await self.send(text_data=json.dumps({"action": action_type, "data": payload}))

    async def receive(self, text_data):
        # text_data chính là cục chuỗi JSON mà App Flutter bắn lên
        data = json.loads(text_data)
        action = data.get("action")

        if action == "checkin":
            log_data = data.get("data", {})
            checkin_id = log_data.get("id")  # UUID gửi từ App
            student_id = log_data.get("student_id")

            logger.info(
                f"⏳ Đang xử lý log điểm danh của {student_id} (ID: {checkin_id})"
            )

            is_saved = await save_attendance_log_from_socket(log_data)

            if is_saved:
                logger.info(f"✅ Đã lưu Database thành công cho {student_id}")

                # Bắn ngược lại App Flutter báo lưu thành công
                await self.send(
                    text_data=json.dumps(
                        {
                            "action": "CHECKIN_SUCCESS",
                            "data": {"uuid": checkin_id, "status": "ok"},
                        }
                    )
                )
            else:
                # Nếu lưu DB xịt, báo lỗi về để App Flutter biết mà đẩy sang luồng HTTP (Bulk Push) dự phòng
                await self.send(
                    text_data=json.dumps(
                        {
                            "action": "CHECKIN_FAILED",
                            "data": {"uuid": checkin_id, "error": "Database error"},
                        }
                    )
                )
