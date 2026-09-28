"""Import du registre « 0_REGISTRE AMM GHPL.xlsx » (classement général des scans, Nextcloud).

Le registre croise le Dashboard AMM Afrique et les scans classés par gamme / pays / produit.
Le Dashboard reste la référence (règle du registre lui-même) : l'import est prudent.

- Il complète une fiche sans jamais écraser une valeur déjà renseignée : n° et date d'origine.
- « Statut dossier = Déposé » : un renouvellement déposé est ouvert s'il n'y en a pas déjà un en
  cours, à la date de la dernière attestation de dépôt classée.
- « Absent du Dashboard » : la présentation n'existe que dans le classement ; l'AMM est créée
  (n°, date d'origine, dernier acte), signalée comme venant du registre.
- Un acte classé plus récent que le Dashboard n'est pas appliqué : il est signalé à vérifier.

Les résultats passent par le même lot et les mêmes lignes que l'import du Dashboard
(`ImportBatch` / `ImportRow`), simulation comprise.
"""

import logging
import re
import unicodedata
from datetime import date, datetime

from django.db import transaction
from openpyxl import load_workbook

from apps.amm.models import MarketingAuthorization, Renewal
from apps.catalog.models import Country, Product, ProductAlias, ProductRange
from apps.catalog.normalize import normalize_product_name, product_key

from .dossier.matching import _country_candidates, _strengths
from .excel_parser import SHEET_COUNTRIES
from .models import ImportBatch, ImportRow

logger = logging.getLogger(__name__)

REGISTRY_SHEETS = {"_Consolidation", "_Docs"}
SHEET = "Registre GHPL"
COUNTER_KEYS = ("rows", "created", "updated", "skipped", "warnings", "errors")
NOTE = "Complété depuis le registre GHPL (classement général des scans)."

# Libellés de pays du registre → codes ISO (en plus des onglets du Dashboard).
COUNTRIES = {
    **{name: iso2 for name, (iso2, _label) in SHEET_COUNTRIES.items()},
    "BURKINA FASO": "BF",
    "COTE D'IVOIRE": "CI",
}
RANGES = {"GAMME GENERALE": "GENERALE", "GAMME CARDIO": "CARDIO", "GAMME BIEN-ETRE": "BIEN_ETRE"}


def is_registry(source) -> bool:
    workbook = load_workbook(source, read_only=True)
    try:
        return REGISTRY_SHEETS <= set(workbook.sheetnames)
    finally:
        workbook.close()
        if hasattr(source, "seek"):
            source.seek(0)


def _plain(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).upper().strip()


def _date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _records(workbook, name: str) -> list[dict]:
    rows = workbook[name].iter_rows(values_only=True)
    header = [str(cell or "").strip() for cell in next(rows, [])]
    return [dict(zip(header, row, strict=False)) for row in rows if any(row)]


UNIDENTIFIED = "PRESENTATION NON IDENTIFIEE"
NEWER_ACT = re.compile(r"plus recent que le Dashboard \((\d{4}-\d{2}-\d{2})\)")
DASHBOARD_MISSING = "AMM du Dashboard introuvable dans AMM GH (importer le Dashboard)."


