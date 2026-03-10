from django.db.models import Q
from django.utils import timezone
from dateutil.parser import parse as parse_datetime

from custom_account.models import UserModel
from custom_account.domains.sync_result_domain import SyncResultDomain
from custom_account.domains.user_sync_domain import UserSyncDomain



def get_incremental_sync_data(last_sync_str: str = None) -> SyncResultDomain:
    # 1. Query DB
    users_query = UserModel.objects.select_related('profile', 'biometric').all()

    if last_sync_str:
        try:
            last_sync = parse_datetime(last_sync_str)
            users_query = users_query.filter(
                Q(updated_on__gt=last_sync) |
                Q(profile__updated_at__gt=last_sync) |
                Q(biometric__updated_at__gt=last_sync)
            ).distinct()
        except ValueError:
            raise ValueError("Invalid last_sync datetime format.")

    # 2. Chuyển đổi toàn bộ QuerySet sang Domain Objects
    domain_users = [UserSyncDomain.from_model(user) for user in users_query]
    
    # 3. Trả về Domain Result tổng
    return SyncResultDomain(
        server_time=timezone.now(),
        data=domain_users
    )