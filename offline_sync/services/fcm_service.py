import logging

import firebase_admin
from firebase_admin import credentials, messaging

logger = logging.getLogger(__name__)

# Khởi tạo Firebase (Chỉ chạy 1 lần khi start server)
# Bạn nhớ tải file serviceAccountKey.json từ Firebase Console về nhé
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(
            "face-attendance-9b627-firebase-adminsdk-fbsvc-43d79c7008.json"
        )
        firebase_admin.initialize_app(cred)
except Exception as e:
    logger.error(f"Lỗi khởi tạo Firebase: {e}")


def send_sync_ping_to_devices():
    """
    Bắn Silent Push (Tin nhắn ngầm) đến tất cả các máy điểm danh.
    """
    try:
        # Tạo cấu trúc tin nhắn chỉ chứa Data (Không chứa Notification để không hiện popup)
        message = messaging.Message(
            data={"action": "SYNC_NOW", "type": "USER_DATA_CHANGED"},
            topic="attendance_devices",  # Tất cả app Flutter sẽ subscribe vào topic này
        )

        response = messaging.send(message)
        logger.info(f"Đã bắn tín hiệu Sync qua FCM: {response}")
    except Exception as e:
        logger.error(f"Lỗi khi gửi FCM: {e}")
