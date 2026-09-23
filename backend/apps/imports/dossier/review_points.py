"""Points à vérifier plus tard : « Appliquer la valeur du scan » ou « Ignorer ».

Seule une action humaine remplace une valeur déjà enregistrée. L'application passe par la même
provenance que l'import (`DossierChange` : ancienne et nouvelle valeur, scan de preuve, auteur),
puis l'état de l'AMM (statut, échéance, complétude) est recalculé après commit.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.accounts.permissions import ALL_ROLES, ensure_country_in_scope
from apps.amm.models import MarketingAuthorization, Renewal
from apps.imports.models import DossierReviewPoint

from .application import (
    AMM_FIELDS,
    RENEWAL_FIELDS,
    _audit,
    _reconcile_after_commit,
    _save_with_actor,
    typed_value,
    value_json,
)

REASON = "Valeur du scan appliquée depuis les points à vérifier"


def _locked_point(point_id, user):
    point = (
        DossierReviewPoint.objects.select_for_update()
        .select_related("amm__country")
        .get(pk=point_id)
    )
    if not user.is_active or user.role not in ALL_ROLES:
        raise PermissionDenied()
    ensure_country_in_scope(user, point.amm.country)
    if point.status != DossierReviewPoint.Status.OPEN:
        raise ValidationError("Ce point a déjà été traité.")
    return point


def _close(point, user, status):
    point.status = status
    point.resolved_by = user
    point.resolved_at = timezone.now()
    point.save(update_fields=["status", "resolved_by", "resolved_at"])
    return point


def ignore_point(point_id, *, user):
    with transaction.atomic():
        point = _locked_point(point_id, user)
        return _close(point, user, DossierReviewPoint.Status.IGNORED)


def apply_point(point_id, *, user):
    """Remplace la valeur de la fiche par celle lue sur le scan, avec audit et recalcul."""
    with transaction.atomic():
        point = _locked_point(point_id, user)
        if not point.applicable:
            raise ValidationError("Ce point n'a pas de valeur de scan à appliquer.")
        amm = MarketingAuthorization.objects.select_for_update().get(pk=point.amm_id)
        if point.renewal_id:
            target = Renewal.objects.select_for_update().get(pk=point.renewal_id, amm=amm)
            allowed = RENEWAL_FIELDS
        else:
            target = amm
            allowed = AMM_FIELDS
        if point.field not in allowed:
            raise ValidationError("Ce champ ne peut pas être modifié depuis un point à vérifier.")
        if point.proof_file_id is None:
            raise ValidationError("Le scan de preuve de ce point n'existe plus.")
        old = value_json(getattr(target, point.field))
        new = point.scan_value
        if old != new:
            setattr(target, point.field, typed_value(point.field, new))
            if point.field in {"original_end_date", "end_date"}:
                setattr(target, point.field + "_manual", True)
            _save_with_actor(target, user, REASON)  # l'échéance non saisie suit la date de début
            start = target.original_start_date if target is amm else target.start_date
            end = target.original_end_date if target is amm else target.end_date
            if start and end and end < start:
                raise ValidationError("La date de fin précéderait la date de début.")
            _audit(
                point.batch,
                amm,
                target,
                point.field,
                old,
                new,
                point.proof_file,
                point.confidence,
                user,
                REASON,
            )
            if target is not amm:
                _save_with_actor(amm, user, REASON)
            transaction.on_commit(lambda: _reconcile_after_commit(amm.pk))
        return _close(point, user, DossierReviewPoint.Status.APPLIED)
