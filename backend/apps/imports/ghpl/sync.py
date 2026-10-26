"""Synchronisation horaire d'AMM GH avec le classement AMM GHPL (Nextcloud).

Le classement est tenu à jour chaque heure par sa propre tâche planifiée, qui réécrit le
registre `0_REGISTRE AMM GHPL.xlsx`. À chaque passage (Celery beat, H+20, ou « Synchroniser
maintenant ») :

1. Le registre est relu s'il a changé (ETag WebDAV). Garde-fou : un registre qui perd plus de
   10 % des pièces du passage précédent n'est pas appliqué (registre en cours d'écriture).
2. Seules les présentations dont le classement a changé (empreintes du passage précédent) sont
   réimportées, par les imports existants : registre GHPL, puis scans classés. Les scans
   complètent et créent ; ils ne corrigent jamais une date déjà sur la fiche (une correction
   faite dans AMM GH n'est pas réécrite) : un écart devient « à vérifier » dans le rapport.
3. Chaque pièce principale devient un document de sa fiche :
   - déjà envoyée (même nom sur la fiche, ou même empreinte) : rattachée sans téléchargement ;
   - reclassée dans le classement (autre période, type, date, voire autre AMM) : le document
     suit automatiquement ;
   - nouvelle : téléchargée (GHPL_SYNC_MAX_FILES par passage, la suite au suivant) ;
   - Word, trop lourde ou illisible : laissée de côté et listée ;
   - retirée du classement : listée, le document est conservé (jamais de suppression).

Lecture seule côté Nextcloud (PROPFIND, GET).
"""

from __future__ import annotations

import hashlib
import io
import logging
from collections import Counter
from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.amm.models import MarketingAuthorization, Renewal
from apps.documents.models import Document

from ..models import GhplSyncedFile, GhplSyncRun, ImportBatch, ImportRow
from .source import fingerprints, group_key, manifest_rows, record_key
from .webdav import Nextcloud, NextcloudError, TooLarge

logger = logging.getLogger(__name__)

REASON = "Synchronisation AMM GHPL"
MIN_COVERAGE = 0.9  # pièces du registre / pièces du passage précédent
MAX_ATTEMPTS = 5
ACCEPTED = {".pdf", ".jpg", ".jpeg", ".png"}
KEEP_BATCH_ROWS = 12  # lots de synchronisation dont on garde les lignes détaillées
ISSUES_SHOWN = 60


class SyncFailed(Exception):
    pass


def _summary_issue(path: str, message: str) -> dict:
    return {"path": path, "message": message}


def run_sync(trigger: str = GhplSyncRun.Trigger.SCHEDULE, user=None, client=None) -> GhplSyncRun:
    """Un passage complet ; ne lève pas (l'échec est consigné sur le passage)."""
    client = client if client is not None else Nextcloud.from_settings()
    run = GhplSyncRun.objects.create(trigger=trigger, started_by=user)
    if client is None or not settings.GHPL_SYNC_ENABLED:
        run.status = GhplSyncRun.Status.NOT_CONFIGURED
        run.message = (
            "Nextcloud n'est pas configuré : renseignez NEXTCLOUD_USER et NEXTCLOUD_APP_PASSWORD "
            "dans Render (voir docs/synchronisation-ghpl.md)."
            if client is None
            else "Synchronisation désactivée (GHPL_SYNC_ENABLED)."
        )
        _finish(run)
        return run
    try:
        _run(run, client, user)
    except (NextcloudError, SyncFailed) as exc:
        run.status = GhplSyncRun.Status.FAILED
        run.message = str(exc)
    except Exception as exc:  # noqa: BLE001 — consigné, le passage suivant réessaie
        logger.exception("Synchronisation AMM GHPL")
        run.status = GhplSyncRun.Status.FAILED
        run.message = f"Erreur inattendue : {exc}"
    _finish(run)
    return run


def _finish(run: GhplSyncRun) -> None:
    run.finished_at = timezone.now()
    run.save()
    _prune()


def _previous() -> GhplSyncRun | None:
    return (
        GhplSyncRun.objects.filter(status__in=[GhplSyncRun.Status.DONE, GhplSyncRun.Status.PARTIAL])
        .exclude(fingerprints={})
        .order_by("-started_at")
        .first()
    )


