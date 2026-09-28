"""Ce que font le siège et les pays sur un dossier de dépôt.

Toutes les fonctions lèvent `django.core.exceptions.ValidationError` en cas de refus (message en
français, prêt à afficher). Le renouvellement lié suit le dossier par la machine d'états
habituelle (`apps.amm.services.workflow`) : historique, recalcul de l'AMM et temps réel compris.
"""

from datetime import date

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.amm.models import MarketingAuthorization, Renewal
from apps.amm.services.workflow import create_renewal, lock_amm, transition
from apps.core.dates import today
from apps.documents.models import Document
from apps.documents.services.ingest import ingest_document
from apps.notifications.models import Notification
from apps.realtime.publisher import country_group, publish, publish_user_event

from .models import (
    DepositActivity,
    DepositDossier,
    DepositEvent,
    DepositMessage,
    DepositPiece,
    DepositSample,
    PieceType,
)

S = Renewal.WorkflowStatus
A = DepositActivity.Kind

# Pièces acceptées : les formulaires et lettres arrivent souvent en Word ou en Excel.
PIECE_TYPES = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "odt": "application/vnd.oasis.opendocument.text",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}


# --- Qui voit, qui agit --------------------------------------------------------------------


def visible_dossiers(user):
    queryset = DepositDossier.objects.select_related(
        "renewal__amm__product", "renewal__amm__country", "sent_by", "created_by"
    )
    if user.is_global:
        return queryset
    return queryset.filter(renewal__amm__country__in=user.countries.all())


def ensure_hq(user) -> None:
    if not user.is_global:
        raise PermissionDenied("Réservé au siège.")


def ensure_open(dossier: DepositDossier) -> None:
    if dossier.renewal.workflow_status in Renewal.TERMINAL_STATUSES:
        raise ValidationError(
            f"Le dossier est clos ({dossier.renewal.get_workflow_status_display().lower()})."
        )


# --- Pièces demandées ----------------------------------------------------------------------


def piece_types_for(country) -> list[PieceType]:
    """Liste de base (moins les pièces que ce pays ne demande pas) puis pièces propres au pays."""
    return list(
        PieceType.objects.filter(active=True)
        .filter(Q(country__isnull=True) | Q(country=country))
        .exclude(excluded_countries=country)
        .order_by("country_id", "order", "label")
        .distinct()
    )


def missing_for_send(dossier: DepositDossier) -> list[str]:
    present = {piece.piece_type_id for piece in dossier.pieces.all()}
    missing = [
        piece_type.label
        for piece_type in piece_types_for(dossier.renewal.amm.country)
        if piece_type.required and piece_type.pk not in present
    ]
    if dossier.samples_required and not dossier.samples.exists():
        missing.append("Échantillons (n° de lot, date de fabrication, date de péremption)")
    return missing


# --- Notifications -------------------------------------------------------------------------


def country_side(dossier: DepositDossier):
    return User.objects.filter(
        is_active=True,
        role=User.Role.COUNTRY_REGULATORY,
        countries=dossier.renewal.amm.country_id,
    ).distinct()


def hq_side(dossier: DepositDossier):
    return User.objects.filter(
        Q(role=User.Role.HQ_REGULATORY) | Q(pk=dossier.created_by_id), is_active=True
    ).distinct()


def _title(dossier: DepositDossier, what: str) -> str:
    amm = dossier.renewal.amm
    return f"{what} : {amm.product.name} ({amm.country.name})"[:255]


def notify(dossier: DepositDossier, users, actor, what: str, body: str = "") -> None:
    link = f"{settings.FRONTEND_URL.rstrip('/')}/depots/{dossier.pk}"
    iso2 = dossier.renewal.amm.country.iso2
    for user in users:
        if actor is not None and user.pk == actor.pk:
            continue
        notification = Notification.objects.create(
            user=user,
            channel=Notification.Channel.IN_APP,
            title=_title(dossier, what),
            body=body,
            link=link,
            sent_at=timezone.now(),
        )
        publish_user_event(user.pk, "notification.created", notification.pk, iso2)


def other_side(dossier: DepositDossier, actor):
    return country_side(dossier) if actor.is_global else hq_side(dossier)


def _touch(dossier: DepositDossier, kind: str, text: str, user) -> None:
    DepositActivity.objects.create(dossier=dossier, kind=kind, text=text[:500], user=user)
    DepositDossier.objects.filter(pk=dossier.pk).update(updated_at=timezone.now())
    amm = dossier.renewal.amm
    publish(
        country_group(amm.country.iso2),
        {"type": "deposit.updated", "id": str(dossier.pk), "country": amm.country.iso2},
    )


