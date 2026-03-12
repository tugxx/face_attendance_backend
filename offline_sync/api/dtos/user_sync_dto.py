from uuid import UUID
from pydantic import BaseModel, ConfigDict
from datetime import datetime

from offline_sync.api.dtos.biometric_sync_dto import BiometricSyncOutput
from offline_sync.api.dtos.profile_sync_dto import ProfileSyncOutput



class UserSyncOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID | str
    username: str
    email: str
    role: str
    is_active: bool
    updated_on: datetime
    profile: ProfileSyncOutput | None = None
    biometric: BiometricSyncOutput | None = None