def _run(run: GhplSyncRun, client: Nextcloud, user) -> None:
    registry_path = settings.GHPL_SYNC_REGISTRY
    remote = client.stat(registry_path)
    if remote is None:
        raise SyncFailed(
            f"Registre introuvable sur Nextcloud : « {settings.GHPL_SYNC_ROOT}/{registry_path} »."
        )
    run.registry_etag, run.registry_modified = remote.etag, remote.modified
    previous = _previous()
    pending = GhplSyncedFile.objects.filter(
        state=GhplSyncedFile.State.PENDING, attempts__lt=MAX_ATTEMPTS
    ).exists()
    if previous and previous.registry_etag == remote.etag and not pending:
        run.status = GhplSyncRun.Status.UP_TO_DATE
        run.fingerprints = {}
        run.summary = {"message": "Registre inchangé depuis le dernier passage."}
        return

    counts: Counter = Counter()
    issues: list[dict] = []
    present: set[str] | None = None
    if previous is None or previous.registry_etag != remote.etag:
        content = client.download(registry_path, max_bytes=64 << 20)
        if content is None:
            raise SyncFailed(
                "Le registre a disparu pendant la lecture : nouvel essai au passage suivant."
            )
        from ..registry import _deposits, read_registry

        try:
            records, docs = read_registry(io.BytesIO(content))
        except Exception as exc:
            raise SyncFailed(
                f"Registre illisible ({exc}) : nouvel essai au passage suivant."
            ) from exc
        rows = manifest_rows(docs, records)
        principal = [r for r in rows if r["principal"] == "oui"]
        before = (previous.summary or {}).get("pieces") if previous else None
        if not principal or (before and len(principal) < MIN_COVERAGE * before):
            raise SyncFailed(
                f"Registre incomplet : {len(principal)} pièces contre {before or 0} au passage "
                "précédent (registre peut-être en cours d'écriture). Rien n'est appliqué."
            )
        prints = fingerprints(rows, records, _deposits(docs))
        old = previous.fingerprints if previous else {}
        changed = {key for key, value in prints.items() if old.get(key) != value}
        changed_records = [r for r in records if f"R:{record_key(r)}" in changed]
        changed_groups = {key[2:] for key in changed if key.startswith("D:")}
        changed_rows = [r for r in rows if group_key(r) in changed_groups]
        counts["pieces"] = len(principal)
        counts["presentations_changed"] = len(changed_groups)
        counts["registry_rows_changed"] = len(changed_records)
        if changed_records:
            run.registry_batch = _import(
                "registry", remote, user, records=changed_records, docs=docs
            )
        if changed_rows:
            run.scans_batch = _import("scans", remote, user, rows=changed_rows)
            _place(run.scans_batch, counts, issues)
        present = {r["chemin"] for r in principal}
        run.fingerprints = prints
    else:
        run.fingerprints = previous.fingerprints
        counts["pieces"] = (previous.summary or {}).get("pieces", 0)

    _download(client, counts, issues)
    if present is not None:
        # Après les téléchargements : une pièce déplacée a retrouvé son document sous son
        # nouveau chemin, l'ancien chemin n'est pas signalé comme « retiré ».
        _mark_removed(present, counts, issues)
    left = GhplSyncedFile.objects.filter(
        state=GhplSyncedFile.State.PENDING, attempts__lt=MAX_ATTEMPTS
    ).count()
    counts["pending"] = left
    run.status = GhplSyncRun.Status.PARTIAL if left else GhplSyncRun.Status.DONE
    run.summary = {**counts, "issues": issues[:ISSUES_SHOWN], "issues_total": len(issues)}
    if counts.get("presentations_changed") or counts.get("downloaded") or counts.get("moved"):
        from apps.analytics.tasks import refresh_analytics_views
        from apps.core.tasks import enqueue
        from apps.realtime.publisher import publish_dashboard_refresh

        publish_dashboard_refresh()
        enqueue(refresh_analytics_views)


