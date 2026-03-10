from typing import List, Optional, Any
from datetime import datetime, date
from uuid import UUID

from custom_account.models import UserModel
from custom_account.domains.profile_domain import ProfileSyncDomain
from custom_account.domains.biometric_domain import BiometricSyncDomain
from custom_account.domains.user_sync_domain import UserSyncDomain



class SyncResultDomain:
    """Domain chứa kết quả trả về cuối cùng"""
    def __init__(self, server_time: datetime, data: List[UserSyncDomain]):
        self.server_time = server_time
        self.data = data
        self.total_changes = len(data)