class _Catalog:
    """Produits du catalogue et produits suivis par pays, chargés une fois pour tout le registre."""

    def __init__(self):
        self.products = list(Product.objects.all())
        self.by_country: dict[str, set] = {}
        for country_id, product_id in MarketingAuthorization.objects.values_list(
            "country_id", "product_id"
        ):
            self.by_country.setdefault(country_id, set()).add(product_id)

    def add(self, product: Product, country) -> None:
        if all(known.pk != product.pk for known in self.products):
            self.products.append(product)
        self.by_country.setdefault(country.pk, set()).add(product.pk)

    def _usage(self, product: Product) -> int:
        return sum(1 for ids in self.by_country.values() if product.pk in ids)

    def _pick(self, name: str, pool: set) -> Product | None:
        marketed = [product for product in self.products if product.pk in pool]
        found = _country_candidates(name, marketed)
        candidates = list({product.pk: (product, pack) for product, pack in found}.values())
        _, pack = _strengths(name)
        if len(candidates) > 1 and pack:
            candidates = [item for item in candidates if item[1] == pack] or candidates
        if len(candidates) == 1:
            return candidates[0][0]
        # Doublons du catalogue (« GENSIL SIROP FL/100ML » et « GENSIL SP F/100ML ») : mêmes
        # dosages et même boîte, c'est la même présentation ; on garde la plus utilisée.
        shapes = {
            (tuple(sorted(_strengths(product.name)[0])), product_pack)
            for product, product_pack in candidates
        }
        if len(candidates) > 1 and len(shapes) == 1:
            return max(candidates, key=lambda item: (self._usage(item[0]), item[0].name))[0]
        return None

    def find(self, labels: list[str], country) -> Product | None:
        """Le libellé exact (alias, nom, clé), puis le même produit écrit autrement.

        « OMEPRAL 20MG GELULE B28 » est « OMEPRAL 20MG GEL B/28 », « TENSOPLUS 2,5MG-10MG-10MG »
        est « TENSOPLUS 10MG/2,5MG/10MG » : même marque, même forme, mêmes dosages. On cherche
        d'abord parmi les produits suivis dans le pays, puis dans tout le catalogue ; il faut une
        seule réponse (ou des doublons du catalogue), sinon le produit est considéré comme nouveau.
        """
        exact = _find_product(labels)
        if exact:
            return exact
        names = [label for label in labels if label]
        everywhere = {product.pk for product in self.products}
        for scope in (self.by_country.get(country.pk, set()), everywhere):
            for name in names:
                found = self._pick(name, scope)
                if found:
                    return found
        return None


def _find_product(labels: list[str]) -> Product | None:
    for label in labels:
        name = normalize_product_name(label)
        if not name:
            continue
        alias = ProductAlias.objects.filter(raw_name=name).select_related("product").first()
        if alias:
            return alias.product
        product = (
            Product.objects.filter(name=name).first()
            or Product.objects.filter(key=product_key(name)).first()
        )
        if product:
            return product
    return None


def _deposits(docs: list[dict]) -> dict[str, date]:
    """Dernière attestation de dépôt classée, par présentation (« PAYS|PRÉSENTATION »)."""
    latest: dict[str, date] = {}
    for doc in docs:
        if not str(doc.get("Type") or "").startswith("Depot"):
            continue
        when = _date(doc.get("Date"))
        key = f"{_plain(doc.get('Pays'))}|{_plain(doc.get('Presentation'))}"
        if when and (key not in latest or when > latest[key]):
            latest[key] = when
    return latest


def _sentence(lines: list[str]) -> str:
    text = "; ".join(lines)
    return text[:1].upper() + text[1:] + "."


