"""Chronologie d'une page du classeur : périodes de validité, pièces et manques, telle
qu'affichée (fenêtre « Chronologie », PDF). Les modifications sont dans `chronology.py`."""

from datetime import timedelta

from apps.documents.models import Document

# Au-delà, deux périodes qui ne se suivent pas laissent un trou dans la validité.
GAP_TOLERANCE = timedelta(days=31)


def _document(doc) -> dict:
    return {
        "document_id": str(doc.pk),
        "kind": doc.kind,
        "kind_label": doc.get_kind_display(),
        "document_date": doc.document_date,
        "title": doc.title,
        "page_count": doc.page_count,
    }


def ignored_gaps(amm) -> set:
    return {(gap.start_date, gap.end_date) for gap in amm.ignored_gaps.all()}


def chronology(amm, renewals, documents, ignored=frozenset()) -> list[dict]:
    """De la décision la plus récente à l'AMM d'origine : pièces de chaque période et manques.

    Chaque période porte ses décisions scannées et ses autres pièces (récépissés, courriers) ;
    `issues` dit ce qui manque et comment le régler. Entre deux périodes obtenues qui ne se
    suivent pas, une entrée « gap » signale une interruption de validité (renouvellement absent
    de l'application, ou décision non classée).
    """
    by_period: dict = {}
    for doc in documents:
        by_period.setdefault(doc.renewal_id, []).append(doc)

    def entry(kind, label, renewal=None) -> dict:
        docs = by_period.get(renewal.pk if renewal else None, [])
        decisions = [d for d in docs if d.kind == Document.Kind.AMM]
        others = [d for d in docs if d.kind != Document.Kind.AMM]
        start = renewal.start_date if renewal else amm.original_start_date
        end = renewal.end_date if renewal else amm.original_end_date
        number = renewal.number if renewal else amm.original_number
        issues = []
        if kind == "closed":
            pass  # rejeté ou abandonné : aucune décision n'a été délivrée, rien ne manque
        elif kind == "pending":
            if not any(d.kind == Document.Kind.RECEPISSE for d in docs):
                issues.append(
                    {
                        "code": "no_receipt",
                        "message": "Récépissé de dépôt non scanné : importez-le sur la fiche AMM.",
                    }
                )
        else:
            if not decisions:
                issues.append(
                    {
                        "code": "no_scan",
                        "message": "Décision non scannée : importez le scan de cette décision.",
                    }
                )
            if not start:
                issues.append(
                    {
                        "code": "no_date",
                        "message": "Date de début inconnue : relevez-la sur la décision papier.",
                    }
                )
            if not number:
                issues.append(
                    {
                        "code": "no_number",
                        "message": "N° d'AMM inconnu : relevez-le sur la décision.",
                    }
                )
        return {
            "kind": kind,
            "label": label,
            "renewal_id": str(renewal.pk) if renewal else None,
            "sequence": renewal.sequence if renewal else 0,
            "workflow_status": renewal.workflow_status if renewal else None,
            "workflow_label": renewal.get_workflow_status_display() if renewal else None,
            "number": number,
            "start_date": start,
            "end_date": end,
            "filing_date": renewal.filing_date if renewal else None,
            "decisions": [_document(d) for d in sorted(decisions, key=lambda d: d.document_date)],
            "others": [_document(d) for d in others],
            "issues": issues,
        }

    periods = [entry("origin", "AMM d'origine")]
    pending = []
    for renewal in sorted(renewals, key=lambda r: r.sequence):
        if renewal.workflow_status == "OBTENU":
            periods.append(entry("renewal", f"Renouvellement {renewal.sequence}", renewal))
        elif renewal.is_pending:
            pending.append(entry("pending", f"Renouvellement {renewal.sequence} en cours", renewal))
        elif renewal.workflow_status in ("REJETE", "ABANDONNE"):
            periods.append(entry("closed", f"Renouvellement {renewal.sequence}", renewal))
    # Interruptions de validité entre deux décisions obtenues successives.
    timeline: list[dict] = []
    previous = None
    for period in periods:
        if period["kind"] == "closed":
            timeline.append(period)
            continue
        if previous and previous["end_date"] and period["start_date"]:
            if period["start_date"] - previous["end_date"] > GAP_TOLERANCE:
                # Ignorée par l'archiviste : il n'y a pas de renouvellement manquant (période
                # sans AMM). Visible, mais on ne force pas l'ajout d'un passage qui n'existe pas.
                skipped = (previous["end_date"], period["start_date"]) in ignored
                timeline.append(
                    {
                        "kind": "gap",
                        "label": "Interruption de validité" + (" (ignorée)" if skipped else ""),
                        "start_date": previous["end_date"],
                        "end_date": period["start_date"],
                        "ignored": skipped,
                        "issues": []
                        if skipped
                        else [
                            {
                                "code": "gap",
                                "message": (
                                    "Aucune décision ne couvre cette période : un renouvellement "
                                    "manque peut-être. Importez sa décision, corrigez sur le "
                                    "classeur papier, ou ignorez ce trou s'il n'y a pas eu de "
                                    "renouvellement."
                                ),
                            }
                        ],
                    }
                )
        timeline.append(period)
        # Une période sans date de fin ne sert pas de repère : sinon un trou après elle passerait
        # inaperçu (elle signale déjà sa date manquante).
        if period["end_date"] or previous is None:
            previous = period
    timeline.extend(pending)
    timeline.reverse()  # la plus récente en haut
    return timeline
