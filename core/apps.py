from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Gestión de la guardería"

    def ready(self):
        from . import roles  # noqa: F401
