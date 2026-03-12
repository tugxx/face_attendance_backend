from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any
from datetime import datetime, date
from uuid import UUID

from custom_account.api.dtos.user_dto import UserSyncOutput



class SyncResultOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    total_changes: int
    server_time: datetime
    data: List[UserSyncOutput]