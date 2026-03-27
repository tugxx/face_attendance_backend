import os

from celery import Celery

# Báo cho Celery biết phải dùng setting của Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core_system.settings")

app = Celery("core_system")  # Tên project của bạn

# Namespace 'CELERY' nghĩa là mọi cấu hình trong settings.py phải bắt đầu bằng CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY")

# Tự động tìm các file tasks.py trong các app của bạn
app.autodiscover_tasks()
