"""Single source of truth for the computed state of an AMM (status, urgency, dates, dossier).

Règles métier (voir docs/workflow-amm.md) :
- fin = date de fin du dernier renouvellement OBTENU et daté, sinon date de fin d'origine ;
  un renouvellement non obtenu (planifié, déposé, en instruction, rejeté…) est ignoré ;
- pas de date de fin -> INDETERMINE (« Échéance inconnue » : donnée manquante) ;
- aujourd'hui > fin -> EXPIRE, même si un dépôt est en cours ;
- aujourd'hui >= fin - 6 mois -> A_RENOUVELER (toujours valide) ;
- sinon VALIDE.
- dépôt idéal = fin - 6 mois (objectif interne) ; limite agence = fin - 3 mois.

The dossier state follows the proof, not a declaration nor the validity: the decision in force
is the renewal that carries `end` (or the original AMM when no renewal does), and the dossier is
complete when that decision has its scan attached.
"""

from dataclasses import dataclass
from datetime import date

from dateutil.relativedelta import relativedelta

from apps.core.dates import today as reference_today

STATUS_VALIDE = "VALIDE"
STATUS_A_RENOUVELER = "A_RENOUVELER"
STATUS_EXPIRE = "EXPIRE"
STATUS_INDETERMINE = "INDETERMINE"
# Statuts d'une AMM en vigueur (non expirée) : « À renouveler » reste valide.
IN_FORCE_STATUSES = (STATUS_VALIDE, STATUS_A_RENOUVELER)

URGENCY_OK = "OK"
URGENCY_A_PLANIFIER = "A_PLANIFIER"
URGENCY_DEPOT_URGENT = "DEPOT_URGENT"
URGENCY_CRITIQUE = "CRITIQUE"
URGENCY_EXPIRE = "EXPIRE"

DOSSIER_COMPLET = "COMPLET"
DOSSIER_INCOMPLET = "INCOMPLET"

PENDING = ("DEPOSE", "EN_INSTRUCTION")

# Règle 3 et 4 du responsable.
RENEWAL_WINDOW_MONTHS = 6  # « À renouveler » dans les six mois précédant l'expiration
IDEAL_FILING_MONTHS = 6  # dépôt idéal (objectif interne)
AGENCY_FILING_MONTHS = 3  # limite de l'agence
PLANNING_HORIZON_DAYS = 365  # urgence « À planifier » (règle d'alerte J-365 conservée)


@dataclass(frozen=True)
class AmmState:
    effective_end_date: date | None
    ideal_filing_date: date | None
    agency_filing_deadline: date | None
    status: str
    urgency: str
    dossier_state: str = DOSSIER_INCOMPLET
    pending: bool = False

    def apply_to(self, amm) -> None:
        amm.effective_end_date = self.effective_end_date
        amm.ideal_filing_date = self.ideal_filing_date
        amm.agency_filing_deadline = self.agency_filing_deadline
        amm.status = self.status
        amm.urgency = self.urgency
        amm.dossier_state = self.dossier_state

    def differs_from(self, amm) -> bool:
        return (
            amm.effective_end_date != self.effective_end_date
            or amm.ideal_filing_date != self.ideal_filing_date
            or amm.agency_filing_deadline != self.agency_filing_deadline
            or amm.status != self.status
            or amm.urgency != self.urgency
            or amm.dossier_state != self.dossier_state
        )


def ideal_filing_date(end: date | None) -> date | None:
    return end - relativedelta(months=IDEAL_FILING_MONTHS) if end else None


def agency_filing_deadline(end: date | None) -> date | None:
    return end - relativedelta(months=AGENCY_FILING_MONTHS) if end else None


def derive_status(end: date | None, today: date) -> str:
    """Statut de validité, fonction de la seule date de fin de l'AMM actuelle."""
    if end is None:
        return STATUS_INDETERMINE
    if today > end:
        return STATUS_EXPIRE
    if today >= end - relativedelta(months=RENEWAL_WINDOW_MONTHS):
        return STATUS_A_RENOUVELER
    return STATUS_VALIDE


