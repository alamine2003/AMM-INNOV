"""Les classeurs papier, reconstitués depuis les AMM.

Un classeur par pays, avec un intercalaire par gamme (Générale → Cardio → Bien-être), sauf au
siège (Sénégal) où chaque gamme a son classeur et la Générale est coupée en A-K et L-Z. Dans
chaque gamme, une page par AMM, dans l'ordre alphabétique du nom de produit : l'ordre des
classeurs papier, pas celui des lignes de l'Excel (des produits y ont été ajoutés plus tard).

Rien n'est stocké : ajouter une AMM ou changer la gamme d'un produit met les classeurs à jour.
"""

import unicodedata
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Prefetch
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.amm.models import MarketingAuthorization, Renewal
from apps.catalog.models import Country
from apps.documents.models import Document
from apps.imports.models import DossierReviewPoint

NO_RANGE = ""
RANGE_ORDER = ("GENERALE", "CARDIO", "BIEN_ETRE", NO_RANGE)
RANGE_LABELS = {
    "GENERALE": "Générale",
    "CARDIO": "Cardio",
    "BIEN_ETRE": "Bien-être",
    NO_RANGE: "Sans gamme",
}
# Couleurs des onglets d'intercalaires (reprises par l'interface et le PDF).
RANGE_COLORS = {
    "GENERALE": "#1f5fbf",
    "CARDIO": "#c62828",
    "BIEN_ETRE": "#2e7d32",
    NO_RANGE: "#6b7280",
}

# Champs d'une page, par bloc : nom affiché → champ du modèle.
SLOT_FIELDS = {
    "original": {
        "number": "original_number",
        "start_date": "original_start_date",
        "end_date": "original_end_date",
    },
    "renewal": {"number": "number", "start_date": "start_date", "end_date": "end_date"},
}
AMM_FIELD_SLOTS = {model: name for name, model in SLOT_FIELDS["original"].items()}


@dataclass(frozen=True)
class Part:
    """Un classeur d'un pays dont les gammes sont rangées dans des classeurs séparés."""

    slug: str
    title: str
    ranges: tuple[str, ...]
    letters: str = ""  # "AK" ou "LZ" : première lettre du produit


# Pays dont chaque gamme a son propre classeur papier : le siège.
SPLIT_COUNTRIES = {
    "SN": (
        Part("generale-a-k", "Générale A-K", ("GENERALE", NO_RANGE), "AK"),
        Part("generale-l-z", "Générale L-Z", ("GENERALE", NO_RANGE), "LZ"),
        Part("cardio", "Cardio", ("CARDIO",)),
        Part("bien-etre", "Bien-être", ("BIEN_ETRE",)),
    )
}
HEADQUARTERS = "SN"


def sort_name(name: str) -> str:
    """Clé de tri alphabétique : sans accents, en majuscules, espaces réduits."""
    plain = unicodedata.normalize("NFKD", name or "")
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return " ".join(plain.upper().split())


def letter_bucket(name: str) -> str:
    first = next((char for char in sort_name(name) if char.isalnum()), "A")
    return "LZ" if "L" <= first <= "Z" else "AK"


@dataclass(frozen=True)
class Binder:
    country: Country
    part: Part | None = None

    @property
    def key(self) -> str:
        return f"{self.country.iso2}-{self.part.slug}" if self.part else self.country.iso2

    @property
    def title(self) -> str:
        return self.part.title if self.part else "Toutes gammes"

    @property
    def ranges(self) -> tuple[str, ...]:
        return self.part.ranges if self.part else RANGE_ORDER

    def contains(self, range_code: str | None, product_name: str) -> bool:
        code = range_code or NO_RANGE
        if code not in self.ranges:
            return False
        return not (self.part and self.part.letters) or (
            letter_bucket(product_name) == self.part.letters
        )


def binders_of(country: Country) -> list[Binder]:
    parts = SPLIT_COUNTRIES.get(country.iso2)
    return [Binder(country, part) for part in parts] if parts else [Binder(country)]


def page_order(range_code: str | None, product_name: str) -> tuple:
    code = range_code or NO_RANGE
    return (
        RANGE_ORDER.index(code) if code in RANGE_ORDER else len(RANGE_ORDER),
        sort_name(product_name),
    )


