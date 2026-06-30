from django.apps import AppConfig


class AppsCoreConfig(AppConfig):
    name = 'apps_core'
    verbose_name = 'applictions utilisateur'


    def ready(self):
        import apps_core.signals
