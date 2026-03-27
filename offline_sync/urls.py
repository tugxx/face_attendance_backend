from django.urls import path

from offline_sync.api.views.attendance_view import (
    PushAttendanceBulkView,
    PushAttendanceImageView,
)
from offline_sync.api.views.sync_view import PullUsersSyncView

urlpatterns = [
    # 1. Luồng KÉO (Pull): Lấy dữ liệu từ Server về Tablet
    path("users/pull", PullUsersSyncView.as_view(), name="sync_pull_users"),
    # 2. Luồng ĐẨY (Push): Đẩy dữ liệu từ Tablet lên Server
    path(
        "attendance/push-bulk",
        PushAttendanceBulkView.as_view(),
        name="sync_push_attendance_bulk",
    ),
    path(
        "attendance/push-image/<uuid:log_id>",
        PushAttendanceImageView.as_view(),
        name="sync_push_attendance_image",
    ),
]
