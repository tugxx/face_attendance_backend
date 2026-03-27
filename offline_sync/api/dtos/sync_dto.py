from datetime import datetime

from pydantic import BaseModel, ConfigDict

from offline_sync.api.dtos.user_sync_dto import UserSyncOutput


class SyncResultOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    total_changes: int
    server_time: datetime
    data: list[UserSyncOutput]
