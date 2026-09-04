"""Renewal state machine (section 5.4 of the architecture document)."""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.amm.models import Renewal

S = Renewal.WorkflowStatus

TRANSITIONS: dict[str, set[str]] = {
    S.PLANIFIE: {S.EN_PREPARATION, S.ABANDONNE},
    S.EN_PREPARATION: {S.DEPOSE, S.ABANDONNE},
    S.DEPOSE: {S.EN_INSTRUCTION, S.OBTENU, S.ABANDONNE},
    S.EN_INSTRUCTION: {S.OBTENU, S.REJETE, S.ABANDONNE},
    S.OBTENU: set(),
    S.REJETE: set(),
    S.ABANDONNE: set(),
}

REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    S.DEPOSE: ("filing_date",),
    S.OBTENU: ("number", "start_date"),
}

EDITABLE_FIELDS = (
    "filing_date",
    "decision_date",
    "number",
    "start_date",
    "end_date",
    "end_date_manual",
    "notes",
)


def allowed_transitions(renewal: Renewal) -> set[str]:
    return set(TRANSITIONS.get(renewal.workflow_status, set()))


def can_transition(renewal: Renewal, to: str) -> bool:
    return to in allowed_transitions(renewal)


def missing_fields(renewal: Renewal, to: str, fields: dict) -> list[str]:
    missing = []
    for name in REQUIRED_FIELDS.get(to, ()):
        value = fields.get(name, getattr(renewal, name))
        if value in (None, ""):
            missing.append(name)
    return missing


@transaction.atomic
def transition(renewal: Renewal, to: str, actor=None, **fields) -> Renewal:
    """Moves a renewal to `to`, applying `fields`. Raises ValidationError when refused."""
    if to not in S.values:
        raise ValidationError({"to": f"Statut inconnu : {to}."})
    if not can_transition(renewal, to):
        possible = ", ".join(sorted(allowed_transitions(renewal))) or "aucune"
        raise ValidationError(
            {
                "to": (
                    f"Transition {renewal.workflow_status} → {to} non autorisée. "
                    f"Transitions possibles : {possible}."
                )
            }
        )
    missing = missing_fields(renewal, to, fields)
    if missing:
        raise ValidationError({name: f"Champ requis pour passer à {to}." for name in missing})
    for name in EDITABLE_FIELDS:
        if name in fields and fields[name] is not None:
            setattr(renewal, name, fields[name])
    if "end_date" in fields and fields["end_date"] is not None:
        renewal.end_date_manual = True
    if to in (S.OBTENU, S.REJETE) and not renewal.decision_date and fields.get("decision_date"):
        renewal.decision_date = fields["decision_date"]
    previous = renewal.workflow_status
    renewal.workflow_status = to
    renewal._transition_from = previous
    renewal._transition_actor = actor
    if actor is not None:
        renewal._history_user = actor
    renewal.save()
    return renewal
