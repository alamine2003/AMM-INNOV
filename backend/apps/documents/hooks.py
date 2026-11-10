"""Ce que l'app Documents déclare au socle : rattrapage des aperçus, invariants, et les
bibliothèques de documents d'un pays et d'un produit (actions du catalogue)."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, F

from apps.catalog.extensions import COUNTRY_DOCUMENTS, PRODUCT_DOCUMENTS
from apps.core.integrity import ERROR, Check
from apps.core.registry import INTEGRITY, RECOVERY

PREVIEW_AFTER = timedelta(minutes=10)


@RECOVERY.register
def recover_previews(now) -> dict[str, int]:
    """PDF sans aperçu (nombre de pages) : la génération est republiée."""
    from .models import Document
    from .tasks import generate_document_preview

    previews = Document.objects.filter(
        page_count__isnull=True,
        content_type="application/pdf",
        uploaded_at__lt=now - PREVIEW_AFTER,
        uploaded_at__gte=now - timedelta(days=1),
    )
    count = 0
    for pk in previews.values_list("pk", flat=True)[:500]:
        generate_document_preview.delay(str(pk))
        count += 1
    return {"previews": count}


@INTEGRITY.register
def check_document_versions(options) -> Check:
    from .models import Document

    check = Check(
        "single_current_version",
        ERROR,
        "Un document remplacé n'est-il plus courant, "
        "et une version n'a-t-elle qu'un seul successeur ?",
    )
    stale = Document.objects.filter(
        is_current=True, archived_at__isnull=True, replaced_by__isnull=False
    ).distinct()
    for document in stale.values_list("pk", flat=True):
        check.add(f"document {document}: encore courant alors qu'une version le remplace")
    forks = (
        Document.objects.filter(replaces__isnull=False, archived_at__isnull=True)
        .order_by()  # le tri imposé par le manager entrerait dans le GROUP BY
        .values("replaces_id")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )
    for row in forks:
        check.add(f"document {row['replaces_id']}: {row['n']} successeurs actifs")
    return check


@INTEGRITY.register
def check_document_links(options) -> Check:
    from .models import Document

    check = Check(
        "document_renewal_same_amm",
        ERROR,
        "Un scan rattaché à un renouvellement appartient-il à la même AMM ?",
    )
    crossed = Document.objects.filter(renewal__isnull=False).exclude(renewal__amm_id=F("amm_id"))
    for pk in crossed.values_list("pk", flat=True):
        check.add(f"document {pk}")
    return check


@COUNTRY_DOCUMENTS.register
def country_documents(request, country):
    from .views import country_documents

    return country_documents(request, country)


@PRODUCT_DOCUMENTS.register
def product_documents(request, product):
    from .views import product_documents

    return product_documents(request, product)
