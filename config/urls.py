"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
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

import re

from django.conf import settings
from django.contrib import admin
from django.core.exceptions import SuspiciousFileOperation
from django.http import Http404
from django.urls import include, path, re_path
from django.views.static import serve


def serve_media(request, path):
    try:
        return serve(request, path, document_root=settings.MEDIA_ROOT)
    except SuspiciousFileOperation as error:
        raise Http404("Media tidak ditemukan.") from error


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.landing.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("design-system/", include("apps.designsystem.urls")),
    path("catalog/", include("apps.catalog.urls")),
    path("map/", include("apps.map.urls")),
    path("orders/", include("apps.orders.urls")),
]

if not settings.PRODUCTION:
    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]

urlpatterns += [
    re_path(
        rf"^{re.escape(settings.MEDIA_URL.lstrip('/'))}(?P<path>.*)$",
        serve_media,
        name="media",
    )
]
