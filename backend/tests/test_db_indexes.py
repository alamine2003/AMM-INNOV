"""Index de la base (1.1.8) : créés par les migrations et choisis par Postgres.

Les tables de test sont minuscules : Postgres y préfère toujours la lecture complète. On
désactive donc les lectures séquentielles le temps d'un `EXPLAIN`, pour vérifier que l'index
*peut* servir la requête (même expression, même condition). En production, c'est le volume qui
fait le choix.
"""

import pytest
from django.db import connection, transaction

from apps.alerts.models import Alert
from apps.amm.models import MarketingAuthorization, Renewal
from apps.catalog.models import Product, ProductAlias
from apps.documents.models import Document
from apps.notifications.models import Notification

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="index propres à Postgres"),
]

INDEXES = {
    "product_name_trgm": "catalog_product",
    "alias_raw_name_trgm": "catalog_productalias",
    "amm_number_trgm": "amm_marketingauthorization",
    "renewal_number_trgm": "amm_renewal",
    "renewal_workflow_idx": "amm_renewal",
    "doc_current_scan_idx": "documents_document",
    "alert_status_due_idx": "alerts_alert",
    "notif_user_recent_idx": "notifications_notification",
    "notif_user_unread_idx": "notifications_notification",
}


def test_migrations_create_every_index():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname, tablename, indexdef FROM pg_indexes WHERE indexname = ANY(%s)",
            [list(INDEXES)],
        )
        found = {name: (table, definition) for name, table, definition in cursor.fetchall()}
    assert {name: table for name, (table, _) in found.items()} == INDEXES
    assert "gin_trgm_ops" in found["product_name_trgm"][1]
    assert "upper" in found["product_name_trgm"][1].lower()


def test_trigram_extension_enabled():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
        assert cursor.fetchone() is not None


def _plan(queryset) -> str:
    """Plan de la requête, sans le tri par défaut des modèles (un autre index le servirait)."""
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan = off")
        return queryset.explain()


@pytest.mark.parametrize(
    ("index", "queryset"),
    [
        # `?search=` de l'API : `icontains`, soit UPPER(col::text) LIKE UPPER('%…%').
        ("product_name_trgm", lambda: Product.objects.filter(name__icontains="omep").order_by()),
        (
            "alias_raw_name_trgm",
            lambda: ProductAlias.objects.filter(raw_name__icontains="b/28").order_by(),
        ),
        (
            "amm_number_trgm",
            lambda: MarketingAuthorization.objects.filter(
                original_number__icontains="12/34"
            ).order_by(),
        ),
        (
            "renewal_number_trgm",
            lambda: Renewal.objects.filter(number__icontains="2026").order_by(),
        ),
        (
            "renewal_workflow_idx",
            lambda: Renewal.objects.filter(
                workflow_status__in=Renewal.PENDING_STATUSES
            ).order_by(),
        ),
        (
            "doc_current_scan_idx",
            lambda: Document.objects.filter(
                amm_id="00000000-0000-0000-0000-000000000000",
                kind=Document.Kind.AMM,
                is_current=True,
                archived_at__isnull=True,
            ).order_by(),  # comme le `Exists` de la liste AMM : sans tri
        ),
        (
            "alert_status_due_idx",
            lambda: Alert.objects.filter(status=Alert.Status.OPEN).order_by("due_date"),
        ),
        (
            "notif_user_unread_idx",
            lambda: Notification.objects.filter(user_id=1, read_at__isnull=True).order_by(),
        ),
    ],
)
def test_query_can_use_index(index, queryset):
    assert index in _plan(queryset())
