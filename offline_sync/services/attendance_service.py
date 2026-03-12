from typing import List, Dict, Any

from custom_account.models import UserModel
from offline_sync.models import AttendanceLog 
from offline_sync.api.dtos.attendance_dto import OfflineAttendanceUploadInput



def process_offline_attendance_logs(input_dto: OfflineAttendanceUploadInput) -> Dict[str, int]:
    """
    Nhận mảng DTO logs, validate tồn tại và insert hàng loạt vào DB.
    Trả về thống kê số lượng bản ghi đã xử lý.
    """
    if not input_dto.logs:
        return {"inserted": 0, "ignored": 0}

    # ---------------------------------------------------------
    # 1. BULK VALIDATION (Giải quyết N+1 Query)
    # ---------------------------------------------------------
    # Lấy ra một set (tập hợp) các user_id duy nhất từ cục JSON
    incoming_user_ids = {log['user_id'] for log in input_dto.logs}
    
    # Chỉ gọi đúng 1 câu SQL SELECT để lấy các ID hợp lệ đang có trong DB
    # values_list('id', flat=True) giúp trả về mảng ID thuần túy, tốn cực ít RAM
    valid_user_ids = set(
        UserModel.objects.filter(id__in=incoming_user_ids, is_active=True)
        .values_list('id', flat=True)
    )

    # ---------------------------------------------------------
    # 2. PREPARE MODEL INSTANCES (Gom data trên RAM)
    # ---------------------------------------------------------
    logs_to_insert = []
    ignored_count = 0

    for log in input_dto.logs:
        # So sánh UUID trực tiếp, không tốn tài nguyên convert sang chuỗi (String)
        if log.user_id not in valid_user_ids:
            ignored_count += 1
            continue

        # KHÔNG TẠO INSTANCE USER. Gán thẳng khóa ngoại qua thuộc tính `user_id`
        # Đây là trick giúp tiết kiệm thêm hàng chục mili-giây
        attendance_log = AttendanceLog(
            id=log.id,
            user_id=log.user_id, 
            device_id=input_dto.device_id,
            check_in_time=log.check_in_time,
            method=log.method,
            confidence_score=log.confidence_score,
            is_offline_log=log.is_offline_log
        )
        logs_to_insert.append(attendance_log)

    # ---------------------------------------------------------
    # 3. BULK CREATE (Chạy 1 câu SQL INSERT duy nhất)
    # ---------------------------------------------------------
    inserted_count = 0
    if logs_to_insert:
        # ignore_conflicts=True: 
        # Nếu DB đã có log này rồi (nhờ set unique_together = ['user', 'check_in_time'] ở Model), 
        # PostgreSQL/SQLite/MySQL sẽ bỏ qua bản ghi đó, không báo lỗi IntegrityError.
        created_logs = AttendanceLog.objects.bulk_create(
            logs_to_insert,
            batch_size=500, # Nếu có 2000 log, tự cắt ra 4 gói 500 để không làm tràn bộ đệm SQL
            ignore_conflicts=True 
        )
        inserted_count = len(created_logs)

    return {
        "inserted": inserted_count,
        "invalid_users_ignored": ignored_count
    }