"""Single source of truth for the computed state of an AMM (status, urgency, dates).

Transcription of the workbook formula:
- end = end_date of the most recent OBTENU renewal with an end date, else original_end_date;
- pending = a renewal is DEPOSE or EN_INSTRUCTION;
- end None -> IN_PROCESS if pending else INDETERMINE;
- end >= today -> VALIDE; else IN_PROCESS if pending else EXPIRE.
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

PENDING = ("DEPOSE", "EN_INSTRUCTION")


@dataclass(frozen=True)
class AmmState:
    effective_end_date: date | None
    filing_deadline: date | None
    status: str
    urgency: str
    pending: bool = False

    def apply_to(self, amm) -> None:
        amm.effective_end_date = self.effective_end_date
        amm.filing_deadline = self.filing_deadline
        amm.status = self.status
        amm.urgency = self.urgency

    def differs_from(self, amm) -> bool:
        return (
            amm.effective_end_date != self.effective_end_date
            or amm.filing_deadline != self.filing_deadline
            or amm.status != self.status
            or amm.urgency != self.urgency
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


def compute_amm_state(amm, today: date | None = None, renewals=None) -> AmmState:
    """Computes the state without writing it. `renewals` may be passed to avoid queries."""
    today = today or reference_today()
    if renewals is None:
        renewals = list(amm.renewals.all()) if amm.pk else []
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
    return AmmState(end, deadline, status, urgency, pending)


def apply_state(amm, today: date | None = None, save: bool = True) -> AmmState:
    """Recomputes and persists the state of an AMM (creates a history entry when saved)."""
    state = compute_amm_state(amm, today=today)
    state.apply_to(amm)
    if save:
        amm.save()
    return state


def recompute_quietly(amm, today: date | None = None) -> bool:
    """Recomputes and writes with `update()` (no signal, no history). Returns True if changed."""
    from apps.amm.models import MarketingAuthorization

    state = compute_amm_state(amm, today=today)
    if not state.differs_from(amm):
        return False
    state.apply_to(amm)
    MarketingAuthorization.objects.filter(pk=amm.pk).update(
        status=state.status,
        urgency=state.urgency,
        effective_end_date=state.effective_end_date,
        filing_deadline=state.filing_deadline,
    )
    return True