# -- imports -------------------------------------------------------------------------------
def _import(kind: str, remote, user, **rows) -> ImportBatch:
    """Lot d'import ordinaire (visible dans Imports Excel), limité aux présentations changées.

    Le registre n'est pas recopié (2,5 Mo à chaque passage) : le lot garde une note de sa
    version, et ses lignes disent ce qui a été appliqué.
    """
    from ..registry import import_registry
    from ..scans import import_scan_manifest

    batch = ImportBatch(
        created_by=user, status=ImportBatch.Status.RUNNING, started_at=timezone.now()
    )
    batch.reference_date = timezone.localdate()
    note = (
        f"Synchronisation AMM GHPL : {settings.GHPL_SYNC_ROOT}/{settings.GHPL_SYNC_REGISTRY}\n"
        f"version {remote.etag}, modifié le {remote.modified}\n"
    )
    label = "registre" if kind == "registry" else "pieces"
    batch.file.save(f"synchro-ghpl-{label}.txt", ContentFile(note.encode()), save=False)
    batch.save()
    summary = {"kind": kind, "source": "synchro", "dry_run": False, "sheets": {}, "totals": {}}
    try:
        if kind == "registry":
            sheets = import_registry(None, batch, False, records=rows["records"], docs=rows["docs"])
        else:
            sheets = import_scan_manifest(None, batch, False, rows=rows["rows"], correct=False)
        summary["sheets"] = sheets
        totals: Counter = Counter()
        for stats in sheets.values():
            totals.update({k: v for k, v in stats.items() if isinstance(v, int)})
        summary["totals"] = dict(totals)
        batch.status = ImportBatch.Status.DONE
    except Exception as exc:
        logger.exception("Synchronisation AMM GHPL, import %s", kind)
        summary["error"] = str(exc)
        batch.status = ImportBatch.Status.FAILED
    batch.summary = summary
    batch.finished_at = timezone.now()
    batch.save(update_fields=["status", "summary", "finished_at"])
    if batch.status == ImportBatch.Status.FAILED:
        raise SyncFailed(f"Import {kind} échoué : {summary.get('error')}")
    return batch


# -- pièces --------------------------------------------------------------------------------
def _same_place(document: Document, place: dict) -> bool:
    return (
        str(document.amm_id) == place["amm"]
        and (str(document.renewal_id) if document.renewal_id else None) == place.get("renewal")
        and document.kind == place["kind"]
        and document.document_date.isoformat() == place["document_date"]
    )


def _move(document: Document, place: dict) -> str | None:
    """Range le document à sa nouvelle place ; renvoie un motif s'il ne peut pas suivre."""
    target_amm = str(document.amm_id) != place["amm"]
    if (
        target_amm
        and Document.objects.filter(
            amm_id=place["amm"], sha256=document.sha256, archived_at__isnull=True
        ).exists()
    ):
        return "le même fichier est déjà sur la fiche de destination"
    previous_amm = document.amm_id
    document.amm_id = place["amm"]
    document.renewal_id = place.get("renewal")
    document.kind = place["kind"]
    document.document_date = date.fromisoformat(place["document_date"])
    document._change_reason = f"{REASON} : reclassé dans le classement"
    with transaction.atomic():
        document.save(update_fields=["amm", "renewal", "kind", "document_date"])
    if target_amm:
        from apps.amm.services.status import apply_state

        old = MarketingAuthorization.objects.filter(pk=previous_amm).first()
        if old is not None:
            apply_state(old)  # la fiche quittée perd peut-être son scan en vigueur
    return None


def _adopt(place: dict, name: str) -> Document | None:
    """Document déjà envoyé (script du Mac, import de dossiers) : même nom sur la fiche."""
    return (
        Document.objects.current()
        .filter(amm_id=place["amm"], title=name[:255])
        .order_by("-uploaded_at")
        .first()
    )


def _place(batch: ImportBatch, counts: Counter, issues: list[dict]) -> None:
    """Rattache chaque pièce importée à son document, ou la met en attente de téléchargement."""
    for row in ImportRow.objects.filter(batch=batch).only("raw", "amm_id").iterator():
        raw = row.raw or {}
        path, place = raw.get("chemin"), raw.get("placement")
        if not path:
            continue
        synced, _ = GhplSyncedFile.objects.get_or_create(path=path)
        if not place:
            synced.state, synced.placement, synced.amm = (
                GhplSyncedFile.State.SKIPPED,
                {},
                None,
            )
            synced.message = "pièce non rangée par l'import (voir le lot « Scans classés »)"
            synced.save()
            counts["not_placed"] += 1
            issues.append(_summary_issue(path, synced.message))
            continue
        synced.placement, synced.amm_id = place, place["amm"]
        document = synced.document
        if document is not None and document.archived_at is None:
            if not _same_place(document, place):
                reason = _move(document, place)
                if reason:
                    synced.message = f"reclassé dans le classement, non suivi : {reason}"
                    issues.append(_summary_issue(path, synced.message))
                else:
                    counts["moved"] += 1
                    synced.message = f"reclassé : {place.get('target', '')}"
            synced.state = GhplSyncedFile.State.SYNCED
            synced.save()
            continue
        adopted = _adopt(place, raw.get("nom") or path.rsplit("/", 1)[-1])
        if adopted is not None:
            synced.document, synced.sha256 = adopted, adopted.sha256
            synced.state, synced.message = GhplSyncedFile.State.SYNCED, "déjà sur la fiche"
            if not _same_place(adopted, place) and not _move(adopted, place):
                counts["moved"] += 1
            counts["adopted"] += 1
        elif not (synced.state == GhplSyncedFile.State.SKIPPED and synced.sha256):
            # Pas encore téléchargée (ou jamais rangée) : en attente. Une pièce déjà lue et
            # laissée de côté (Word, trop lourde) n'est pas retéléchargée à chaque changement.
            synced.state, synced.attempts, synced.message = GhplSyncedFile.State.PENDING, 0, ""
            counts["queued"] += 1
        synced.save()


