from typing import List
from datetime import datetime

from offline_sync.domains.user_sync_domain import UserSyncDomain



class SyncResultDomain:
    """Domain chứa kết quả trả về cuối cùng"""
    def __init__(self, server_time: datetime, data: List[UserSyncDomain]):
        self.server_time = server_time
        self.data = data
        self.total_changes = len(data)