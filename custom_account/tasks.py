import logging
import os

import pandas as pd
from celery import shared_task

from custom_account.services.user_service import register_students_bulk

logger = logging.getLogger(__name__)


@shared_task
def process_bulk_upload_task(file_path):
    """
    Task chạy ngầm: Đọc file Excel, xử lý và báo cáo.
    """
    try:
        logger.info(f"Bắt đầu xử lý ngầm file: {file_path}")

        # 1. Đọc file
        df = pd.read_excel(file_path, dtype=str)
        df = df.fillna("")
        rows_data = df.to_dict(orient="records")

        # 2. Xử lý hạng nặng (Hàm này giờ cứ chạy 5-10 phút cũng vô tư)
        report = register_students_bulk(rows_data)

        # 3. BẮN WEBSOCKET (Tương lai bạn có thể gửi thẳng report này qua Socket)
        # Giờ mình in ra log trước để test
        logger.info(
            f"Xử lý xong! Thành công: {report['success_count']}, Lỗi: {report['error_count']}"
        )

        # TODO: Gọi lại cái hàm broadcast_hybrid_sync_signal() của bạn ở đây

    except Exception as e:
        logger.error(f"Lỗi khi xử lý Background Task: {str(e)}")

    finally:
        # Quan trọng: Quét dọn chiến trường (Xóa file Excel tạm)
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info("Đã dọn dẹp file tạm.")
