from typing import List, Optional, Any
from datetime import datetime, date
from uuid import UUID

from custom_account.models import UserModel
from offline_sync.domains.profile_sync_domain import ProfileSyncDomain
from offline_sync.domains.biometric_sync_domain import BiometricSyncDomain



class UserSyncDomain:
    """Domain tổng hợp dữ liệu User cho việc Sync offline"""
    def __init__(
        self, id: UUID, username: str, email: str, role: str, is_active: bool,
        updated_on: datetime, profile: Optional[ProfileSyncDomain] = None, biometric: Optional[BiometricSyncDomain] = None
    ):
        self.id = id
        self.username = username
        self.email = email
        self.role = role
        self.is_active = is_active
        self.updated_on = updated_on
        self.profile = profile
        self.biometric = biometric

    @classmethod
    def from_model(cls, model: UserModel) -> "UserSyncDomain":
        # Hàm hasattr an toàn hơn để check OneToOneField xem có tồn tại không
        profile_model = model.profile if hasattr(model, 'profile') else None
        biometric_model = model.biometric if hasattr(model, 'biometric') else None

        return cls(
            id=model.id,
            username=model.username,
            email=model.email,
            role=model.role,
            is_active=model.is_active,
            updated_on=model.updated_on,
            profile=ProfileSyncDomain.from_model(profile_model),
            biometric=BiometricSyncDomain.from_model(biometric_model)
        )