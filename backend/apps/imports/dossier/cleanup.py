"""Reprise des dossiers pays rangés avant le 26/09/2026 : documents communs hors sujet.

Avant cette date, les documents posés à la racine d'un dossier pays (« AMM groupée 23 DEC
2023 », « AMM PALUCARE 20 mg ») étaient rangés dans la fiche de chacun de ses produits, qu'ils
le concernent ou non. Chaque document commun est relu avec les règles actuelles : s'il ne
concerne pas le produit de la fiche, il est archivé (jamais supprimé) et ses points à vérifier
sont fermés. Un document qui concerne le produit reste en place.
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Country, Product

from ..models import DossierFile, DossierImport, DossierReviewPoint
from .preview import COMMON_FOLDER, _focus_on_product
from .recognition import recognize_file

logger = logging.getLogger(__name__)


def detach_unrelated_common_documents(*, dry_run: bool = False) -> dict:
    report = {"examined": 0, "archived": 0, "kept": 0, "points_closed": 0, "amms": 0}
    sources = (
        DossierFile.objects.filter(
            relative_path__contains=f"/{COMMON_FOLDER}/",
            document__isnull=False,
            document__archived_at__isnull=True,
            batch__status=DossierImport.Status.APPLIED,
            batch__amm__isnull=False,
        )
        .select_related("document", "batch__amm__product", "batch__amm__country")
        .order_by("batch__created_at", "relative_path")
    )
    if not sources.exists():
        return report
    countries = list(Country.objects.all())
    products = list(Product.objects.prefetch_related("aliases").all())
    touched = set()
    for source in sources.iterator(chunk_size=200):
        report["examined"] += 1
        amm, document = source.batch.amm, source.document
        if document.amm_id != amm.pk:
            continue
        row = recognize_file(source, countries, products, source.batch.root_name)
        _, _, ignored = _focus_on_product(
            [source], [row], amm.product, products, countries, amm.country,
            source.batch.root_name, [],
        )  # fmt: skip
        if not ignored:
            report["kept"] += 1
            continue
        # Le même document peut aussi être la preuve d'un fichier du dossier du produit lui-même.
        if (
            DossierFile.objects.filter(document=document)
            .exclude(relative_path__contains=f"/{COMMON_FOLDER}/")
            .exists()
        ):
            report["kept"] += 1
            continue
        report["archived"] += 1
        touched.add(amm.pk)
        logger.warning(
            "Document commun hors sujet archivé : %s (fiche %s)", source.relative_path, amm.pk
        )
        if dry_run:
            continue
        with transaction.atomic():
            document.archived_at = timezone.now()
            document._change_reason = (
                f"Document commun du dossier pays sans rapport avec {amm.product.name}"
            )
            document.save(update_fields=["archived_at"])
            report["points_closed"] += DossierReviewPoint.objects.filter(
                proof_file__in=DossierFile.objects.filter(document=document),
                status=DossierReviewPoint.Status.OPEN,
            ).update(status=DossierReviewPoint.Status.IGNORED, resolved_at=timezone.now())
    report["amms"] = len(touched)
    if not dry_run and touched:
        from apps.amm.models import MarketingAuthorization
        from apps.amm.services.status import recompute_quietly

        for amm in MarketingAuthorization.objects.filter(pk__in=touched):
            recompute_quietly(amm)
    return report