def derive_urgency(status: str, end: date | None, today: date) -> str:
    """Urgence de dépôt, alignée sur les dates du responsable (aucune règle en plus) :
    limite agence atteinte -> CRITIQUE ; dépôt idéal atteint -> DEPOT_URGENT ;
    échéance sous un an -> A_PLANIFIER ; expirée -> EXPIRE. Un dépôt en cours ne la masque plus.
    """
    if status == STATUS_EXPIRE:
        return URGENCY_EXPIRE
    if end is None:
        return URGENCY_A_PLANIFIER
    if today >= agency_filing_deadline(end):
        return URGENCY_CRITIQUE
    if today >= ideal_filing_date(end):
        return URGENCY_DEPOT_URGENT
    if (end - today).days <= PLANNING_HORIZON_DAYS:
        return URGENCY_A_PLANIFIER
    return URGENCY_OK


def current_scans_prefetch(to_attr: str = "current_scans"):
    """Prefetch of the AMM decision scans, for the batches that recompute many AMM at once."""
    from django.db.models import Prefetch

    from apps.documents.models import Document

    return Prefetch(
        "documents",
        queryset=Document.objects.filter(
            kind=Document.Kind.AMM, is_current=True, archived_at__isnull=True
        ).only("id", "amm_id", "renewal_id"),
        to_attr=to_attr,
    )


def derive_dossier_state(amm, decision, documents=None) -> str:
    """COMPLET when the decision in force carries its scan; INCOMPLET otherwise.

    `decision` is the renewal that sets the effective end date, or None for the original AMM.
    `documents` may be passed by callers that already hold an up-to-date list.
    Never depends on the validity: an expired AMM whose decision is scanned stays COMPLET.
    """
    from apps.documents.models import Document

    if amm.pk is None:
        return DOSSIER_INCOMPLET
    if documents is None:
        documents = Document.objects.filter(
            amm_id=amm.pk, kind=Document.Kind.AMM, is_current=True, archived_at__isnull=True
        )
    renewal_id = decision.pk if decision is not None else None
    proven = any(document.renewal_id == renewal_id for document in documents)
    return DOSSIER_COMPLET if proven else DOSSIER_INCOMPLET


def current_decision(renewals):
    """Le dernier renouvellement OBTENU et daté (document actuel), ou None pour l'origine."""
    obtained = [r for r in renewals if r.workflow_status == "OBTENU" and r.end_date]
    return max(obtained, key=lambda r: r.sequence) if obtained else None


def compute_amm_state(amm, today: date | None = None, renewals=None, documents=None) -> AmmState:
    """Computes the state without writing it. `renewals`/`documents` avoid queries."""
    today = today or reference_today()
    if renewals is None:
        # Relecture de la base : `amm.renewals.all()` peut servir le prefetch de la vue
        # appelante, obsolète dès qu'un renouvellement vient d'être créé ou modifié. Les
        # traitements de masse qui détiennent un prefetch à jour passent `renewals`.
        from apps.amm.models import Renewal

        renewals = list(Renewal.objects.filter(amm_id=amm.pk)) if amm.pk else []
    last = current_decision(renewals)
    pending = any(r.workflow_status in PENDING for r in renewals)
    end = last.end_date if last is not None else amm.original_end_date

    status = derive_status(end, today)
    return AmmState(
        effective_end_date=end,
        ideal_filing_date=ideal_filing_date(end),
        agency_filing_deadline=agency_filing_deadline(end),
        status=status,
        urgency=derive_urgency(status, end, today),
        dossier_state=derive_dossier_state(amm, last, documents),
        pending=pending,
    )


def apply_state(amm, today: date | None = None, save: bool = True) -> AmmState:
    """Recomputes and persists the state of an AMM (creates a history entry when saved)."""
    state = compute_amm_state(amm, today=today)
    state.apply_to(amm)
    if save:
        amm.save()
    return state


def recompute_quietly(amm, today: date | None = None, renewals=None, documents=None) -> bool:
    """Recomputes and writes with `update()` (no signal, no history). Returns True if changed."""
    from apps.amm.models import MarketingAuthorization

    state = compute_amm_state(amm, today=today, renewals=renewals, documents=documents)
    if not state.differs_from(amm):
        return False
    state.apply_to(amm)
    MarketingAuthorization.objects.filter(pk=amm.pk).update(
        status=state.status,
        urgency=state.urgency,
        effective_end_date=state.effective_end_date,
        ideal_filing_date=state.ideal_filing_date,
        agency_filing_deadline=state.agency_filing_deadline,
        dossier_state=state.dossier_state,
    )
    return True
