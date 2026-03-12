from typing import List, Optional, Any
from datetime import datetime, date
from uuid import UUID

from custom_account.models import UserModel



class ProfileSyncDomain:
    def __init__(self, display_name: Optional[str] = None, avatar_id: Optional[str] = None, dob: Optional[date] = None, gender: Optional[str] = None):
        self.display_name = display_name
        self.avatar_id = avatar_id
        self.dob = dob
        self.gender = gender

    @classmethod
    def from_model(cls, model) -> Optional["ProfileSyncDomain"]:
        if not model: return None
        return cls(
            display_name=model.display_name,
            avatar_id=model.avatar_id,
            dob=model.dob,
            gender=model.gender
        )