def _who(user) -> str:
    return user.full_name if user else "?"


# --- Ouvrir le dossier ---------------------------------------------------------------------


@transaction.atomic
def open_dossier(amm: MarketingAuthorization, user) -> DepositDossier:
    """Ouvre le dossier de dépôt du prochain renouvellement de `amm` (siège).

    Le renouvellement ouvert est repris ; sinon il est planifié. Un renouvellement planifié passe
    « en préparation » : le montage commence.
    """
    ensure_hq(user)
    lock_amm(amm.pk)
    renewal = (
        Renewal.objects.filter(amm=amm, workflow_status__in=Renewal.OPEN_STATUSES)
        .order_by("-sequence")
        .first()
    )
    if renewal is not None and DepositDossier.objects.filter(renewal=renewal).exists():
        raise ValidationError("Un dossier de dépôt est déjà ouvert pour ce renouvellement.")
    if renewal is None:
        renewal = create_renewal(amm, actor=user)
    if renewal.workflow_status == S.PLANIFIE:
        renewal = transition(renewal, S.EN_PREPARATION, actor=user)
    dossier = DepositDossier.objects.create(renewal=renewal, created_by=user)
    _touch(dossier, A.CREE, f"Dossier ouvert par {_who(user)}", user)
    return dossier


# --- Montage (siège) -----------------------------------------------------------------------


def _read(uploaded_file, allowed: dict[str, str]) -> tuple[bytes, str, str]:
    name = (getattr(uploaded_file, "name", "") or "piece").rsplit("/", 1)[-1]
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in allowed:
        accepted = ", ".join(sorted({ext.upper() for ext in allowed}))
        raise ValidationError(f"Format non accepté pour « {name} » (acceptés : {accepted}).")
    max_bytes = settings.DOCUMENT_MAX_MB * 1024 * 1024
    if getattr(uploaded_file, "size", 0) > max_bytes:
        raise ValidationError(f"« {name} » dépasse {settings.DOCUMENT_MAX_MB} Mo.")
    content = uploaded_file.read()
    if not content:
        raise ValidationError(f"« {name} » est vide.")
    if len(content) > max_bytes:
        raise ValidationError(f"« {name} » dépasse {settings.DOCUMENT_MAX_MB} Mo.")
    return content, name, allowed[extension]


def add_piece(
    dossier, user, uploaded_file, piece_type: PieceType | None = None, label=""
) -> DepositPiece:
    ensure_hq(user)
    ensure_open(dossier)
    if piece_type is None and not label.strip():
        raise ValidationError("Nommez la pièce.")
    if piece_type is not None and piece_type not in piece_types_for(dossier.renewal.amm.country):
        raise ValidationError("Cette pièce n'est pas demandée dans ce pays.")
    content, name, content_type = _read(uploaded_file, PIECE_TYPES)
    piece = DepositPiece(
        dossier=dossier,
        piece_type=piece_type,
        label=label.strip() or (piece_type.label if piece_type else ""),
        filename=name,
        content_type=content_type,
        size_bytes=len(content),
        uploaded_by=user,
    )
    piece.file.save(name, ContentFile(content), save=False)
    piece.save()
    _touch(dossier, A.PIECE, f"{piece.label} : {name}", user)
    if dossier.sent_at:
        # Complément après l'envoi : le pays doit le savoir pour le joindre au dépôt.
        notify(
            dossier,
            country_side(dossier),
            user,
            "Pièce ajoutée au dossier envoyé",
            f"{piece.label} : {name}",
        )
    return piece


def remove_piece(piece: DepositPiece, user) -> None:
    ensure_hq(user)
    dossier = piece.dossier
    if dossier.sent_at:
        raise ValidationError("Le dossier est déjà envoyé au pays : ajoutez plutôt un complément.")
    label = f"{piece.label} : {piece.filename}"
    piece.file.delete(save=False)
    piece.delete()
    _touch(dossier, A.PIECE_RETIREE, label, user)


def add_sample(dossier, user, **fields) -> DepositSample:
    ensure_hq(user)
    ensure_open(dossier)
    if fields["expires_on"] <= fields["manufactured_on"]:
        raise ValidationError("La date de péremption doit suivre la date de fabrication.")
    sample = DepositSample.objects.create(dossier=dossier, created_by=user, **fields)
    _touch(
        dossier,
        A.ECHANTILLON,
        f"Lot {sample.batch_number} (fabriqué le {sample.manufactured_on:%d/%m/%Y}, "
        f"périme le {sample.expires_on:%d/%m/%Y})",
        user,
    )
    return sample


