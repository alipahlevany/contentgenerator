from django.contrib import admin
from django.urls import include, path

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAdminUser


urlpatterns = [
    # Django Admin
    path(
        "admin/",
        admin.site.urls,
    ),

    # API v1
    path(
        "api/v1/",
        include("contents.urls"),
    ),

    # OpenAPI Schema (Admin Only)
    path(
        "api/schema/",
        SpectacularAPIView.as_view(
            authentication_classes=[
                SessionAuthentication,
            ],
            permission_classes=[
                IsAdminUser,
            ],
        ),
        name="schema",
    ),

    # Swagger UI (Admin Only)
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="schema",
            authentication_classes=[
                SessionAuthentication,
            ],
            permission_classes=[
                IsAdminUser,
            ],
        ),
        name="swagger-ui",
    ),
]