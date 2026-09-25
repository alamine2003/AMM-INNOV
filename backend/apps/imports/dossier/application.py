"""Rangement d'un dossier sous verrous, avec la provenance documentaire de chaque champ.

Automatique dès que l'AMM est identifiée (voir `apps.imports.tasks`) : chaque scan va à sa
période, les renouvellements obtenus lus sont créés, les champs vides sont complétés. Une valeur
déjà renseignée n'est jamais remplacée : l'écart devient un « point à vérifier plus tard »
(`DossierReviewPoint`), que le réglementaire applique ou ignore ensuite (`review_points`).
"""

import hashlib
import json
from datetime import date

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied

from apps.accounts.permissions import ALL_ROLES, ensure_country_in_scope
from apps.amm.models import MarketingAuthorization, Renewal
from apps.catalog.models import Country, Product
from apps.catalog.normalize import normalize_product_name, product_key
from apps.core.dates import today
from apps.documents.models import Document
from apps.documents.services.ingest import convert_image_to_pdf
from apps.imports.models import DossierChange, DossierImport, DossierReviewPoint

from .preview import build_preview
from .summary import record_and_notify, snapshot

AMM_FIELDS = {"original_number", "original_start_date", "original_end_date", "holder"}
RENEWAL_FIELDS = {"number", "start_date", "end_date", "decision_date", "workflow_status"}


class StalePreview(APIException):
    status_code = 409
    default_detail = "Les données ont changé. Relancez l'analyse du dossier."


