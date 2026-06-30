from django.apps import AppConfig


class AppsContenuConfig(AppConfig):
    name = 'apps_contenu'
    verbose_name = 'application contenu'


    def ready(self):
        import apps_contenu.signals
