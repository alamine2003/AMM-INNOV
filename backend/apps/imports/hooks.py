"""Ce que l'app Imports déclare au socle.

- rattrapage : analyses de dossiers et imports restés en plan, dossiers à relire, synchro AMM
  GHPL en retard ;
- démarrage du worker : reprise des analyses coupées par un redémarrage (Render gratuit) ;
- travail en cours : maintien en éveil tant qu'un import ou une analyse attend ;
- invariants : tâches bloquées, fichiers référencés présents dans le stockage ;
- fiche AMM : corrections des dossiers dans l'historique, points à vérifier dans la liste.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.amm.extensions import HISTORY_SOURCES, LIST_ANNOTATIONS
from apps.core.integrity import ERROR, WARNING, Check
from apps.core.registry import INTEGRITY, PENDING_WORK, RECOVERY, WORKER_START

logger = logging.getLogger(__name__)

PENDING_AFTER = timedelta(minutes=5)
IMPORT_RUNNING_MAX = timedelta(minutes=45)
DOSSIER_RUNNING_MAX = timedelta(minutes=25)  # soft_time_limit de l'analyse : 20 min
GHPL_SYNC_EVERY = timedelta(minutes=65)
REREAD_PER_RUN = 10

# Une analyse qui fait tomber le serveur ne boucle pas indéfiniment.
MAX_ATTEMPTS = 3
GAVE_UP = (
    "L'analyse a été interrompue {attempts} fois (redémarrage du serveur, mémoire). "
    "Relancez-la, ou déposez ce produit seul."
)


# --- Rattrapage (toutes les 5 minutes) ---------------------------------------------------


@RECOVERY.register
def recover_dossiers(now) -> dict[str, int]:
    """Analyses coupées en route : marquées en échec ; demandes jamais lancées : republiées."""
    from .models import DossierImport
    from .tasks import analyze_dossier

    interrupted = DossierImport.objects.filter(
        status=DossierImport.Status.RUNNING, started_at__lt=now - DOSSIER_RUNNING_MAX
    ).update(
        status=DossierImport.Status.FAILED,
        finished_at=now,
        error="L'analyse a été interrompue (redémarrage du service). Relancez l'analyse.",
    )
    republished = 0
    pending = DossierImport.objects.filter(
        status=DossierImport.Status.PENDING, created_at__lt=now - PENDING_AFTER
    )
    for pk in pending.values_list("pk", flat=True)[:100]:
        analyze_dossier.delay(str(pk))
        republished += 1
    return {
        "dossiers_interrupted": interrupted,
        "dossiers_republished": republished,
        "dossiers_reread": reread_stale_dossiers(),
    }


def reread_stale_dossiers() -> int:
    """Relit les dossiers restés « prêt à ranger » ou « question » : rien à cliquer.

    - lus avec d'anciennes règles (version d'aperçu inférieure) : relus avec les règles
      actuelles, puis rangés d'office si l'AMM est identifiée (dossiers du 22/09/2026 restés
      « À ranger », MAGLIFE en « Question » à cause d'un pays mal lu) ;
    - « prêt à ranger » dont le rangement automatique a échoué (coupure, stockage) : nouvel
      essai, au plus MAX_ATTEMPTS fois.
    Quelques dossiers par passage : le worker unique de Render reste disponible.
    """
    from .dossier.preview import PREVIEW_VERSION
    from .models import DossierImport
    from .tasks import analyze_dossier

    if not getattr(settings, "DOSSIER_AUTO_APPLY", False):
        return 0
    waiting = DossierImport.objects.filter(
        status__in=[DossierImport.Status.READY, DossierImport.Status.QUESTION],
        created_by__is_active=True,
        attempts__lt=MAX_ATTEMPTS,
    ).order_by("created_at")
    reread = 0
    for batch in waiting.only("pk", "status", "preview")[:200]:
        version = (batch.preview or {}).get("version", 0)
        stale = version < PREVIEW_VERSION
        retry = batch.status == DossierImport.Status.READY
        if not (stale or retry):
            continue
        if DossierImport.objects.filter(pk=batch.pk, status=batch.status).update(
            status=DossierImport.Status.PENDING, preview_token=""
        ):
            analyze_dossier.delay(str(batch.pk))
            reread += 1
        if reread >= REREAD_PER_RUN:
            break
    return reread


@RECOVERY.register
def recover_imports(now) -> dict[str, int]:
    """Imports Excel jamais lancés : republiés ; coupés en route : marqués en échec."""
    from .models import ImportBatch
    from .tasks import run_import

    republished = 0
    imports = ImportBatch.objects.filter(
        status=ImportBatch.Status.PENDING, created_at__lt=now - PENDING_AFTER
    )
    for pk in imports.values_list("pk", flat=True)[:20]:
        run_import.delay(str(pk))  # prise en charge exclusive dans la tâche : pas de doublon
        republished += 1

    # Import coupé en route (redémarrage du service, mémoire) : il resterait « en cours » pour
    # toujours. Rien n'a été écrit (transaction annulée) : on le marque en échec, à relancer.
    limit = now - IMPORT_RUNNING_MAX
    stuck = ImportBatch.objects.filter(status=ImportBatch.Status.RUNNING).filter(
        Q(started_at__lt=limit) | Q(started_at__isnull=True, created_at__lt=limit)
    )
    failed = stuck.update(
        status=ImportBatch.Status.FAILED,
        finished_at=now,
        summary={"error": "Import interrompu (redémarrage du service) : relancez-le."},
    )
    return {"imports_republished": republished, "imports_failed": failed}


@RECOVERY.register
def recover_ghpl(now) -> dict[str, int]:
    return {"ghpl_sync": recover_ghpl_sync(now)}


def recover_ghpl_sync(now) -> int:
    """Synchronisation AMM GHPL en retard (service endormi à H+20 sur Render gratuit) : relancée
    dans les cinq minutes du réveil au lieu d'attendre l'heure suivante."""
    from .ghpl.webdav import Nextcloud
    from .models import GhplSyncRun
    from .tasks import sync_ghpl

    if not settings.GHPL_SYNC_ENABLED or Nextcloud.from_settings() is None:
        return 0
    last = GhplSyncRun.objects.order_by("-started_at").values_list("started_at", flat=True).first()
    if last is not None and last > now - GHPL_SYNC_EVERY:
        return 0
    sync_ghpl.delay()
    return 1


# --- Démarrage du worker et maintien en éveil ---------------------------------------------


@WORKER_START.register
def resume_interrupted_analyses() -> dict:
    """Analyses « en cours » au démarrage du seul worker : reprises, ou abandonnées après
    MAX_ATTEMPTS essais (un dossier qui fait tomber le serveur ne boucle pas indéfiniment)."""
    from .models import DossierImport
    from .tasks import analyze_dossier

    running = DossierImport.objects.filter(status=DossierImport.Status.RUNNING)
    failed = running.filter(attempts__gte=MAX_ATTEMPTS)
    abandoned = 0
    for batch in failed:
        abandoned += DossierImport.objects.filter(
            pk=batch.pk, status=DossierImport.Status.RUNNING
        ).update(
            status=DossierImport.Status.FAILED,
            finished_at=timezone.now(),
            error=GAVE_UP.format(attempts=batch.attempts),
        )
    resumed = []
    for pk in running.filter(attempts__lt=MAX_ATTEMPTS).values_list("pk", flat=True):
        if DossierImport.objects.filter(pk=pk, status=DossierImport.Status.RUNNING).update(
            status=DossierImport.Status.PENDING, started_at=None
        ):
            resumed.append(str(pk))
    for pk in resumed:
        analyze_dossier.delay(pk)
    report = {"resumed": len(resumed), "abandoned": abandoned}
    if resumed or abandoned:
        logger.warning("Analyses interrompues au démarrage du worker : %s", report)
    return report


@PENDING_WORK.register
def has_pending_imports() -> bool:
    from .models import DossierImport, ImportBatch

    busy = [DossierImport.Status.PENDING, DossierImport.Status.RUNNING]
    return (
        DossierImport.objects.filter(status__in=busy).exists()
        or ImportBatch.objects.filter(
            status__in=[ImportBatch.Status.PENDING, ImportBatch.Status.RUNNING]
        ).exists()
    )


# --- Invariants (check_integrity) ---------------------------------------------------------


@INTEGRITY.register
def check_stuck_jobs(options) -> Check:
    from .models import DossierImport, ImportBatch

    minutes = options.stuck_minutes
    check = Check(
        "no_stuck_job",
        ERROR,
        f"Un import ou une analyse de dossier est-il bloqué depuis plus de {minutes} min ?",
    )
    limit = timezone.now() - timedelta(minutes=minutes)
    for model in (ImportBatch, DossierImport):
        stuck = model.objects.filter(
            Q(status=model.Status.PENDING) | Q(status=model.Status.RUNNING),
            created_at__lt=limit,
        )
        if options.since:
            stuck = stuck.filter(created_at__gte=options.since)
        for pk, status in stuck.values_list("pk", "status"):
            check.add(f"{model.__name__} {pk}: {status}")
    return check


@INTEGRITY.register
def check_storage(options) -> list[Check]:
    """Fichiers des scans et des dossiers déposés : présents, et sans fichier orphelin."""
    if options.skip_storage:
        return []
    from django.core.files.storage import default_storage

    from apps.documents.models import Document

    from .models import DossierFile

    missing = Check(
        "referenced_file_exists",
        ERROR,
        "Chaque fichier référencé en base existe-t-il dans le stockage ?",
    )
    orphans = Check(
        "orphan_blobs",
        WARNING,
        "Le stockage contient-il des fichiers qu'aucune ligne ne référence (fuite) ?",
    )
    referenced = set()
    for model in (Document, DossierFile):
        for pk, name in model.objects.values_list("pk", "file"):
            if not name:
                continue
            referenced.add(name)
            if not default_storage.exists(name):
                missing.add(f"{model.__name__} {pk}: {name}")
    # Les scans des éléments mis à la corbeille restent au stockage : ce ne sont pas des fuites.
    from apps.core.trash import trashed_files

    referenced |= trashed_files()
    for name in _list_blobs(default_storage, "documents/"):
        if name not in referenced:
            orphans.add(name)
    return [missing, orphans]


def _list_blobs(storage, prefix: str):
    """Tous les fichiers sous `prefix`, en local comme sur S3."""
    bucket = getattr(storage, "bucket", None)
    if bucket is not None:  # S3Storage (django-storages)
        location = getattr(storage, "location", "") or ""
        base = f"{location.rstrip('/')}/" if location else ""
        for obj in bucket.objects.filter(Prefix=base + prefix):
            yield obj.key[len(base) :]
        return
    try:
        directories, files = storage.listdir(prefix)
    except (FileNotFoundError, NotImplementedError):
        return
    for name in files:
        yield f"{prefix}{name}"
    for directory in directories:
        yield from _list_blobs(storage, f"{prefix}{directory}/")


# --- Fiche AMM : historique et liste --------------------------------------------------------


@HISTORY_SOURCES.register
def dossier_corrections(amm) -> list[dict]:
    """Valeurs renseignées ou corrigées par l'import d'un dossier, avec leur preuve."""
    from apps.amm.history import label_value

    from .models import DossierChange

    entries: list[dict] = []
    for change in DossierChange.objects.filter(amm=amm).select_related("user", "proof_file"):
        entries.append(
            {
                "date": change.created_at,
                "user_email": change.user.email if change.user else None,
                # Une valeur absente OU vide est renseignée, pas corrigée : seul un
                # désaccord avec une donnée existante est une correction.
                "type": "documentary_correction"
                if change.old_value not in (None, "")
                else "documentary_creation",
                "model": "renewal" if change.renewal_id else "amm",
                "object_id": str(change.renewal_id or amm.pk),
                "changes": [
                    {
                        "field": change.field,
                        "old": label_value(change.old_value),
                        "new": label_value(change.new_value),
                    }
                ],
                "source": change.source,
                "reason": change.reason,
                "confidence": change.confidence,
                "batch_id": str(change.batch_id),
                "proof_file_id": str(change.proof_file_id),
                "document_id": str(change.proof_file.document_id)
                if change.proof_file.document_id
                else None,
            }
        )
    return entries


@LIST_ANNOTATIONS.register
def open_review_points() -> dict:
    """Points à vérifier plus tard laissés par l'import de dossiers (badge de la liste)."""
    from django.db.models import Count, IntegerField, OuterRef, Subquery
    from django.db.models.functions import Coalesce

    from .models import DossierReviewPoint

    open_points = (
        DossierReviewPoint.objects.filter(amm=OuterRef("pk"), status="OPEN")
        .order_by()
        .values("amm")
        .annotate(total=Count("pk"))
        .values("total")
    )
    return {
        "open_review_points": Coalesce(Subquery(open_points, output_field=IntegerField()), 0)
    }