def preview_token(preview):
    # La projection (échéance et statut prévus) dépend de la date du jour : elle ne doit pas
    # rendre un aperçu « périmé » au passage de minuit. Elle est recalculée à chaque analyse.
    preview = {key: value for key, value in preview.items() if key != "projection"}
    return hashlib.sha256(
        json.dumps(preview, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def value_json(value):
    return value.isoformat() if isinstance(value, date) else value


def typed_value(field, value):
    return date.fromisoformat(value) if field.endswith("date") and value else value


def _audit(batch, amm, target, field, old, new, proof, confidence, user, reason=None):
    if old == new:
        return
    DossierChange.objects.create(
        batch=batch,
        amm=amm,
        renewal=target if isinstance(target, Renewal) else None,
        field=field,
        old_value=value_json(old),
        new_value=value_json(new),
        proof_file=proof,
        confidence=confidence,
        user=user,
        **({"reason": reason} if reason else {}),
    )


def _save_with_actor(obj, user, reason="Dossier réglementaire importé et rangé"):
    obj._history_user = user
    obj._change_reason = reason
    # Domain events must describe committed state. Reconcile once after the transaction.
    obj._skip_signals = True
    obj.save()


def _reconcile_after_commit(amm_id):
    from apps.amm.services.status import recompute_quietly
    from apps.amm.signals import on_amm_saved
    from apps.realtime.publisher import publish_amm_event

    amm = MarketingAuthorization.objects.get(pk=amm_id)
    # Les preuves viennent d'être rattachées : l'état du dossier en découle.
    recompute_quietly(amm)
    on_amm_saved(MarketingAuthorization, amm, created=False)
    publish_amm_event("document.created", amm, amm_id=str(amm.pk))


def _proof(files, proof_id):
    if str(proof_id) not in files:
        raise ValidationError("La preuve documentaire est absente du dossier.")
    return files[str(proof_id)]


class LostScan(ValidationError):
    """Scan absent du stockage et d'aucune autre copie : le dossier doit être redéposé."""


def _stored_content(field_file) -> bytes | None:
    from apps.documents.views import file_is_missing

    try:
        with field_file.open("rb") as stream:
            return stream.read()
    except Exception as exc:
        if file_is_missing(field_file, exc):
            return None
        raise


def source_content(source) -> bytes:
    """Contenu d'un scan déposé ; à défaut, n'importe quelle copie du même contenu.

    Les lots déposés avant le stockage permanent (22/09/2026) ont perdu leurs fichiers ; le
    même scan a souvent été redéposé depuis ou rangé ailleurs (même empreinte SHA-256).
    """
    from apps.imports.models import DossierFile

    content = _stored_content(source.file) if source.file else None
    if content is not None:
        return content
    copies = [
        other.file
        for other in DossierFile.objects.filter(sha256=source.sha256).exclude(pk=source.pk)[:5]
    ] + [document.file for document in Document.objects.filter(sha256=source.sha256)[:5]]
    for copy in copies:
        content = _stored_content(copy) if copy else None
        if content is not None and hashlib.sha256(content).hexdigest() == source.sha256:
            return content
    raise LostScan(
        f"Le scan « {source.relative_path.rsplit('/', 1)[-1]} » n'est plus sur le serveur "
        "(dossier déposé avant le stockage permanent) : redéposez ce dossier."
    )


def _pages_pdf(content: bytes, pages) -> bytes:
    """Pages d'un recueil de décisions qui concernent le produit, en un PDF à part."""
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter

    first, last = pages
    reader = PdfReader(BytesIO(content), strict=False)
    writer = PdfWriter()
    for page in reader.pages[max(first, 1) - 1 : last]:
        writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _document(batch, source, amm, renewal, proposal, user, created_blobs):
    existing = source.document
    if existing and existing.archived_at is None and existing.amm_id == amm.pk:
        return existing
    pages = proposal.get("pages")
    title = source.relative_path.rsplit("/", 1)[-1]
    is_pdf = source.content_type == "application/pdf"
    digest = source.sha256
    if is_pdf and not pages:
        duplicate = Document.objects.filter(
            amm=amm, sha256=digest, archived_at__isnull=True
        ).first()
        if duplicate:
            # Déjà rangé (ce dossier réimporté, ou le même fichier à deux endroits) : il reste
            # à sa place, jamais re-rangé ; l'aperçu en a fait un point à vérifier s'il y a lieu.
            return duplicate
    content = source_content(source)
    if pages and is_pdf:
        # Recueil de décisions : la fiche ne reçoit que la décision du produit.
        content = _pages_pdf(content, pages)
        span = str(pages[0]) if pages[0] == pages[1] else f"{pages[0]}-{pages[1]}"
        title = f"{title} (p. {span})"
    elif not is_pdf:
        content = convert_image_to_pdf(content)
        if content is None:
            raise ValidationError("Impossible de convertir une image du dossier en PDF.")
    digest = hashlib.sha256(content).hexdigest()
    duplicate = Document.objects.filter(amm=amm, sha256=digest, archived_at__isnull=True).first()
    if duplicate:
        return duplicate
    converted = content
    document = Document(
        amm=amm,
        renewal=renewal,
        kind=proposal["kind"],
        title=title[:255],
        document_date=typed_value("date", proposal.get("document_date"))
        or (renewal.start_date if renewal else amm.original_start_date)
        or today(),
        content_type="application/pdf",
        sha256=digest,
        size_bytes=len(converted),
        uploaded_by=user,
    )
    # Copie indépendante : la preuve du dossier (DossierFile) reste intacte même si le
    # document est remplacé, archivé puis purgé après la durée de rétention.
    document.file.save("document.pdf", ContentFile(converted), save=False)
    created_blobs.append((document.file.storage, document.file.name))
    _save_with_actor(document, user)
    return document


def _fingerprint(amm, renewal, point) -> str:
    identity = [
        str(amm.pk),
        str(renewal.pk) if renewal else "",
        point["code"],
        point.get("field") or "",
        json.dumps(point.get("scan"), sort_keys=True, ensure_ascii=False),
        "" if point.get("field") else point["message"],
    ]
    return hashlib.sha256("|".join(identity).encode()).hexdigest()


def record_points(batch, amm, plan, targets, files) -> int:
    """Enregistre les points à vérifier du plan ; un point déjà connu n'est pas recréé."""
    created = 0
    for point in plan.get("review_points", []):
        target = targets.get(point.get("target") or "")
        renewal = target if isinstance(target, Renewal) else None
        fingerprint = _fingerprint(amm, renewal, point)
        if DossierReviewPoint.objects.filter(amm=amm, fingerprint=fingerprint).exists():
            continue
        proof = files.get(str(point.get("proof_file_id")))
        DossierReviewPoint.objects.create(
            batch=batch,
            amm=amm,
            renewal=renewal,
            code=point["code"],
            field=point.get("field") or "",
            recorded_value=point.get("recorded"),
            scan_value=point.get("scan"),
            proof_file=proof,
            confidence=max(0, min(100, int(point.get("confidence") or 0))),
            message=point["message"],
            fingerprint=fingerprint,
        )
        created += 1
    return created


def _create_amm(batch, plan, identity, country, files, user):
    """Création depuis la décision d'origine : par le siège, ou d'office à l'analyse."""
    if identity.get("product_id"):
        product = Product.objects.select_for_update().get(pk=identity["product_id"])
    else:
        name = normalize_product_name(identity["product_name"])
        if Product.objects.filter(key=product_key(name)).exists():
            raise StalePreview()
        product = Product(name=name)
        product._history_user = user
        product.save()
    if MarketingAuthorization.objects.filter(product=product, country=country).exists():
        raise StalePreview()
    amm = MarketingAuthorization(product=product, country=country)
    for field, value in plan["original"].items():
        if field in AMM_FIELDS and value not in (None, ""):
            _proof(files, plan["original_proofs"].get(field))
            setattr(amm, field, typed_value(field, value))
    if plan["original"].get("original_end_date"):
        amm.original_end_date_manual = True
    _save_with_actor(amm, user)
    for field, value in plan["original"].items():
        if field in AMM_FIELDS and value not in (None, ""):
            _audit(
                batch,
                amm,
                amm,
                field,
                None,
                value,
                _proof(files, plan["original_proofs"].get(field)),
                plan["confidence"],
                user,
                "Création depuis le dossier réglementaire",
            )
    return amm


def apply_dossier(batch_id, *, user, token, auto=False, create=False):
    """Range le dossier : idempotent, et un aperçu qui a changé n'est jamais appliqué.

    `auto` : rangement automatique à la fin de l'analyse, au nom de l'auteur de l'import.
    `create` : l'AMM absente est créée depuis le dossier (par le siège, ou d'office avec
    `auto` quand la décision d'origine est lisible).
    """
    created_blobs = []
    try:
        with transaction.atomic():
            batch = DossierImport.objects.select_for_update().get(pk=batch_id)
            if not user.is_active or user.role not in ALL_ROLES:
                raise PermissionDenied()
            if not user.is_global and batch.created_by_id != user.pk:
                raise PermissionDenied()
            ensure_country_in_scope(user, batch.country)
            if batch.status == DossierImport.Status.APPLIED:
                return batch
            allowed = {DossierImport.Status.READY, DossierImport.Status.QUESTION}
            if batch.status not in allowed or token != batch.preview_token:
                raise StalePreview()
            plan = batch.preview
            identity = plan["amm"]
            question = plan.get("question")
            if question or not identity.get("id"):
                if not create:
                    raise ValidationError(
                        "AMM non identifiée : indiquez d'abord à quelle AMM ranger ce dossier."
                    )
                if not user.is_global and not auto:
                    # Création d'office (DOSSIER_AUTO_CREATE) : au nom de l'auteur, dans son
                    # périmètre ; le siège est notifié. À la main, elle reste au siège.
                    raise PermissionDenied("La création d'une AMM est réservée au siège.")
                if not question or not question.get("can_create"):
                    raise ValidationError("Ce dossier ne permet pas de créer l'AMM.")
            elif create:
                raise ValidationError("L'AMM de ce dossier existe déjà.")
            country = Country.objects.select_for_update().get(pk=identity["country_id"])
            ensure_country_in_scope(user, country)
            # Serialize catalog creation across countries as product keys are shared globally.
            if create and connection.vendor == "postgresql":
                key = product_key(identity["product_name"])
                lock_key = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], signed=True)
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])
            before = None
            if identity.get("id"):
                amm = MarketingAuthorization.objects.select_for_update().get(pk=identity["id"])
                before = snapshot(amm)
                list(
                    Renewal.objects.select_for_update().filter(amm=amm).values_list("pk", flat=True)
                )
            # Re-run reconciliation from stored extraction, under the same locks as application.
            fresh = build_preview(batch)
            if preview_token(fresh) != token:
                raise StalePreview()
            files = {str(f.pk): f for f in batch.files.select_related("document")}
            if not identity.get("id"):
                amm = _create_amm(batch, plan, identity, country, files, user)
            targets = {"amm": amm}
            for proposal in sorted(
                plan["renewals"], key=lambda r: (r.get("start_date") or "", r["key"])
            ):
                if proposal.get("existing_id"):
                    renewal = Renewal.objects.get(pk=proposal["existing_id"], amm=amm)
                else:
                    if not proposal.get("number") or not proposal.get("start_date"):
                        raise ValidationError(
                            "Un renouvellement obtenu exige un numéro et une date."
                        )
                    proof = _proof(files, proposal["proof_file_id"])
                    if Renewal.objects.filter(
                        amm=amm,
                        number=proposal["number"],
                        start_date=proposal["start_date"],
                    ).exists():
                        raise StalePreview()
                    renewal = Renewal(amm=amm, workflow_status=Renewal.WorkflowStatus.OBTENU)
                    for field in ("number", "start_date", "end_date", "decision_date"):
                        setattr(renewal, field, typed_value(field, proposal.get(field)))
                    renewal.end_date_manual = bool(proposal.get("end_date"))
                    _save_with_actor(renewal, user)
                    for field in (*sorted(RENEWAL_FIELDS),):
                        value = getattr(renewal, field)
                        if value not in (None, ""):
                            _audit(
                                batch,
                                amm,
                                renewal,
                                field,
                                None,
                                value,
                                proof,
                                proposal["confidence"],
                                user,
                                "Création d'un renouvellement depuis le dossier réglementaire",
                            )
                targets[proposal["key"]] = renewal
            dirty = set()
            # Seuls les champs vides sont complétés (et un renouvellement en cours conclu par sa
            # décision passe « obtenu ») ; les écarts sont devenus des points à vérifier.
            for change in plan["changes"]:
                if change["requires_confirmation"]:
                    continue
                obj = targets[change["target"]]
                field = change["field"]
                allowed = AMM_FIELDS if isinstance(obj, MarketingAuthorization) else RENEWAL_FIELDS
                if field not in allowed:
                    raise ValidationError("Modification non autorisée.")
                old = value_json(getattr(obj, field))
                if old != change["old"]:
                    raise StalePreview()
                proof = _proof(files, change["proof_file_id"])
                setattr(obj, field, typed_value(field, change["new"]))
                if field in {"original_end_date", "end_date"}:
                    setattr(obj, field + "_manual", True)
                _audit(
                    batch, amm, obj, field, old, change["new"], proof, change["confidence"], user
                )
                dirty.add(change["target"])
            for key in dirty:
                obj = targets[key]
                start = obj.original_start_date if key == "amm" else obj.start_date
                end = obj.original_end_date if key == "amm" else obj.end_date
                if start and end and end < start:
                    raise ValidationError("La date de fin précède la date de début.")
                _save_with_actor(obj, user)
            for proposal in plan["documents"]:
                source = _proof(files, proposal["file_id"])
                renewal = targets.get(proposal["period"])
                renewal = renewal if isinstance(renewal, Renewal) else None
                document = _document(batch, source, amm, renewal, proposal, user, created_blobs)
                source.document = document
                source.save(update_fields=["document"])
            record_points(batch, amm, plan, targets, files)
            # Recompute once after all renewals, then publish only on successful commit.
            _save_with_actor(amm, user)
            batch.amm = amm
            batch.country = country
            batch.status = DossierImport.Status.APPLIED
            batch.finished_at = timezone.now()
            batch.error = ""
            batch.auto_applied = auto
            batch.save(
                update_fields=["amm", "country", "status", "finished_at", "error", "auto_applied"]
            )
            transaction.on_commit(lambda: _reconcile_after_commit(amm.pk))
            # Après le recalcul : bilan réel (avant/après) et notification des personnes concernées.
            transaction.on_commit(lambda: record_and_notify(batch.pk, before))
            return batch
    except Exception:
        for storage, name in created_blobs:
            storage.delete(name)
        raise