def _mark_removed(present: set[str], counts: Counter, issues: list[dict]) -> None:
    gone = GhplSyncedFile.objects.exclude(path__in=present).exclude(
        state=GhplSyncedFile.State.REMOVED
    )
    claimed = set(
        GhplSyncedFile.objects.filter(path__in=present, document__isnull=False).values_list(
            "document_id", flat=True
        )
    )
    for synced in gone.iterator():
        synced.state = GhplSyncedFile.State.REMOVED
        if synced.document_id and synced.document_id not in claimed:
            synced.message = "retiré du classement : le document reste dans AMM GH (à vérifier)"
            issues.append(_summary_issue(synced.path, synced.message))
            counts["removed"] += 1
        else:
            synced.message = "déplacé dans le classement"
        synced.save(update_fields=["state", "message", "updated_at"])


def _to_upload(name: str, content: bytes) -> tuple[bytes, str] | str:
    """(contenu, nom) acceptés par AMM GH, ou le motif de mise de côté."""
    suffix = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if suffix == ".pdf":
        return content, name
    if suffix in ACCEPTED:
        # Converti ici comme à l'envoi : l'empreinte comparée est celle du PDF conservé.
        from apps.documents.services.ingest import convert_image_to_pdf

        pdf = convert_image_to_pdf(content)
        if pdf is None:
            return "image illisible : à vérifier dans le classement"
        return pdf, name[: -len(suffix)] + ".pdf"
    if suffix == ".jp2":
        try:
            from PIL import Image

            from apps.documents.services.ingest import convert_image_to_pdf

            buffer = io.BytesIO()
            Image.open(io.BytesIO(content)).convert("RGB").save(buffer, "PNG")
            pdf = convert_image_to_pdf(buffer.getvalue())
            if pdf is None:
                raise ValueError("conversion impossible")
            return pdf, name[: -len(suffix)] + ".pdf"
        except Exception:  # noqa: BLE001
            return "image JPEG 2000 illisible : à convertir puis déposer à la main"
    if suffix == ".docx":
        return "document Word : à enregistrer en PDF dans le classement"
    return f"format non accepté par AMM GH ({suffix or 'sans extension'})"


