"""Renewal state machine (section 5.4 of the architecture document)."""

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.amm.models import MarketingAuthorization, Renewal

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
def create_renewal(amm: MarketingAuthorization, actor=None, **fields) -> Renewal:
    """Enregistre un renouvellement pour `amm`, en une seule étape.

    Une décision déjà délivrée se saisit telle quelle : dès qu'une date de début est fournie, le
    renouvellement est « Obtenu » sans repasser par le workflow. `Renewal.save()` en dérive
    l'échéance à partir de la durée de validité du pays, et le signal post-save recalcule l'AMM —
    une AMM expirée redevient valide d'elle-même.

    Si un renouvellement est déjà ouvert, la décision le conclut au lieu d'être refusée : c'est le
    même renouvellement qui aboutit, il garde son n° d'ordre et sa date de dépôt. Seul le fait
    d'en planifier un second alors qu'un autre est ouvert reste refusé.

    Sans date de début, on planifie : le workflow reste disponible pour suivre un dépôt en cours.

    La ligne AMM est verrouillée le temps de la transaction pour que deux requêtes simultanées ne
    créent pas deux renouvellements (et que `sequence` reste unique).
    """
    MarketingAuthorization.objects.select_for_update().get(pk=amm.pk)
    fields.setdefault(
        "workflow_status", S.OBTENU if fields.get("start_date") else S.PLANIFIE
    )
    open_renewal = (
        Renewal.objects.filter(amm=amm, workflow_status__in=Renewal.OPEN_STATUSES)
        .order_by("-sequence")
        .first()
    )
    if open_renewal is not None and fields["workflow_status"] != S.OBTENU:
        raise ValidationError(
            {
                "detail": (
                    f"Le renouvellement n°{open_renewal.sequence} est déjà en cours "
                    f"({open_renewal.get_workflow_status_display()}) : renseignez sa décision "
                    "au lieu d'en planifier un second."
                )
            }
        )
    if open_renewal is not None:
        renewal = open_renewal
        renewal._transition_from = renewal.workflow_status
        for name, value in fields.items():
            # Une valeur vide ne vient pas effacer ce que le renouvellement porte déjà : la
            # décision complète le dépôt, elle ne le remplace pas.
            if value not in (None, "") or not getattr(renewal, name):
                setattr(renewal, name, value)
    else:
        renewal = Renewal(amm=amm, **fields)
    if actor is not None:
        renewal._history_user = actor
        # Propagates the actor to the AMM recomputed by the post-save signal.
        renewal._transition_actor = actor
    renewal.save()
    return renewal


@transaction.atomic
def transition(renewal: Renewal, to: str, actor=None, **fields) -> Renewal:
    """Moves a renewal to `to`, applying `fields`. Raises ValidationError when refused.

    The renewal row is locked and re-read first: two users acting at the same time on the
    same renewal (one files it, the other abandons it) cannot both succeed.
    """
    if to not in S.values:
        raise ValidationError({"to": f"Statut inconnu : {to}."})
    list(Renewal.objects.select_for_update().filter(pk=renewal.pk).values("pk"))  # verrou ligne
    renewal.refresh_from_db(fields=["workflow_status"])
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
