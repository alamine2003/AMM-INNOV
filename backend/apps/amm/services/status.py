"""Single source of truth for the computed state of an AMM (status, urgency, dates, dossier).

Transcription of the workbook formula:
- end = end_date of the most recent OBTENU renewal with an end date, else original_end_date;
- pending = a renewal is DEPOSE or EN_INSTRUCTION;
- end None -> IN_PROCESS if pending else INDETERMINE;
- end >= today -> VALIDE; else IN_PROCESS if pending else EXPIRE.

The dossier state follows the proof, not a declaration: the decision in force is the renewal
that carries `end` (or the original AMM when no renewal does), and the dossier is complete when
that decision has its scan attached.
"""

from dataclasses import dataclass
from datetime import date

from dateutil.relativedelta import relativedelta

from apps.core.dates import today as reference_today

STATUS_VALIDE = "VALIDE"
STATUS_EXPIRE = "EXPIRE"
STATUS_IN_PROCESS = "IN_PROCESS"
STATUS_INDETERMINE = "INDETERMINE"

URGENCY_OK = "OK"
URGENCY_A_PLANIFIER = "A_PLANIFIER"
URGENCY_DEPOT_URGENT = "DEPOT_URGENT"
URGENCY_CRITIQUE = "CRITIQUE"
URGENCY_EXPIRE = "EXPIRE"
URGENCY_EN_INSTRUCTION = "EN_INSTRUCTION"

DOSSIER_COMPLET = "COMPLET"
DOSSIER_INCOMPLET = "INCOMPLET"

PENDING = ("DEPOSE", "EN_INSTRUCTION")


@dataclass(frozen=True)
class AmmState:
    effective_end_date: date | None
    filing_deadline: date | None
    status: str
    urgency: str
    dossier_state: str = DOSSIER_INCOMPLET
    pending: bool = False

    def apply_to(self, amm) -> None:
        amm.effective_end_date = self.effective_end_date
        amm.filing_deadline = self.filing_deadline
        amm.status = self.status
        amm.urgency = self.urgency
        amm.dossier_state = self.dossier_state

    def differs_from(self, amm) -> bool:
        return (
            amm.effective_end_date != self.effective_end_date
            or amm.filing_deadline != self.filing_deadline
            or amm.status != self.status
            or amm.urgency != self.urgency
            or amm.dossier_state != self.dossier_state
        )


def derive_urgency(status: str, end: date | None, pending: bool, today: date) -> str:
    if status == STATUS_EXPIRE:
        return URGENCY_EXPIRE
    if pending:
        return URGENCY_EN_INSTRUCTION
    if end is None:
        return URGENCY_A_PLANIFIER
    remaining = (end - today).days
    if remaining <= 90:
        return URGENCY_CRITIQUE
    if remaining <= 180:
        return URGENCY_DEPOT_URGENT
    if remaining <= 365:
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


def compute_amm_state(amm, today: date | None = None, renewals=None, documents=None) -> AmmState:
    """Computes the state without writing it. `renewals`/`documents` avoid queries."""
    today = today or reference_today()
    if renewals is None:
        # Relecture de la base : `amm.renewals.all()` peut servir le prefetch de la vue
        # appelante, obsolète dès qu'un renouvellement vient d'être créé ou modifié. Les
        # traitements de masse qui détiennent un prefetch à jour passent `renewals`.
        from apps.amm.models import Renewal

        renewals = list(Renewal.objects.filter(amm_id=amm.pk)) if amm.pk else []
    obtained = [r for r in renewals if r.workflow_status == "OBTENU" and r.end_date]
    last = max(obtained, key=lambda r: r.sequence) if obtained else None
    pending = any(r.workflow_status in PENDING for r in renewals)

    if last is not None:
        end = last.end_date
    elif amm.original_end_date:
        end = amm.original_end_date
    else:
        end = None

    if end is None:
        status = STATUS_IN_PROCESS if pending else STATUS_INDETERMINE
    elif end >= today:
        status = STATUS_VALIDE
    else:
        status = STATUS_IN_PROCESS if pending else STATUS_EXPIRE

    lead_months = amm.country.filing_lead_months if amm.country_id else 6
    deadline = end - relativedelta(months=lead_months) if end else None
    urgency = derive_urgency(status, end, pending, today)
    dossier = derive_dossier_state(amm, last, documents)
    return AmmState(end, deadline, status, urgency, dossier, pending)


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
        filing_deadline=state.filing_deadline,
        dossier_state=state.dossier_state,
    )
    return True
