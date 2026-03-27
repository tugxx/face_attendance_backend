from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# 1. Định nghĩa DTO cho từng dòng Log
class AttendanceLogItemInput(BaseModel):
    id: UUID
    user_id: str
    timestamp: datetime
    confidence: float | None = None
    liveness_score: float | None = None
    is_offline_log: bool = True


# 2. Định nghĩa DTO Tổng (Hứng cục JSON từ Flutter)
class OfflineAttendanceUploadInput(BaseModel):
    device_id: str = Field(..., max_length=255)

    # min_length=1: Tương đương đoạn code bắt lỗi "Logs list cannot be empty"
    # max_length=50000: Chống hacker spam payload khổng lồ làm sập server
    logs: list[AttendanceLogItemInput] = Field(..., min_length=1, max_length=50000)


class OfflineAttendanceUploadOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    inserted: int
    ignored: int
    synced_log_ids: list[UUID]
