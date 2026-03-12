from django.db.models import Q
from django.utils import timezone
from dateutil.parser import parse as parse_datetime

from custom_account.models import UserModel
from offline_sync.domains.sync_result_domain import SyncResultDomain
from offline_sync.domains.user_sync_domain import UserSyncDomain



def get_incremental_sync_queryset(last_sync_str: str = None):
    # 1. Query DB
    users_query = UserModel.objects.select_related('profile', 'biometric').only(
        # Cột của bảng UserModel
        'id', 'username', 'email', 'role', 'is_active', 'updated_on',
        # Cột của bảng Profile
        'profile__display_name', 'profile__avatar_id', 'profile__date_of_birth', 'profile__gender', 'profile__updated_at',
        # Cột của bảng Biometric
        'biometric__rfid_card_id', 'biometric__face_embeddings', 'biometric__is_active', 'biometric__updated_at'
    )

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

    return users_query