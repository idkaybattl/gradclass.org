from django.apps import AppConfig


class AbiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dashboard"

    def ready(self):
        from . import signals  # noqa
