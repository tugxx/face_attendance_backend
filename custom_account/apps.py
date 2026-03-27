from django.apps import AppConfig


class CustomAccountConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "custom_account"

    def ready(self):
        # Thêm noqa: F401 để tắt cảnh báo "Unused import" của Ruff/Flake8
        import custom_account.signals  # noqa: F401
