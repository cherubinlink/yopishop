"""
URL configuration for yopishop project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # url apps
    path('apps_core/',include('apps_core.urls', namespace='apps_core')),
    path('apps_marketplace/', include('apps_marketplace.urls', namespace='apps_marketplace')),
    path('apps_encheres/', include('apps_encheres.urls', namespace='apps_encheres')),
    path('apps_social/', include('apps_social.urls', namespace='apps_social')),
    path('apps_remaining/', include('apps_remaining.urls', namespace='apps_remaining')),
    path('apps_contenu/', include('apps_contenu.urls', namespace='apps_contenu')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
