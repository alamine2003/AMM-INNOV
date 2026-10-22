"""Corriger la chronologie d'une page : périodes (origine, renouvellements) et pièces scannées.

Ce que la lecture automatique d'un scan a faussé se reprend ici, à la main, depuis le classeur :
- une période (AMM d'origine ou renouvellement) : n° et dates ;
- un renouvellement en trop (créé deux fois par un import) : il s'annule, ses pièces rejoignent
  la période choisie au lieu d'être archivées ;
- une pièce : sa date, son type, la période à laquelle elle appartient ; ou elle est retirée
  (archivée, l'historique la garde) ;
- une pièce manquante : ajoutée directement sur la bonne période, avec la date saisie — sans
  repasser par la lecture automatique.

Chaque écriture garde son auteur (historique) et l'AMM est recalculée (statut, échéance, état
du dossier) une fois la transaction validée.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import User
from apps.accounts.permissions import ensure_country_in_scope
from apps.amm.models import MarketingAuthorization, Renewal
from apps.amm.services import workflow
from apps.documents.models import Document
from apps.documents.services.ingest import ingest_document
from apps.imports.dossier.application import _reconcile_after_commit, _save_with_actor

from .layout import Binder, ensure_in_binder

REASON = "Chronologie corrigée depuis le classeur"
# Retirer une pièce, c'est la supprimer de la page : même règle que la suppression de document.
REMOVE_ROLES = (User.Role.CEO_ADMIN,)


def _page(binder: Binder, amm_id, user) -> MarketingAuthorization:
    amm = (
        MarketingAuthorization.objects.select_for_update(of=("self",))
        .select_related("country", "product__range")
        .get(pk=amm_id)
    )
    ensure_country_in_scope(user, amm.country)
    ensure_in_binder(binder, amm)
    return amm


def _renewal(amm, renewal_id, lock=True) -> Renewal:
    queryset = Renewal.objects.select_for_update() if lock else Renewal.objects
    try:
        renewal = queryset.filter(pk=renewal_id, amm=amm).first()
    except (ValueError, ValidationError):  # identifiant mal formé
        renewal = None
    if renewal is None:
        raise ValidationError("Cette période n'appartient pas à cette AMM.")
    return renewal


def _document(amm, document_id) -> Document:
    document = Document.objects.filter(
        pk=document_id, amm=amm, is_current=True, archived_at__isnull=True
    ).first()
    if document is None:
        raise ValidationError("Pièce introuvable sur cette page (déjà retirée ?).")
    return document


def _target_period(amm, period, lock=True):
    """« origin » ou l'identifiant d'un renouvellement de cette AMM."""
    if period in (None, "", "origin"):
        return None
    return _renewal(amm, period, lock=lock)


def _reconcile(amm) -> None:
    transaction.on_commit(lambda: _reconcile_after_commit(amm.pk))


def edit_period(binder: Binder, amm_id, *, period: str, values: dict, user):
    """Corrige le n° et les dates d'une période. Seuls les champs envoyés changent.

    Une date de fin envoyée est tenue pour saisie à la main ; l'effacer la fait recalculer
    à partir de la date de début et de la durée de validité du pays.
    """
    with transaction.atomic():
        amm = _page(binder, amm_id, user)
        target = _target_period(amm, period)
        prefix = "original_" if target is None else ""
        obj = amm if target is None else target
        changed = False
        for field in ("number", "start_date", "end_date"):
            if field not in values:
                continue
            value = values[field]
            if field == "number":
                value = (value or "").strip()
            attr = f"{prefix}{field}"
            if getattr(obj, attr) == value:
                continue
            setattr(obj, attr, value)
            if field == "end_date":
                setattr(obj, f"{attr}_manual", value is not None)
            changed = True
        if not changed:
            return amm
        start, end = getattr(obj, f"{prefix}start_date"), getattr(obj, f"{prefix}end_date")
        if start and end and end < start:
            raise ValidationError("La date de fin précéderait la date de début.")
        _save_with_actor(obj, user, REASON)
        if target is not None:
            # L'échéance de l'AMM suit son dernier renouvellement.
            _save_with_actor(amm, user, REASON)
        _reconcile(amm)
    return amm


def delete_period(binder: Binder, amm_id, renewal_id, *, move_to: str | None, user):
    """Annule un renouvellement saisi à tort (le plus récent seulement, comme sur la fiche AMM).

    Avec `move_to`, ses pièces sont rangées sur cette période au lieu d'être archivées : un
    renouvellement créé en double par un import ne fait pas perdre les scans qu'il portait.
    """
    with transaction.atomic():
        amm = _page(binder, amm_id, user)
        renewal = _renewal(amm, renewal_id)
        if move_to is not None:
            destination = _target_period(amm, move_to)
            if destination is not None and destination.pk == renewal.pk:
                raise ValidationError("Choisissez une autre période pour ranger les pièces.")
            for document in Document.objects.filter(
                renewal=renewal, is_current=True, archived_at__isnull=True
            ):
                document.renewal = destination
                document._history_user = user
                document._change_reason = REASON
                document._skip_signals = True
                document.save(update_fields=["renewal"])
        workflow.delete_renewal(renewal, actor=user)
        _reconcile(amm)
    return amm


def edit_document(binder: Binder, amm_id, document_id, *, values: dict, user):
    """Corrige la date ou le type d'une pièce, ou la range sur une autre période."""
    with transaction.atomic():
        amm = _page(binder, amm_id, user)
        document = _document(amm, document_id)
        fields = []
        if "period" in values:
            destination = _target_period(amm, values["period"])
            if document.renewal_id != (destination.pk if destination else None):
                document.renewal = destination
                fields.append("renewal")
        for field in ("document_date", "kind"):
            if field in values and values[field] != getattr(document, field):
                setattr(document, field, values[field])
                fields.append(field)
        if fields:
            document._history_user = user
            document._change_reason = REASON
            document._skip_signals = True
            document.save(update_fields=fields)
            _reconcile(amm)
    return amm


def remove_document(binder: Binder, amm_id, document_id, *, user):
    """Retire une pièce de la page : elle est archivée (l'historique la garde)."""
    if user.role not in REMOVE_ROLES:
        raise PermissionDenied("Seul un administrateur peut retirer une pièce.")
    with transaction.atomic():
        amm = _page(binder, amm_id, user)
        document = _document(amm, document_id)
        document.archived_at = timezone.now()
        document._history_user = user
        document._change_reason = "Pièce retirée depuis le classeur"
        document._skip_signals = True
        document.save(update_fields=["archived_at"])
        _reconcile(amm)
    return amm


def add_document(binder: Binder, amm_id, *, file, kind, document_date, period, user):
    """Ajoute une pièce sur une période précise, avec la date saisie (pas de lecture auto)."""
    amm = MarketingAuthorization.objects.select_related("country", "product__range").get(pk=amm_id)
    ensure_country_in_scope(user, amm.country)
    ensure_in_binder(binder, amm)
    renewal = _target_period(amm, period, lock=False)
    # ingest_document gère sa propre transaction (fichier écrit hors transaction) ; le signal du
    # document recalcule l'état du dossier.
    ingest_document(amm, file, kind, document_date=document_date, renewal=renewal, user=user)
    return amm
