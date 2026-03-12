from typing import List, Optional, Any
from datetime import datetime, date
from uuid import UUID
from custom_account.models import UserModel

class BiometricSyncDomain:
    def __init__(self, rfid_card_id: Optional[str] = None, face_vector_1: Any = None, face_vector_2: Any = None, is_active: bool = True):
        self.rfid_card_id = rfid_card_id
        self.face_vector_1 = face_vector_1
        self.face_vector_2 = face_vector_2
        self.is_active = is_active

    @classmethod
    def from_model(cls, model) -> Optional["BiometricSyncDomain"]:
        if not model: return None
        return cls(
            rfid_card_id=model.rfid_card_id,
            face_vector_1=model.face_vector_1,
            face_vector_2=model.face_vector_2,
            is_active=model.is_active
        )