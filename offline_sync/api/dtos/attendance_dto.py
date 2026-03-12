from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from uuid import UUID
from datetime import datetime



# 1. Định nghĩa DTO cho từng dòng Log
class AttendanceLogItemInput(BaseModel):
    id: UUID
    user_id: UUID # Pydantic tự động ép kiểu string "uuid" sang UUID object, báo lỗi nếu sai format
    check_in_time: datetime # Tự động parse chuỗi ISO 8601 (có chữ Z hoặc +00:00) sang datetime
    method: str = "unknown"
    confidence_score: Optional[float] = None
    is_offline_log: bool = True


# 2. Định nghĩa DTO Tổng (Hứng cục JSON từ Flutter)
class OfflineAttendanceUploadInput(BaseModel):
    device_id: str = Field(..., max_length=255)
    
    # min_length=1: Tương đương đoạn code bắt lỗi "Logs list cannot be empty"
    # max_length=50000: Chống hacker spam payload khổng lồ làm sập server
    logs: List[AttendanceLogItemInput] = Field(..., min_length=1, max_length=50000)


class OfflineAttendanceUploadOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    inserted: int
    ignored: int
    synced_log_ids: List[UUID]