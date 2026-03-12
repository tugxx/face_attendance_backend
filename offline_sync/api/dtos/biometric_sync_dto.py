from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any
from datetime import datetime, date
from uuid import UUID

class BiometricSyncOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    rfid_card_id: str | None = None
    face_vector_1: Any | None = None
    face_vector_2: Any | None = None
    is_active: bool