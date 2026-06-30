from django.apps import AppConfig


class AppsEncheresConfig(AppConfig):
    name = 'apps_encheres'
    verbose_name = 'application encheres'


    def ready(self):
        import apps_encheres.signals
