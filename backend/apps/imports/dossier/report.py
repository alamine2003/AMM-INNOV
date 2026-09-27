"""Récapitulatif des imports de dossiers : ce que l'application a organisé, corrigé et créé seule,
et uniquement ce qui demande réellement une intervention.

Calculé à la demande sur les lots visibles par l'utilisateur, pour une période (par défaut les
7 derniers jours). Rien n'est écrit : le récapitulatif lit les bilans (`DossierImport.summary`),
les questions restantes et les points ouverts qui exigent une action.
"""

from datetime import timedelta

from django.utils import timezone

from apps.imports.models import DossierImport, DossierReviewPoint

# Points qui exigent une action : fiche créée sans n° ni date lisibles, aucune décision lisible.
ATTENTION_CODES = {"incomplete", "unreadable"}


def _identity(batch) -> dict:
    summary = batch.summary or {}
    preview = batch.preview or {}
    amm = preview.get("amm") or {}
    return {
        "batch_id": str(batch.pk),
        "folder": batch.root_name,
        "amm_id": summary.get("amm_id") or (str(batch.amm_id) if batch.amm_id else None),
        "product": summary.get("product") or amm.get("product_name") or "",
        "country_iso2": summary.get("country_iso2") or amm.get("country_iso2") or "",
    }


def build_report(queryset, *, days: int = 7) -> dict:
    since = timezone.now() - timedelta(days=days)
    batches = list(
        queryset.filter(created_at__gte=since).select_related("country").order_by("-created_at")
    )
    open_points = {}
    for point in (
        DossierReviewPoint.objects.filter(
            batch__in=[batch.pk for batch in batches],
            status=DossierReviewPoint.Status.OPEN,
            code__in=ATTENTION_CODES,
        )
        .select_related("amm")
        .order_by("created_at")
    ):
        amm = point.amm
        # Sans décision lisible, rien à faire si la fiche a déjà son n° et sa date d'origine :
        # les scans y sont rangés comme autres documents.
        if point.code == "unreadable" and amm.original_number and amm.original_start_date:
            continue
        # Un seul signalement par dossier : la fiche est à compléter.
        open_points.setdefault(point.batch_id, point.message)

    filed, corrections, created, decisions, attention = [], [], [], [], []
    totals = {
        "folders": len(batches),
        "filed": 0,
        "created": 0,
        "corrected": 0,
        "completed": 0,
        "documents": 0,
        "renewals": 0,
        "decisions": 0,
        "attention": 0,
        "in_progress": 0,
    }
    for batch in batches:
        who = _identity(batch)
        if batch.status in {DossierImport.Status.PENDING, DossierImport.Status.RUNNING}:
            totals["in_progress"] += 1
            continue
        if batch.status == DossierImport.Status.QUESTION:
            reasons = ((batch.preview or {}).get("question") or {}).get("reasons") or []
            attention.append(
                {**who, "kind": "question", "reason": " ".join(reasons) or "AMM non identifiée."}
            )
            continue
        if batch.status == DossierImport.Status.FAILED:
            attention.append(
                {**who, "kind": "failed", "reason": batch.error or "L'analyse a échoué."}
            )
            continue
        if batch.status == DossierImport.Status.READY:
            attention.append(
                {
                    **who,
                    "kind": "ready",
                    "reason": "Analysé mais pas rangé automatiquement : relancez l'analyse.",
                }
            )
            continue
        summary = batch.summary or {}
        fields = summary.get("fields_changed") or []
        fixed = [field for field in fields if field.get("corrected")]
        filled = [field for field in fields if not field.get("corrected")]
        documents = len(summary.get("documents") or [])
        renewals = len(summary.get("renewals_created") or [])
        chosen = list(summary.get("decisions") or (batch.preview or {}).get("decisions") or [])
        totals["filed"] += 1
        totals["documents"] += documents
        totals["renewals"] += renewals
        totals["completed"] += len(filled)
        totals["corrected"] += len(fixed)
        totals["decisions"] += len(chosen)
        filed.append(
            {
                **who,
                "created": bool(summary.get("created")),
                "documents": documents,
                "renewals": renewals,
                "completed": len(filled),
                "corrected": len(fixed),
                "status_after": (summary.get("after") or {}).get("status"),
                "lines": summary.get("lines") or [],
            }
        )
        if summary.get("created"):
            totals["created"] += 1
            created.append({**who, "number": summary.get("number") or ""})
        for field in fixed:
            corrections.append(
                {
                    **who,
                    "label": field.get("label") or field.get("field"),
                    "old": field.get("old"),
                    "new": field.get("new"),
                }
            )
        for message in chosen:
            if " corrigé d'après la décision" in message:
                continue  # déjà dans les corrections
            decisions.append({**who, "message": message})
        if batch.pk in open_points:
            attention.append({**who, "kind": "incomplete", "reason": open_points[batch.pk]})
    totals["attention"] = len(attention)
    return {
        "days": days,
        "since": since.isoformat(),
        "totals": totals,
        "attention": attention,
        "created": created,
        "corrections": corrections,
        "decisions": decisions,
        "filed": filed,
    }