def remove_sample(sample: DepositSample, user) -> None:
    ensure_hq(user)
    if sample.dossier.sent_at:
        raise ValidationError("Le dossier est déjà envoyé au pays.")
    dossier = sample.dossier
    sample.delete()
    _touch(dossier, A.ECHANTILLON, f"Lot {sample.batch_number} retiré", user)


def set_samples_required(dossier, user, required: bool) -> None:
    ensure_hq(user)
    ensure_open(dossier)
    dossier.samples_required = required
    dossier.save(update_fields=["samples_required", "updated_at"])
    _touch(
        dossier,
        A.ECHANTILLON,
        "Échantillons demandés" if required else "Pas d'échantillons pour ce dépôt",
        user,
    )


# --- Envoi au pays -------------------------------------------------------------------------


@transaction.atomic
def send(dossier: DepositDossier, user, note: str = "") -> DepositDossier:
    ensure_hq(user)
    ensure_open(dossier)
    dossier = DepositDossier.objects.select_for_update().get(pk=dossier.pk)
    if dossier.sent_at:
        raise ValidationError("Le dossier est déjà envoyé au pays.")
    missing = missing_for_send(dossier)
    if missing:
        raise ValidationError("Dossier incomplet : " + " ; ".join(missing) + ".")
    dossier.sent_at = timezone.now()
    dossier.sent_by = user
    dossier.send_note = note.strip()
    dossier.save(update_fields=["sent_at", "sent_by", "send_note", "updated_at"])
    _touch(dossier, A.ENVOI, f"Envoyé au pays par {_who(user)}", user)
    recipients = country_side(dossier)
    notify(
        dossier,
        recipients,
        user,
        "Dossier de renouvellement à déposer",
        (note.strip() + "\n\n" if note.strip() else "")
        + "Téléchargez le dossier, déposez-le à l'agence, puis envoyez l'attestation de dépôt.",
    )
    return dossier


def record_download(dossier: DepositDossier, user) -> None:
    first = (
        not user.is_global
        and not dossier.activities.filter(kind=A.TELECHARGEMENT, user=user).exists()
    )
    _touch(dossier, A.TELECHARGEMENT, f"Téléchargé par {_who(user)}", user)
    if first:
        notify(dossier, hq_side(dossier), user, f"Dossier téléchargé par {_who(user)}")


# --- Dépôt, commission, décision (pays ou siège) -------------------------------------------


def _ingest(dossier, user, uploaded_file, kind, when: date, title: str) -> Document:
    return ingest_document(
        dossier.renewal.amm,
        uploaded_file,
        kind,
        document_date=when,
        title=title,
        renewal=dossier.renewal,
        user=user,
    )


def record_deposit(dossier: DepositDossier, user, filing_date: date, attestation) -> DepositDossier:
    """Le pays a déposé : date de dépôt et attestation, envoyée au siège."""
    ensure_open(dossier)
    if not dossier.sent_at and not user.is_global:
        raise ValidationError("Le siège n'a pas encore envoyé le dossier.")
    if filing_date > today():
        raise ValidationError("La date de dépôt ne peut pas être dans le futur.")
    status = dossier.renewal.workflow_status
    if status not in (S.PLANIFIE, S.EN_PREPARATION, S.DEPOSE, S.EN_INSTRUCTION):
        raise ValidationError("Ce renouvellement ne peut plus être déposé.")
    document = _ingest(
        dossier, user, attestation, Document.Kind.RECEPISSE, filing_date, "Attestation de dépôt"
    )
    with transaction.atomic():
        dossier = DepositDossier.objects.select_for_update().get(pk=dossier.pk)
        renewal = dossier.renewal
        if renewal.workflow_status == S.PLANIFIE:
            renewal = transition(renewal, S.EN_PREPARATION, actor=user)
        if renewal.workflow_status == S.EN_PREPARATION:
            transition(renewal, S.DEPOSE, actor=user, filing_date=filing_date)
        elif not renewal.filing_date:
            renewal.filing_date = filing_date
            renewal._history_user = user
            renewal.save(update_fields=["filing_date", "updated_at"])
        dossier.deposited_at = timezone.now()
        dossier.deposited_by = user
        dossier.attestation = document
        dossier.save(update_fields=["deposited_at", "deposited_by", "attestation", "updated_at"])
        _touch(
            dossier,
            A.DEPOT,
            f"Déposé à l'agence le {filing_date:%d/%m/%Y} ; attestation envoyée par {_who(user)}",
            user,
        )
        notify(
            dossier,
            other_side(dossier, user),
            user,
            "Attestation de dépôt reçue",
            f"Déposé à l'agence le {filing_date:%d/%m/%Y}.",
        )
    return dossier


