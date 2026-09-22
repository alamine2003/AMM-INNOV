"""Bilan d'un import de dossier validé : ce qui a changé, et qui en est prévenu.

Calculé après commit, une fois l'état de l'AMM recalculé : le bilan décrit l'état réel en base,
pas l'aperçu. Il est gardé sur le lot (`DossierImport.summary`) et notifié dans l'application
à l'auteur de l'import, au siège et aux réglementaires du pays.
"""

import logging

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.amm.models import MarketingAuthorization, Renewal
from apps.notifications.models import Notification
from apps.realtime.publisher import publish_user_event

from .projection import missing_scan_label

logger = logging.getLogger(__name__)

STATUS_LABELS = dict(MarketingAuthorization.Status.choices)
DOSSIER_LABELS = dict(MarketingAuthorization.DossierState.choices)
FIELD_LABELS = {
    "original_number": "N° d'AMM",
    "original_start_date": "date de délivrance",
    "original_end_date": "date d'échéance",
    "holder": "titulaire",
    "number": "n° de renouvellement",
    "start_date": "date de début",
    "end_date": "date de fin",
    "decision_date": "date de décision",
    "workflow_status": "statut du renouvellement",
}


def snapshot(amm) -> dict | None:
    """État de l'AMM à retenir avant la validation (None pour une AMM créée par l'import)."""
    if amm is None or amm.pk is None:
        return None
    return {
        "status": amm.status,
        "dossier_state": amm.dossier_state,
        "effective_end_date": _iso(amm.effective_end_date),
    }


def _iso(value):
    return value.isoformat() if value else None


def _fr(value):
    if not value:
        return "—"
    y, m, d = str(value)[:10].split("-")
    return f"{d}/{m}/{y}"


def _missing_scan(amm) -> str:
    """Pourquoi le dossier reste incomplet : la décision en vigueur n'a pas son scan."""
    return missing_scan_label(Renewal.objects.filter(amm=amm))


def build_summary(batch, before: dict | None) -> dict:
    amm = MarketingAuthorization.objects.select_related("product", "country").get(pk=batch.amm_id)
    audit = list(batch.audit.select_related("renewal").order_by("created_at"))
    renewals = {}
    fields = []
    for change in audit:
        if change.renewal_id and change.old_value is None:
            r = change.renewal
            renewals[r.pk] = {
                "number": r.number,
                "start_date": _iso(r.start_date),
                "end_date": _iso(r.end_date),
            }
            continue
        fields.append(
            {
                "target": "renewal" if change.renewal_id else "amm",
                "field": change.field,
                "label": FIELD_LABELS.get(change.field, change.field),
                "old": change.old_value,
                "new": change.new_value,
            }
        )
    documents = [
        {
            "title": f.document.title,
            "kind": f.document.kind,
            "period": "renewal" if f.document.renewal_id else "original",
        }
        for f in batch.files.select_related("document").order_by("relative_path")
        if f.document_id
    ]
    after = snapshot(amm)
    summary = {
        "amm_id": str(amm.pk),
        "product": amm.product.name,
        "country": amm.country.name,
        "country_iso2": amm.country.iso2,
        "number": amm.original_number,
        "created": before is None,
        "before": before,
        "after": after,
        "renewals_created": list(renewals.values()),
        "fields_changed": fields,
        "documents": documents,
        "missing_scan": (
            _missing_scan(amm)
            if amm.dossier_state == MarketingAuthorization.DossierState.INCOMPLET
            else None
        ),
    }
    summary["lines"] = summary_lines(summary)
    return summary


def summary_lines(s: dict) -> list[str]:
    before, after = s["before"] or {}, s["after"]
    lines = []
    if s["created"]:
        lines.append("AMM créée à partir du dossier.")
    for key, labels, name in (
        ("status", STATUS_LABELS, "Statut"),
        ("dossier_state", DOSSIER_LABELS, "Dossier"),
    ):
        old, new = before.get(key), after[key]
        if s["created"]:
            lines.append(f"{name} : {labels.get(new, new)}")
        elif old != new:
            lines.append(f"{name} : {labels.get(old, old)} → {labels.get(new, new)}")
    old_end, new_end = before.get("effective_end_date"), after["effective_end_date"]
    if old_end != new_end:
        lines.append(f"Échéance : {_fr(old_end)} → {_fr(new_end)}")
    for r in s["renewals_created"]:
        period = f"{_fr(r['start_date'])} → {_fr(r['end_date'])}"
        lines.append(f"Renouvellement n° {r['number'] or '?'} ajouté ({period})")
    for f in s["fields_changed"]:
        old = f["old"] if f["old"] not in (None, "") else "vide"
        lines.append(f"{f['label'].capitalize()} : {old} → {f['new']}")
    if s["documents"]:
        lines.append(f"{len(s['documents'])} document(s) rattaché(s)")
    if s["missing_scan"]:
        lines.append(f"Dossier toujours incomplet : il manque le {s['missing_scan']}.")
    if len(lines) == (1 if s["created"] else 0) and not s["documents"]:
        lines.append("Aucune modification : le dossier était déjà à jour.")
    return lines


def recipients(batch, amm) -> list[User]:
    """L'auteur de l'import, le siège, et les réglementaires du pays de l'AMM."""
    users = User.objects.filter(is_active=True).filter(
        Q(pk=batch.created_by_id) | Q(role__in=User.GLOBAL_ROLES) | Q(countries=amm.country_id)
    )
    return list(users.distinct())


def notify(batch, summary: dict) -> list[Notification]:
    amm = MarketingAuthorization.objects.select_related("country").get(pk=batch.amm_id)
    headline = next(
        (line for line in summary["lines"] if line.startswith(("Statut", "Dossier", "AMM créée"))),
        summary["lines"][0] if summary["lines"] else "",
    )
    title = f"Import de dossier : {summary['product']} ({summary['country_iso2']})"
    if headline:
        title = f"{title} — {headline}"[:255]
    who = batch.created_by
    author = (f"{who.first_name} {who.last_name}".strip() or who.email) if who else ""
    if batch.auto_applied:
        how = "validé automatiquement (lecture sûre, aucune donnée existante remplacée)"
        if author:
            how += f", import de {author}"
    else:
        how = f"validé{f' par {author}' if author else ''}"
    body = "\n".join(
        [
            f"Dossier « {batch.root_name} » {how}.",
            *summary["lines"],
        ]
    )
    link = f"{settings.FRONTEND_URL.rstrip('/')}/dossier-imports/{batch.pk}"
    created = []
    for user in recipients(batch, amm):
        notification = Notification.objects.create(
            user=user,
            channel=Notification.Channel.IN_APP,
            title=title,
            body=body,
            link=link,
            sent_at=timezone.now(),
        )
        created.append(notification)
        publish_user_event(user.pk, "notification.created", notification.pk, amm.country.iso2)
    return created


def record_and_notify(batch_id, before: dict | None) -> None:
    """Après commit : bilan puis notifications. Ne fait jamais échouer un import validé."""
    from apps.imports.models import DossierImport

    try:
        batch = DossierImport.objects.select_related("created_by").get(pk=batch_id)
        summary = build_summary(batch, before)
        DossierImport.objects.filter(pk=batch.pk).update(summary=summary)
        notify(batch, summary)
    except Exception:  # noqa: BLE001 — le bilan est informatif, l'import reste validé
        logger.exception("Bilan ou notification de l'import de dossier %s en échec", batch_id)