def visible_countries(user):
    countries = Country.objects.all()
    return countries if user.is_global else countries.filter(pk__in=user.countries.all())


def shelf_order(country: Country) -> tuple:
    """Le siège d'abord, puis les pays par ordre alphabétique."""
    return (country.iso2 != HEADQUARTERS, sort_name(country.name))


def binder_by_key(key: str) -> Binder:
    iso2, _, slug = (key or "").partition("-")
    country = Country.objects.filter(iso2=iso2.upper()).first()
    if country is not None:
        for binder in binders_of(country):
            if binder.key == f"{country.iso2}{'-' + slug if slug else ''}":
                return binder
    raise Http404("Classeur inconnu.")


def get_binder(user, key: str) -> Binder:
    binder = binder_by_key(key)
    if not user.can_access_country(binder.country):
        # Un pays ne voit que ses classeurs : même réponse qu'un classeur inexistant.
        raise Http404("Classeur inconnu.")
    return binder


def ensure_in_binder(binder: Binder, amm) -> None:
    if amm.country_id != binder.country.pk or not binder.contains(
        amm.product.range.code if amm.product.range_id else None, amm.product.name
    ):
        raise PermissionDenied("Cette AMM n'est pas dans ce classeur.")


def binder_amms(binder: Binder) -> list:
    """Les AMM du classeur, dans l'ordre des pages."""
    queryset = (
        MarketingAuthorization.objects.filter(country=binder.country)
        .select_related("product__range", "binder_check__checked_by")
        .prefetch_related(
            "renewals",
            Prefetch(
                "documents",
                queryset=Document.objects.filter(
                    is_current=True, archived_at__isnull=True
                ).order_by("document_date", "uploaded_at"),
                to_attr="current_documents",
            ),
            "ignored_gaps",
            Prefetch(
                "review_points",
                queryset=DossierReviewPoint.objects.filter(
                    status=DossierReviewPoint.Status.OPEN, code="value_mismatch"
                ).exclude(field=""),
                to_attr="open_mismatches",
            ),
        )
    )
    amms = [
        amm
        for amm in queryset
        if binder.contains(
            amm.product.range.code if amm.product.range_id else None, amm.product.name
        )
    ]
    amms.sort(key=lambda amm: page_order(_range_code(amm), amm.product.name))
    return amms


def _range_code(amm) -> str:
    return amm.product.range.code if amm.product.range_id else NO_RANGE


def last_obtained(renewals):
    """Le dernier renouvellement obtenu : celui qui figure dans le classeur."""
    obtained = [r for r in renewals if r.workflow_status == "OBTENU"]
    return max(obtained, key=lambda r: r.sequence) if obtained else None


def _person(user) -> str | None:
    return user.full_name if user else None


def check_payload(check) -> dict | None:
    if check is None:
        return None
    return {
        "result": check.result,
        "corrections": check.corrections,
        "note": check.note,
        "checked_by": _person(check.checked_by),
        "checked_at": check.checked_at,
    }


def pending_renewal(renewals):
    """Renouvellement déposé ou en instruction : tamponné « DÉPOSÉ » sur la page."""
    pending = [r for r in renewals if r.is_pending]
    return max(pending, key=lambda r: r.sequence) if pending else None


FIELD_NAMES = ("number", "start_date", "end_date")


