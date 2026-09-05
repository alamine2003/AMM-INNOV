"""URL configuration: everything under /api/v1/, OpenAPI on /api/schema/ and /api/docs/."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path, re_path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import SimpleRouter

from apps.accounts.views import HealthView, LoginView, LogoutView, MeView, RefreshView, UserViewSet
from apps.alerts.views import AlertRuleViewSet, AlertViewSet
from apps.amm.views import AmmViewSet, RenewalViewSet
from apps.analytics.views import AfricaView, CountryView, ExportView, ProductCoverageView
from apps.catalog.views import CountryViewSet, ProductRangeViewSet, ProductViewSet
from apps.documents.views import DocumentViewSet
from apps.imports.views import ImportViewSet
from apps.notifications.views import NotificationViewSet

router = SimpleRouter(trailing_slash=False)
router.trailing_slash = "/?"  # accept both `/amms` and `/amms/`
router.register("users", UserViewSet, basename="user")
router.register("countries", CountryViewSet, basename="country")
router.register("ranges", ProductRangeViewSet, basename="range")
router.register("products", ProductViewSet, basename="product")
router.register("amms", AmmViewSet, basename="amm")
router.register("renewals", RenewalViewSet, basename="renewal")
router.register("documents", DocumentViewSet, basename="document")
router.register("alerts", AlertViewSet, basename="alert")
router.register("alert-rules", AlertRuleViewSet, basename="alert-rule")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("imports", ImportViewSet, basename="import")

api_v1 = [
    re_path(r"^auth/login/?$", LoginView.as_view(), name="auth-login"),
    re_path(r"^auth/refresh/?$", RefreshView.as_view(), name="auth-refresh"),
    re_path(r"^auth/logout/?$", LogoutView.as_view(), name="auth-logout"),
    re_path(r"^me/?$", MeView.as_view(), name="me"),
    re_path(r"^health/?$", HealthView.as_view(), name="health"),
    re_path(r"^analytics/africa/?$", AfricaView.as_view(), name="analytics-africa"),
    re_path(
        r"^analytics/country/(?P<iso2>[A-Za-z]{2})/?$",
        CountryView.as_view(),
        name="analytics-country",
    ),
    re_path(
        r"^analytics/product/(?P<pk>[0-9a-fA-F-]{36})/coverage/?$",
        ProductCoverageView.as_view(),
        name="analytics-product-coverage",
    ),
    re_path(r"^analytics/export/?$", ExportView.as_view(), name="analytics-export"),
    *router.urls,
]



def metrics(request):
    """Prometheus scrape endpoint; requires `Authorization: Bearer METRICS_TOKEN` when set."""
    from django_prometheus.exports import ExportToDjangoView

    token = settings.METRICS_TOKEN
    if token and request.headers.get("Authorization") != f"Bearer {token}":
        return HttpResponse(status=401)
    return ExportToDjangoView(request)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1, "api"), namespace="v1")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("metrics", metrics, name="prometheus-django-metrics"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
