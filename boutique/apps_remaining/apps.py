from django.apps import AppConfig


class AppsRemainingConfig(AppConfig):
    name = 'apps_remaining'
    verbose_name = 'application remaining'



    def ready(self):
        import apps_remaining.signals