def _json(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def page_values(amm, renewal) -> dict:
    """Valeurs de la page telles qu'elles sont vérifiées sur le papier (format JSON)."""
    values = {
        "original": {
            "number": amm.original_number,
            "start_date": _json(amm.original_start_date),
            "end_date": _json(amm.original_end_date),
        }
    }
    if renewal is not None:
        values["renewal"] = {
            "number": renewal.number,
            "start_date": _json(renewal.start_date),
            "end_date": _json(renewal.end_date),
        }
    return values


def changes_since(snapshot: dict, current: dict) -> list[dict]:
    """Ce qui a changé dans la fiche depuis le constat de l'archiviste."""
    if not snapshot:
        return []
    changes = []
    for slot in ("original", "renewal"):
        before, now = snapshot.get(slot) or {}, current.get(slot) or {}
        if not before and not now:
            continue
        for field in FIELD_NAMES:
            if (before.get(field) or None) != (now.get(field) or None):
                changes.append(
                    {
                        "slot": slot,
                        "field": field,
                        "checked": before.get(field),
                        "now": now.get(field),
                    }
                )
    return changes


def traces_for(amm_ids) -> dict:
    """Derniers imports qui ont touché chaque AMM : ligne du Dashboard (Excel) et dossier."""
    from apps.imports.models import DossierImport, ImportRow

    traces: dict = {str(pk): {"excel": None, "dossier": None} for pk in amm_ids}
    for row in (
        ImportRow.objects.filter(amm_id__in=amm_ids)
        .exclude(outcome=ImportRow.Outcome.ERROR)
        .order_by("amm_id", "-batch__created_at", "-row_number")
        .values("amm_id", "batch_id", "batch__created_at", "sheet", "row_number", "outcome")
    ):
        trace = traces[str(row["amm_id"])]
        if trace["excel"] is None:
            trace["excel"] = {
                "batch_id": str(row["batch_id"]),
                "date": row["batch__created_at"],
                "sheet": row["sheet"],
                "row": row["row_number"],
                "outcome": row["outcome"],
            }
    for batch in (
        DossierImport.objects.filter(amm_id__in=amm_ids)
        .order_by("amm_id", "-created_at")
        .values("amm_id", "id", "created_at", "status", "root_name", "auto_applied")
    ):
        trace = traces[str(batch["amm_id"])]
        if trace["dossier"] is None:
            trace["dossier"] = {
                "batch_id": str(batch["id"]),
                "date": batch["created_at"],
                "status": batch["status"],
                "folder": batch["root_name"],
                "auto_applied": batch["auto_applied"],
            }
    return traces


def _change_source(trace: dict | None, since) -> str:
    """D'où vient la modification faite après le constat (le plus récent des imports)."""
    if trace:
        dossier, excel = trace.get("dossier"), trace.get("excel")
        candidates = [
            (item["date"], label)
            for item, label in (
                (dossier, "import de dossier"),
                (excel, "import Excel du Dashboard"),
            )
            if item and item["date"] > since
        ]
        if candidates:
            return max(candidates)[1]
    return "modification de la fiche AMM"


def page_payload(amm, trace: dict | None = None) -> dict:
    renewals = list(amm.renewals.all())
    renewal = last_obtained(renewals)
    filed = pending_renewal(renewals)
    documents = getattr(amm, "current_documents", None)
    if documents is None:
        documents = list(
            amm.documents.filter(is_current=True, archived_at__isnull=True).order_by(
                "document_date", "uploaded_at"
            )
        )
    scans = [doc for doc in documents if doc.kind == Document.Kind.AMM]
    # La décision la plus récente en haut de la pile agrafée.
    scans.sort(key=lambda doc: doc.document_date, reverse=True)
    # En haut de la pile : le scan de la décision en vigueur, sinon la plus récente scannée
    # (signalée comme n'étant pas celle en vigueur).
    current_scan = _scan_of_decision(amm, renewal, scans)
    scan = current_scan or (scans[0] if scans else None)
    discrepancies = []
    for point in getattr(amm, "open_mismatches", []):
        if point.renewal_id is None and point.field in AMM_FIELD_SLOTS:
            slot, field = "original", AMM_FIELD_SLOTS[point.field]
        elif renewal and point.renewal_id == renewal.pk and point.field in SLOT_FIELDS["renewal"]:
            slot, field = "renewal", point.field
        else:
            continue
        discrepancies.append(
            {
                "slot": slot,
                "field": field,
                "recorded": point.recorded_value,
                "scan": point.scan_value,
                "message": point.message,
            }
        )
    check = amm.binder_check if hasattr(amm, "binder_check") else None
    code = _range_code(amm)
    changed = changes_since(check.snapshot, page_values(amm, renewal)) if check else []
    verdict = conformity(amm, renewal, check, changed, current_scan, scan)
    return {
        "amm_id": str(amm.pk),
        "product_name": amm.product.name,
        "range_code": code,
        "range_label": RANGE_LABELS.get(code, code),
        "original": {
            "number": amm.original_number,
            "start_date": amm.original_start_date,
            "end_date": amm.original_end_date,
        },
        "renewal": (
            {
                "id": str(renewal.pk),
                "sequence": renewal.sequence,
                "number": renewal.number,
                "start_date": renewal.start_date,
                "end_date": renewal.end_date,
            }
            if renewal
            else None
        ),
        "pending_renewal": (
            {
                "workflow_status": filed.workflow_status,
                "workflow_label": filed.get_workflow_status_display(),
                "filing_date": filed.filing_date,
            }
            if filed
            else None
        ),
        "status": amm.status,
        "status_label": amm.get_status_display(),
        "dossier_state": amm.dossier_state,
        "scan": (
            {
                "document_id": str(scan.pk),
                "document_date": scan.document_date,
                "page_count": scan.page_count,
                "is_current": scan is current_scan,
            }
            if scan
            else None
        ),
        "decision_count": len(scans),
        "chronology": chronology(amm, renewals, documents, _ignored_gaps(amm)),
        "discrepancies": discrepancies,
        "check": check_payload(check),
        # Le dashboard ou un import a changé la fiche depuis le constat : à revérifier.
        "changed_since_check": changed,
        "changed_by": _change_source(trace, check.checked_at) if changed else None,
        "trace": trace or {"excel": None, "dossier": None},
        # Le papier est là mais la décision en vigueur n'a pas de scan.
        "to_scan": verdict["to_scan"],
        "conformity": verdict,
    }


CONFORMITY_LABELS = {
    "CONFORME": "Le dossier est conforme",
    "NON_CONFORME": "Dossier non conforme",
    "NON_VERIFIE": "Dossier pas encore vérifié",
}


def _scan_of_decision(amm, renewal, scans):
    """Le scan de la décision en vigueur (dernier renouvellement obtenu, sinon l'origine)."""
    wanted = renewal.pk if renewal else None
    return next((doc for doc in scans if doc.renewal_id == wanted), None)


def conformity(amm, renewal, check, changed, current_scan, scan=None) -> dict:
    """Les 4 niveaux de vérification d'un dossier, et le résultat.

    1. Visible dans le classeur numérique : la fiche existe dans AMM GH (toujours vrai pour une
       page ; un dossier papier sans fiche est une « page en trop »).
    2. Dossier papier dans le classeur : constat de l'archiviste (présent ou absent).
    3. Décision en vigueur scannée : dans AMM GH, automatiquement.
    4. Bonne date et bon n° d'AMM : relevés sur le papier par l'archiviste (« Conforme » ou
       « Corriger »), renseignés, et inchangés depuis.

    « Le dossier est conforme » quand les 4 sont justes ; pas encore vérifié tant que le papier
    n'a pas été constaté. Le résultat est recalculé à chaque lecture : un scan ajouté plus tard,
    ou une fiche modifiée après le constat, le met à jour.
    """
    number = renewal.number if renewal else amm.original_number
    start = renewal.start_date if renewal else amm.original_start_date
    known = bool(renewal) or bool(amm.original_number or amm.original_start_date)
    decision = f"renouvellement {renewal.sequence}" if renewal else "AMM d'origine"

    paper = None if check is None else check.result != "ABSENT"
    if not known:
        scanned, scan_detail = False, "aucune décision enregistrée sur la fiche"
    elif current_scan is not None:
        scanned, scan_detail = True, f"décision scannée ({decision})"
    elif scan is not None:
        scanned, scan_detail = False, f"la décision en vigueur ({decision}) n'est pas scannée"
    else:
        scanned, scan_detail = False, "aucun scan de décision"

    if check is None:
        data, data_detail = None, "à relever sur le papier"
    elif not paper:
        data, data_detail = None, "pas de papier pour le vérifier"
    elif changed:
        data, data_detail = False, "la fiche a changé depuis la vérification : à revérifier"
    elif not number or not start:
        missing = " et ".join(
            label for label, value in (("date", start), ("n° d'AMM", number)) if not value
        )
        data, data_detail = False, f"{missing} manquant{'s' if ' et ' in missing else ''}"
    else:
        data, data_detail = True, f"n° {number} du {start:%d/%m/%Y}"

    criteria = [
        {
            "key": "digital",
            "label": "Visible dans le classeur numérique",
            "ok": True,
            "detail": "fiche dans AMM GH",
        },
        {
            "key": "paper",
            "label": "Dossier papier dans le classeur",
            "ok": paper,
            "detail": {None: "à constater", True: "présent", False: "absent du classeur"}[paper],
        },
        {
            "key": "scan",
            "label": "Version scannée",
            "ok": scanned,
            "detail": scan_detail,
        },
        {
            "key": "data",
            "label": "Bonne date et bon n° d'AMM",
            "ok": data,
            "detail": data_detail,
        },
    ]
    if paper is None:
        status = "NON_VERIFIE"
    elif all(item["ok"] is True for item in criteria):
        status = "CONFORME"
    else:
        status = "NON_CONFORME"
    return {
        "status": status,
        "label": CONFORMITY_LABELS[status],
        "criteria": criteria,
        "to_scan": bool(paper) and not scanned and known,
        "stale": bool(changed),
    }


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


def _ignored_gaps(amm) -> set:
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


COUNT_KEYS = (
    "total",  # pages du classeur
    "checked",  # papier constaté (présent ou absent)
    "conformes",  # les 4 niveaux justes : « Le dossier est conforme »
    "non_conformes",  # constatées, au moins un niveau faux
    "corrected",  # date ou n° corrigé sur la fiche d'après le papier
    "absent",  # dossier papier absent du classeur
    "to_scan",  # papier présent, décision en vigueur non scannée
    "stale",  # fiche modifiée depuis le constat : à revérifier
)


def _empty_counts() -> dict:
    return dict.fromkeys(COUNT_KEYS, 0)


def _count(counts: dict, verdict: dict, result: str | None) -> None:
    """Les compteurs viennent du même calcul que la page (`conformity`) : pas d'écart possible."""
    counts["total"] += 1
    if verdict["status"] == "NON_VERIFIE":
        return
    counts["checked"] += 1
    counts["conformes" if verdict["status"] == "CONFORME" else "non_conformes"] += 1
    if result == "CORRIGE":
        counts["corrected"] += 1
    if result == "ABSENT":
        counts["absent"] += 1
    counts["to_scan"] += verdict["to_scan"]
    counts["stale"] += verdict["stale"]


READING_WINDOW = timedelta(minutes=2)


def readers_by_binder(keys) -> dict[str, list[str]]:
    """Qui a chaque classeur ouvert en ce moment (signal envoyé chaque minute par la page)."""
    from .models import BinderPresence

    readers: dict[str, list[str]] = {}
    for presence in (
        BinderPresence.objects.filter(
            binder_key__in=list(keys), last_seen__gte=timezone.now() - READING_WINDOW
        )
        .select_related("user")
        .order_by("last_seen")
    ):
        user = presence.user
        readers.setdefault(presence.binder_key, []).append(user.first_name or user.full_name)
    return readers


def _summary(
    binder: Binder, sections: dict, extras: int, last_check, readers: list | None = None
) -> dict:
    counts = _empty_counts()
    for section in sections.values():
        for name in counts:
            counts[name] += section[name]
    return {
        "key": binder.key,
        "title": binder.title,
        "country_iso2": binder.country.iso2,
        "country_name": binder.country.name,
        "is_headquarters": binder.country.iso2 == HEADQUARTERS,
        "sections": [
            {
                "code": code,
                "label": RANGE_LABELS[code],
                "color": RANGE_COLORS[code],
                **sections[code],
            }
            for code in binder.ranges
            # Un intercalaire n'existe que pour une gamme présente dans le classeur.
            if code in sections and (sections[code]["total"] or (binder.part and code != NO_RANGE))
        ],
        **counts,
        "extras": extras,
        "last_checked_at": last_check["at"] if last_check else None,
        "last_checked_by": last_check["by"] if last_check else None,
        "readers": readers or [],
    }


def _verdict(amm) -> dict:
    """Résultat de la page d'une AMM (même calcul que `page_payload`, sans le reste)."""
    renewals = list(amm.renewals.all())
    renewal = last_obtained(renewals)
    scans = sorted(amm.decision_scans, key=lambda doc: doc.document_date, reverse=True)
    check = amm.binder_check if hasattr(amm, "binder_check") else None
    changed = changes_since(check.snapshot, page_values(amm, renewal)) if check else []
    current = _scan_of_decision(amm, renewal, scans)
    return conformity(amm, renewal, check, changed, current, scans[0] if scans else None)


def shelf(user) -> list[dict]:
    """Les classeurs visibles par l'utilisateur, avec leur avancement."""
    from .models import BinderExtraPage

    countries = sorted(
        Country.objects.filter(
            pk__in=MarketingAuthorization.objects.filter(
                country__in=visible_countries(user)
            ).values("country")
        ),
        key=shelf_order,
    )
    amms = (
        MarketingAuthorization.objects.filter(country__in=countries)
        .select_related("product__range", "binder_check__checked_by")
        .prefetch_related(
            Prefetch(
                "renewals",
                queryset=Renewal.objects.only(
                    "amm_id", "sequence", "workflow_status", "number", "start_date", "end_date"
                ),
            ),
            Prefetch(
                "documents",
                queryset=Document.objects.filter(
                    is_current=True, archived_at__isnull=True, kind=Document.Kind.AMM
                ).only("amm_id", "renewal_id", "document_date"),
                to_attr="decision_scans",
            ),
        )
    )
    by_country: dict = {}
    for amm in amms:
        by_country.setdefault(amm.country_id, []).append(amm)
    extras: dict = {}
    for key in BinderExtraPage.objects.filter(country__in=countries).values_list(
        "binder_key", flat=True
    ):
        extras[key] = extras.get(key, 0) + 1

    reading = readers_by_binder(
        binder.key for country in countries for binder in binders_of(country)
    )
    result = []
    for country in countries:
        for binder in binders_of(country):
            sections = {code: _empty_counts() for code in binder.ranges}
            last = None
            for amm in by_country.get(country.pk, []):
                code = amm.product.range.code if amm.product.range_id else None
                if not binder.contains(code, amm.product.name):
                    continue
                check = amm.binder_check if hasattr(amm, "binder_check") else None
                _count(sections[code or NO_RANGE], _verdict(amm), check.result if check else None)
                if check and (last is None or check.checked_at > last["at"]):
                    last = {"at": check.checked_at, "by": _person(check.checked_by)}
            result.append(
                _summary(binder, sections, extras.get(binder.key, 0), last, reading.get(binder.key))
            )
    return result


def binder_detail(binder: Binder) -> dict:
    from .models import BinderExtraPage

    amms = binder_amms(binder)
    traces = traces_for([amm.pk for amm in amms])
    sections: dict = {}
    pages_by_section: dict = {}
    resume = None
    last = None
    for index, amm in enumerate(amms):
        page = page_payload(amm, traces.get(str(amm.pk)))
        code = page["range_code"]
        section = pages_by_section.setdefault(code, [])
        page["page"] = index + 1
        page["section_page"] = len(section) + 1
        section.append(page)
        check = page["check"]
        _count(
            sections.setdefault(code, _empty_counts()),
            page["conformity"],
            check["result"] if check else None,
        )
        if (check is None or page["changed_since_check"]) and resume is None:
            resume = index
        if check and (last is None or check["checked_at"] > last["at"]):
            last = {"at": check["checked_at"], "by": check["checked_by"]}
    extras = [
        {
            "id": str(extra.pk),
            "product_name": extra.product_name,
            "note": extra.note,
            "created_by": _person(extra.created_by),
            "created_at": extra.created_at,
        }
        for extra in BinderExtraPage.objects.filter(binder_key=binder.key).select_related(
            "created_by"
        )
    ]
    summary = _summary(
        binder,
        {code: sections.get(code, _empty_counts()) for code in binder.ranges},
        len(extras),
        last,
        readers_by_binder([binder.key]).get(binder.key),
    )
    for section in summary["sections"]:
        section["pages"] = pages_by_section.get(section["code"], [])
    summary["extra_pages"] = extras
    summary["resume_page"] = resume if resume is not None else 0
    return summary


def locate(user, amm_id) -> dict:
    """La page d'une AMM dans les classeurs : pour relier la fiche AMM et les imports au papier."""
    amm = MarketingAuthorization.objects.select_related("country", "product__range").get(pk=amm_id)
    if not user.can_access_country(amm.country):
        raise Http404("AMM inconnue.")
    code = _range_code(amm)
    binder = next(b for b in binders_of(amm.country) if b.contains(code, amm.product.name))
    amms = binder_amms(binder)
    index = next(i for i, item in enumerate(amms) if item.pk == amm.pk)
    page = page_payload(amms[index])
    return {
        "binder_key": binder.key,
        "title": binder.title,
        "country_name": amm.country.name,
        "page": index + 1,
        "total": len(amms),
        "check": page["check"],
        "stale": bool(page["changed_since_check"]),
        "conformity": page["conformity"],
    }
