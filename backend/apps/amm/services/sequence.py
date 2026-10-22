"""N° d'ordre des renouvellements, tenu dans l'ordre des dates."""

from datetime import date

from apps.amm.models import Renewal


def _sequence_key(renewal: Renewal):
    when = renewal.start_date or renewal.decision_date or renewal.filing_date
    still_open = renewal.workflow_status in Renewal.OPEN_STATUSES
    return (still_open, when or date.max, renewal.sequence or 0)


def resequence(amm) -> bool:
    """Renumérote les renouvellements dans l'ordre des dates (dossiers en cours à la fin).

    `current_decision` retient le renouvellement obtenu de plus grand n° d'ordre : une décision
    ancienne ajoutée ou redatée après coup ne doit pas devenir « la dernière ».
    """
    renewals = list(Renewal.objects.filter(amm=amm))
    ordered = sorted(renewals, key=_sequence_key)
    if [r.pk for r in ordered] == [r.pk for r in sorted(renewals, key=lambda r: r.sequence)]:
        return False
    offset = max(r.sequence for r in renewals) + len(renewals) + 1
    for index, renewal in enumerate(ordered, start=1):  # deux temps : (amm, sequence) unique
        Renewal.objects.filter(pk=renewal.pk).update(sequence=offset + index)
    for index, renewal in enumerate(ordered, start=1):
        Renewal.objects.filter(pk=renewal.pk).update(sequence=index)
    return True
