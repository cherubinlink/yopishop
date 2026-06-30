from django.apps import AppConfig


class AppsMarketplaceConfig(AppConfig):
    name = 'apps_marketplace'
    verbose_name = 'marketplace'



    def ready(self):
        import apps_marketplace.signals