def _apply(
    record: dict, deposits: dict, countries: dict, ranges: dict, catalog: _Catalog
) -> tuple[str, str, object]:
    iso2 = COUNTRIES.get(_plain(record.get("Pays")))
    country = countries.get(iso2)
    presentation = str(record.get("Presentation") or "").strip()
    if not presentation:
        return "SKIPPED", "Ligne sans présentation.", None
    if country is None:
        return "WARNING", f"Pays non suivi dans AMM GH : {record.get('Pays')}.", None
    if UNIDENTIFIED in _plain(presentation):
        return "SKIPPED", "Présentation non identifiée dans le classement : rien n'est créé.", None
    control = str(record.get("Controle") or "")
    labels = [presentation, str(record.get("Referentiel") or "").strip()]
    product = catalog.find(labels, country)
    amm = (
        MarketingAuthorization.objects.filter(product=product, country=country).first()
        if product
        else None
    )
    number = str(record.get("N° AMM origine") or "").strip()
    origin = _date(record.get("Date origine"))
    lines: list[str] = []
    outcome = "SKIPPED"

    if amm is None:
        if record.get("Source") != "Classement seul":
            return "WARNING", DASHBOARD_MISSING, None
        # Présentation connue par les scans seulement : l'AMM est créée avec ce qu'ils disent.
        if product is None:
            product = Product.objects.create(
                name=presentation, range=ranges.get(RANGES.get(_plain(record.get("Gamme"))))
            )
            lines.append("produit créé")
        else:
            lines.append(f"produit du catalogue repris : {product.name}")
        amm = MarketingAuthorization.objects.create(
            product=product,
            country=country,
            original_number=number,
            original_start_date=origin,
            notes=f"{NOTE} Présentation absente du Dashboard AMM Afrique.",
        )
        outcome = "CREATED"
        lines.append("AMM créée (absente du Dashboard, connue par les scans classés)")
    else:
        changed = []
        if number and not amm.original_number:
            amm.original_number = number
            changed.append(f"n° d'origine {number}")
        if origin and not amm.original_start_date:
            amm.original_start_date = origin
            changed.append(f"date d'origine {origin:%d/%m/%Y}")
        if changed:
            amm._change_reason = NOTE
            amm.save()
            outcome = "UPDATED"
            lines.append("complété : " + ", ".join(changed))

    if str(record.get("Statut dossier") or "").startswith("Depos"):
        key = f"{_plain(record.get('Pays'))}|{_plain(record.get('Referentiel') or presentation)}"
        filed = deposits.get(key)
        if not amm.renewals.filter(workflow_status__in=Renewal.PENDING_STATUSES).exists():
            Renewal.objects.create(
                amm=amm,
                workflow_status=Renewal.WorkflowStatus.DEPOSE,
                filing_date=filed,
                notes=f"Déposé selon le registre GHPL{' (attestation classée)' if filed else ''}.",
            )
            outcome = "UPDATED" if outcome == "SKIPPED" else outcome
            lines.append(
                "renouvellement déposé ouvert"
                + (f" (attestation du {filed:%d/%m/%Y})" if filed else "")
            )
    newer = NEWER_ACT.search(control)
    if newer or "plus recent" in control:
        when = f" du {date.fromisoformat(newer.group(1)):%d/%m/%Y}" if newer else ""
        lines.append(
            f"à vérifier : un acte classé{when} est plus récent que le Dashboard "
            "(importer son scan dans « Import de dossiers AMM »)"
        )
        if outcome == "SKIPPED":
            outcome = "WARNING"
    if not lines:
        lines.append("déjà à jour" if "Concordant" in control else f"inchangée ({control})")
    return outcome, _sentence(lines), amm


class _Rollback(Exception):
    pass


OUTCOME_COUNTERS = {
    "CREATED": "created",
    "UPDATED": "updated",
    "SKIPPED": "skipped",
    "WARNING": "warnings",
    "ERROR": "errors",
}


def import_registry(source, batch: ImportBatch | None, dry_run: bool) -> dict[str, dict]:
    """Applique le registre ; renvoie les compteurs par pays (« Registre GHPL — SENEGAL »)."""
    workbook = load_workbook(source, data_only=True, read_only=True)
    try:
        records = _records(workbook, "_Consolidation")
        deposits = _deposits(_records(workbook, "_Docs"))
    finally:
        workbook.close()
    sheets: dict[str, dict] = {}
    rows: list[ImportRow] = []
    try:
        with transaction.atomic():
            countries = {c.iso2: c for c in Country.objects.all()}
            ranges = {r.code: r for r in ProductRange.objects.all()}
            catalog = _Catalog()
            for number, record in enumerate(records, start=2):
                sheet = f"{SHEET} — {record.get('Pays') or '?'}"
                counters = sheets.setdefault(sheet, dict.fromkeys(COUNTER_KEYS, 0))
                counters["rows"] += 1
                try:
                    with transaction.atomic():
                        outcome, message, amm = _apply(record, deposits, countries, ranges, catalog)
                    if outcome == "CREATED":
                        catalog.add(amm.product, amm.country)
                except Exception as exc:
                    logger.exception("Registre GHPL, ligne %s", number)
                    outcome, message, amm = "ERROR", f"erreur inattendue : {exc}", None
                counters[OUTCOME_COUNTERS[outcome]] += 1
                if batch is not None:
                    raw = {
                        k: (v.isoformat() if isinstance(v, (date, datetime)) else v)
                        for k, v in record.items()
                        if k
                    }
                    rows.append(
                        ImportRow(
                            batch=batch,
                            sheet=sheet,
                            row_number=number,
                            raw=raw,
                            outcome=outcome,
                            message=message,
                            amm=None if dry_run else amm,
                        )
                    )
            if dry_run:
                raise _Rollback
    except _Rollback:
        pass
    if rows:
        ImportRow.objects.bulk_create(rows, batch_size=500)
    return sheets