def _download(client: Nextcloud, counts: Counter, issues: list[dict]) -> None:
    max_bytes = settings.DOCUMENT_MAX_MB * 1024 * 1024
    queue = GhplSyncedFile.objects.filter(
        state=GhplSyncedFile.State.PENDING, attempts__lt=MAX_ATTEMPTS
    ).order_by("first_seen_at")[: settings.GHPL_SYNC_MAX_FILES]
    for synced in list(queue):
        place, path = synced.placement, synced.path
        name = path.rsplit("/", 1)[-1]
        synced.attempts += 1
        if not place:
            synced.state, synced.message = GhplSyncedFile.State.SKIPPED, "pas de place dans AMM GH"
            synced.save()
            continue
        try:
            content = client.download(path, max_bytes)
        except TooLarge as exc:
            synced.state = GhplSyncedFile.State.SKIPPED
            synced.message = (
                f"trop volumineux ({exc}, limite {settings.DOCUMENT_MAX_MB} Mo) : à compresser"
            )
            issues.append(_summary_issue(path, synced.message))
            counts["skipped"] += 1
            synced.save()
            continue
        except NextcloudError as exc:
            synced.message = str(exc)
            synced.save()
            counts["errors"] += 1
            break  # Nextcloud ne répond plus : la suite au passage suivant
        if content is None:
            synced.state, synced.message = GhplSyncedFile.State.REMOVED, "introuvable sur Nextcloud"
            synced.save()
            continue
        synced.sha256 = hashlib.sha256(content).hexdigest()
        prepared = _to_upload(name, content)
        if isinstance(prepared, str):
            synced.state, synced.message = GhplSyncedFile.State.SKIPPED, prepared
            issues.append(_summary_issue(path, prepared))
            counts["skipped"] += 1
            synced.save()
            continue
        data, upload_name = prepared
        existing = (
            Document.objects.current().filter(sha256=hashlib.sha256(data).hexdigest()).first()
        )
        if existing is not None:
            # Même fichier déjà dans AMM GH (envoyé à la main, ou reclassé sous un autre nom).
            synced.document = existing
            if not _same_place(existing, place):
                reason = _move(existing, place)
                synced.message = (
                    f"déjà dans AMM GH, non déplacé : {reason}"
                    if reason
                    else "déjà dans AMM GH, reclassé"
                )
                if not reason:
                    counts["moved"] += 1
            else:
                synced.message = "déjà dans AMM GH"
            synced.state = GhplSyncedFile.State.SYNCED
            counts["adopted"] += 1
            synced.save()
            GhplSyncedFile.objects.filter(
                document=existing, state=GhplSyncedFile.State.REMOVED
            ).exclude(pk=synced.pk).update(message="déplacé dans le classement")
            continue
        amm = MarketingAuthorization.objects.filter(pk=place["amm"]).first()
        renewal = (
            Renewal.objects.filter(pk=place["renewal"], amm_id=place["amm"]).first()
            if place.get("renewal")
            else None
        )
        if amm is None:
            synced.state, synced.message = GhplSyncedFile.State.ERROR, "fiche AMM introuvable"
            synced.save()
            continue
        from apps.documents.services.ingest import ingest_document

        try:
            document = ingest_document(
                amm,
                ContentFile(data, name=upload_name),
                place["kind"],
                document_date=date.fromisoformat(place["document_date"]),
                title=place.get("title") or name[:255],
                renewal=renewal,
                user=None,
            )
        except ValidationError as exc:
            messages = "; ".join(
                m
                for values in getattr(exc, "message_dict", {"": exc.messages}).values()
                for m in values
            )
            synced.state = (
                GhplSyncedFile.State.ERROR
                if synced.attempts >= MAX_ATTEMPTS
                else GhplSyncedFile.State.SKIPPED
            )
            synced.message = messages or "fichier refusé"
            issues.append(_summary_issue(path, synced.message))
            counts["skipped"] += 1
            synced.save()
            continue
        except Exception as exc:  # stockage indisponible : nouvel essai au passage suivant
            logger.warning("Synchronisation AMM GHPL, envoi de %s : %s", path, exc)
            synced.message = "stockage des scans indisponible : nouvel essai au passage suivant"
            synced.save()
            counts["errors"] += 1
            break
        synced.document, synced.state, synced.message = (
            document,
            GhplSyncedFile.State.SYNCED,
            "ajouté",
        )
        counts["downloaded"] += 1
        synced.save()


# -- ménage --------------------------------------------------------------------------------
def _prune() -> None:
    """Passages « déjà à jour » de plus de 7 jours, et lignes détaillées des anciens lots."""
    now = timezone.now()
    GhplSyncRun.objects.filter(
        status__in=[GhplSyncRun.Status.UP_TO_DATE, GhplSyncRun.Status.NOT_CONFIGURED],
        started_at__lt=now - timedelta(days=7),
    ).delete()
    GhplSyncRun.objects.filter(started_at__lt=now - timedelta(days=120)).delete()
    batches = [
        pk
        for run in GhplSyncRun.objects.exclude(registry_batch=None, scans_batch=None).order_by(
            "-started_at"
        )
        for pk in (run.registry_batch_id, run.scans_batch_id)
        if pk
    ]
    old = batches[KEEP_BATCH_ROWS:]
    if old:
        ImportRow.objects.filter(batch_id__in=old).delete()
    # Seules les empreintes du dernier passage réussi servent (150 Ko par passage sinon).
    latest = _previous()
    if latest is not None:
        GhplSyncRun.objects.exclude(pk=latest.pk).exclude(fingerprints={}).update(fingerprints={})
