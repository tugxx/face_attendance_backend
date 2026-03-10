from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any
from datetime import datetime, date
from uuid import UUID



class ProfileSyncOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    display_name: str | None = None
    avatar_id: str | None = None
    dob: date | None = None
    gender: str | None = None