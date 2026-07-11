from django.contrib import admin
from django.urls import include, path

from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAdminUser

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)


urlpatterns = [
    path(
        "admin/",
        admin.site.urls,
    ),

    path(
        "api/v1/",
        include("contents.urls"),
    ),

    path(
        "api/schema/",
        SpectacularAPIView.as_view(
            authentication_classes=[SessionAuthentication],
            permission_classes=[IsAdminUser],
        ),
        name="schema",
    ),

    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema",
            authentication_classes=[SessionAuthentication],
            permission_classes=[IsAdminUser],
        ),
        name="swagger-ui",
    ),
]