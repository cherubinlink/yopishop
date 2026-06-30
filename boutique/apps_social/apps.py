from django.apps import AppConfig


class AppsSocialConfig(AppConfig):
    name = 'apps_social'
    verbose_name = 'apllication social'



    def ready(self):
        import apps_social.signals