def add_event(dossier: DepositDossier, user, kind: str, when: date, note="", file=None):
    ensure_open(dossier)
    if dossier.renewal.workflow_status not in Renewal.PENDING_STATUSES:
        raise ValidationError("Enregistrez d'abord le dépôt à l'agence.")
    if when > today():
        raise ValidationError("La date ne peut pas être dans le futur.")
    event = DepositEvent(dossier=dossier, kind=kind, date=when, note=note.strip(), created_by=user)
    if file is not None:
        content, name, _ = _read(file, PIECE_TYPES)
        event.filename = name
        event.file.save(name, ContentFile(content), save=False)
    with transaction.atomic():
        event.save()
        if kind == DepositEvent.Kind.COMMISSION and dossier.renewal.workflow_status == S.DEPOSE:
            transition(dossier.renewal, S.EN_INSTRUCTION, actor=user)
        label = event.get_kind_display()
        _touch(dossier, A.SUIVI, f"{label} du {when:%d/%m/%Y}", user)
        notify(dossier, other_side(dossier, user), user, label, note.strip())
    return event


def record_decision(
    dossier: DepositDossier,
    user,
    result: str,
    decision_date: date,
    number: str = "",
    start_date: date | None = None,
    note: str = "",
    file=None,
) -> DepositDossier:
    ensure_open(dossier)
    renewal = dossier.renewal
    if renewal.workflow_status not in Renewal.PENDING_STATUSES:
        raise ValidationError("Enregistrez d'abord le dépôt à l'agence.")
    if result == S.OBTENU and (not number.strip() or not start_date):
        raise ValidationError("Renseignez le n° du renouvellement et sa date de début.")
    if result not in (S.OBTENU, S.REJETE):
        raise ValidationError("Décision inconnue.")
    if file is not None and result == S.OBTENU:
        _ingest(dossier, user, file, Document.Kind.AMM, start_date, "Décision de renouvellement")
    elif file is not None:
        _ingest(dossier, user, file, Document.Kind.COURRIER, decision_date, "Décision de rejet")
    with transaction.atomic():
        if result == S.REJETE and renewal.workflow_status == S.DEPOSE:
            renewal = transition(renewal, S.EN_INSTRUCTION, actor=user)
        fields = {"decision_date": decision_date}
        if result == S.OBTENU:
            fields.update(number=number.strip(), start_date=start_date)
        if note.strip():
            fields["notes"] = "\n".join(filter(None, [renewal.notes, note.strip()]))
        transition(renewal, result, actor=user, **fields)
        dossier.refresh_from_db()
        text = (
            f"Renouvellement obtenu : n° {number.strip()} à partir du {start_date:%d/%m/%Y}"
            if result == S.OBTENU
            else f"Renouvellement rejeté le {decision_date:%d/%m/%Y}"
        )
        _touch(dossier, A.DECISION, text, user)
        users = list(hq_side(dossier)) + list(country_side(dossier))
        notify(dossier, {u.pk: u for u in users}.values(), user, text)
    return dossier


@transaction.atomic
def abandon(dossier: DepositDossier, user, reason: str) -> None:
    ensure_hq(user)
    ensure_open(dossier)
    if not reason.strip():
        raise ValidationError("Indiquez pourquoi le renouvellement est abandonné.")
    renewal = dossier.renewal
    notes = "\n".join(filter(None, [renewal.notes, f"Abandonné : {reason.strip()}"]))
    transition(renewal, S.ABANDONNE, actor=user, notes=notes)
    _touch(dossier, A.ABANDON, f"Abandonné : {reason.strip()}", user)
    notify(dossier, country_side(dossier), user, "Renouvellement abandonné", reason.strip())


def post_message(dossier: DepositDossier, user, body: str) -> DepositMessage:
    if not body.strip():
        raise ValidationError("Message vide.")
    message = DepositMessage.objects.create(dossier=dossier, author=user, body=body.strip())
    DepositDossier.objects.filter(pk=dossier.pk).update(updated_at=timezone.now())
    amm = dossier.renewal.amm
    publish(
        country_group(amm.country.iso2),
        {"type": "deposit.updated", "id": str(dossier.pk), "country": amm.country.iso2},
    )
    notify(
        dossier, other_side(dossier, user), user, f"Message de {_who(user)}", body.strip()[:1000]
    )
    return message
