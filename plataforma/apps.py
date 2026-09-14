from django.apps import AppConfig


class PlataformaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'plataforma'
    verbose_name = 'Plataforma'

    def ready(self):
        import plataforma.signals  # noqa: F401
