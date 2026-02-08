from django.apps import AppConfig


class OrdersConfig(AppConfig):
    name = 'orders'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        """
        Import signals when app is ready.
        This ensures signal handlers are registered.
        """
        import orders.signals  # noqa: F401
