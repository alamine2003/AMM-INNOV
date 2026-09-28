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

from apps.amm.models import MarketingAuthorization
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
                    kind=Document.Kind.AMM, is_current=True, archived_at__isnull=True
                ),
                to_attr="decision_scans",
            ),
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
    scans = getattr(amm, "decision_scans", None)
    if scans is None:
        scans = list(
            amm.documents.filter(kind=Document.Kind.AMM, is_current=True, archived_at__isnull=True)
        )
    wanted = renewal.pk if renewal else None
    scan = next((doc for doc in scans if doc.renewal_id == wanted), None) or (
        scans[0] if scans else None
    )
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
            }
            if scan
            else None
        ),
        "discrepancies": discrepancies,
        "check": check_payload(check),
        # Le dashboard ou un import a changé la fiche depuis le constat : à revérifier.
        "changed_since_check": changed,
        "changed_by": _change_source(trace, check.checked_at) if changed else None,
        "trace": trace or {"excel": None, "dossier": None},
        # Le papier est là mais la décision en vigueur n'a pas de scan.
        "to_scan": bool(
            check
            and check.physical_present
            and amm.dossier_state == MarketingAuthorization.DossierState.INCOMPLET
        ),
    }


def _empty_counts() -> dict:
    return {"total": 0, "checked": 0, "conformes": 0, "corrected": 0, "absent": 0, "to_scan": 0}


def _count(counts: dict, result: str | None, dossier_state: str) -> None:
    counts["total"] += 1
    if not result:
        return
    counts["checked"] += 1
    counts[{"CONFORME": "conformes", "CORRIGE": "corrected", "ABSENT": "absent"}[result]] += 1
    if result != "ABSENT" and dossier_state == MarketingAuthorization.DossierState.INCOMPLET:
        counts["to_scan"] += 1


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
    rows = MarketingAuthorization.objects.filter(country__in=countries).values_list(
        "country_id",
        "product__name",
        "product__range__code",
        "dossier_state",
        "binder_check__result",
        "binder_check__checked_at",
        "binder_check__checked_by__first_name",
        "binder_check__checked_by__last_name",
        "binder_check__checked_by__email",
    )
    by_country: dict = {}
    for row in rows:
        by_country.setdefault(row[0], []).append(row)
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
            for _, name, code, state, check, at, first, last_name, email in by_country.get(
                country.pk, []
            ):
                if not binder.contains(code, name):
                    continue
                _count(sections[code or NO_RANGE], check, state)
                if at and (last is None or at > last["at"]):
                    last = {"at": at, "by": f"{first} {last_name}".strip() or email}
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
    stale: dict = {}
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
            check["result"] if check else None,
            amm.dossier_state,
        )
        if page["changed_since_check"]:
            stale[code] = stale.get(code, 0) + 1
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
        section["stale"] = stale.get(section["code"], 0)
    summary["stale"] = sum(stale.values())
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
    }
