import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from custom_account.models import UserModel
from offline_sync.services.fcm_service import send_sync_ping_to_devices

logger = logging.getLogger(__name__)


def broadcast_hybrid_sync_signal():
    """
    Hàm này làm 2 nhiệm vụ:
    1. Bắn WebSocket cho máy đang mở màn hình.
    2. Bắn FCM cho máy đang tắt màn hình.
    """
    logger.info("Đang phát tín hiệu SYNC_NOW tới toàn bộ thiết bị...")

    # 1. Bắn qua WebSocket
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "sync_devices",
        {
            "type": "sync_signal",  # Trỏ tới hàm sync_signal trong SyncConsumer
            "action": "SYNC_NOW",
            "payload": {"reason": "Dữ liệu học sinh vừa thay đổi"},
        },
    )

    # 2. Bắn qua Firebase FCM
    send_sync_ping_to_devices()


@receiver(post_save, sender=UserModel)
def trigger_sync_on_user_change(sender, instance, created, **kwargs):
    """
    Kích hoạt khi một User được thêm mới hoặc cập nhật (bao gồm cả Soft Delete).
    """
    # 🌟 BÍ QUYẾT SENIOR: Dùng transaction.on_commit
    # Nếu gửi FCM ngay lập tức, App Flutter có thể gọi API Pull về
    # TRƯỚC KHI database của Django kịp Commit xong dữ liệu.
    # on_commit đảm bảo data đã nằm an toàn trong DB rồi mới gọi App vào lấy.

    # Lấy danh sách các trường vừa bị thay đổi (kwargs có cung cấp)
    update_fields = kwargs.get("update_fields", frozenset())

    # Nếu Đã Update và CHỈ CÓ MỖI trường "last_login" bị đổi -> KỆ NÓ, KHÔNG SYNC!
    if not created and update_fields and update_fields == {"last_login"}:
        return

    transaction.on_commit(broadcast_hybrid_sync_signal)
