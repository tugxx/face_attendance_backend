from django.apps import AppConfig


class CustomAccountConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "custom_account"

    def ready(self):
        # Import file signals khi App khởi động
        pass
