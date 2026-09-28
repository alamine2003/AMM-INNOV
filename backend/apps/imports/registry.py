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
from difflib import SequenceMatcher

from django.db import transaction
from openpyxl import load_workbook

from apps.amm.models import MarketingAuthorization, Renewal
from apps.catalog.models import Country, Product, ProductAlias, ProductRange
from apps.catalog.normalize import normalize_product_name, product_key

from .dossier.matching import (
    _UNITS,
    _distinctive,
    _forms,
    _parts,
    _strengths,
    _strengths_fit,
    _words_fit,
)
from .excel_parser import SHEET_COUNTRIES
from .models import ImportBatch, ImportRow
from .progress import set_progress

logger = logging.getLogger(__name__)

REGISTRY_SHEETS = {"_Consolidation", "_Docs"}
SHEET = "Registre GHPL"
PROGRESS_EVERY = 50
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
    """Tout ce que l'import consulte, chargé une fois : produits, alias, AMM, dépôts en cours.

    Sur Render gratuit (0,1 CPU), l'import faisait ~10 000 requêtes et comparait chaque libellé à
    tout le catalogue : plus de dix minutes, le service figé. Ici chaque ligne ne lit plus rien en
    base, et le rapprochement ne compare que les produits de la même marque (mêmes deux premières
    lettres), dont les caractéristiques sont calculées une seule fois.
    """

    def __init__(self):
        self.products: dict = {}
        self.by_name: dict[str, Product] = {}
        self.by_key: dict[str, Product] = {}
        self._features: dict = {}
        self._brands: dict[str, list] = {}
        for product in Product.objects.order_by("pk"):
            self._remember(product)
        self.aliases = {
            raw: self.products.get(product_id)
            for raw, product_id in ProductAlias.objects.values_list("raw_name", "product_id")
        }
        self.amms: dict[tuple, MarketingAuthorization] = {}
        self.by_country: dict = {}
        for amm in MarketingAuthorization.objects.order_by("pk"):
            self.amms.setdefault((amm.product_id, amm.country_id), amm)
            self.by_country.setdefault(amm.country_id, set()).add(amm.product_id)
        self.pending = set(
            Renewal.objects.filter(workflow_status__in=Renewal.PENDING_STATUSES).values_list(
                "amm_id", flat=True
            )
        )

    def _remember(self, product: Product) -> None:
        if product.pk in self.products:
            return
        self.products[product.pk] = product
        self.by_name.setdefault(product.name, product)
        if product.key:
            self.by_key.setdefault(product.key, product)
        features = _features(product.name)
        self._features[product.pk] = features
        if features:
            self._brands.setdefault(features[0][:2], []).append(product.pk)

    def add(self, amm: MarketingAuthorization) -> None:
        self._remember(amm.product)
        self.amms[(amm.product_id, amm.country_id)] = amm
        self.by_country.setdefault(amm.country_id, set()).add(amm.product_id)

    def amm(self, product, country) -> MarketingAuthorization | None:
        return self.amms.get((product.pk, country.pk)) if product else None

    def _usage(self, product: Product) -> int:
        return sum(1 for ids in self.by_country.values() if product.pk in ids)

    def _candidates(self, name: str, pool: set | None) -> list[tuple]:
        label = _features(name)
        if not label:
            return []
        brand, forms, strengths, _pack, distinctive = label
        found = []
        for pk in self._brands.get(brand[:2], []):
            if pool is not None and pk not in pool:
                continue
            other = self._features[pk]
            if SequenceMatcher(None, brand, other[0]).ratio() < 0.85:
                continue
            if forms and other[1] and not forms & other[1]:
                continue
            if not _strengths_fit(strengths, other[2]):
                continue
            if not _words_fit(distinctive, other[4]):
                continue
            found.append((self.products[pk], other[3]))
        return found

    def _pick(self, name: str, pool: set | None) -> Product | None:
        candidates = self._candidates(name, pool)
        _, pack = _strengths(name)
        if len(candidates) > 1 and pack:
            candidates = [item for item in candidates if item[1] == pack] or candidates
        if len(candidates) == 1:
            return candidates[0][0]
        # Doublons du catalogue (« GENSIL SIROP FL/100ML » et « GENSIL SP F/100ML ») : mêmes
        # dosages et même boîte, c'est la même présentation ; on garde la plus utilisée.
        shapes = {
            (tuple(sorted(self._features[product.pk][2])), product_pack)
            for product, product_pack in candidates
        }
        if len(candidates) > 1 and len(shapes) == 1:
            return max(candidates, key=lambda item: (self._usage(item[0]), item[0].name))[0]
        return None

    def exact(self, labels: list[str]) -> Product | None:
        for label in labels:
            name = normalize_product_name(label)
            if not name:
                continue
            product = self.aliases.get(name) or self.by_name.get(name)
            product = product or self.by_key.get(product_key(name))
            if product:
                return product
        return None

    def find(self, labels: list[str], country) -> Product | None:
        """Le libellé exact (alias, nom, clé), puis le même produit écrit autrement.

        « OMEPRAL 20MG GELULE B28 » est « OMEPRAL 20MG GEL B/28 », « TENSOPLUS 2,5MG-10MG-10MG »
        est « TENSOPLUS 10MG/2,5MG/10MG » : même marque, même forme, mêmes dosages. On cherche
        d'abord parmi les produits suivis dans le pays, puis dans tout le catalogue ; il faut une
        seule réponse (ou des doublons du catalogue), sinon le produit est considéré comme nouveau.
        """
        exact = self.exact(labels)
        if exact:
            return exact
        names = [label for label in labels if label]
        for scope in (self.by_country.get(country.pk, set()), None):
            for name in names:
                found = self._pick(name, scope)
                if found:
                    return found
        return None


def _features(name: str) -> tuple | None:
    """Marque, formes, dosages, boîte et mots distinctifs (comme `_country_candidates`)."""
    words, _ = _parts(name)
    words = [word for word in words if word not in _UNITS]
    if not words or len(words[0]) < 4:
        return None
    strengths, pack = _strengths(name)
    return words[0], _forms(words), strengths, pack, _distinctive(words)


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
    labels = [presentation, str(record.get("Referentiel") or "").strip()]
    product = catalog.find(labels, country)
    amm = catalog.amm(product, country)
    if amm is None and record.get("Source") != "Classement seul":
        return "WARNING", DASHBOARD_MISSING, None
    args = (record, deposits, ranges, catalog, country, presentation, product, amm)
    if not _writes(record, catalog, amm):
        return _write(*args)
    with transaction.atomic():  # une ligne en erreur n'emporte qu'elle
        return _write(*args)


def _writes(record, catalog, amm) -> bool:
    """La ligne modifie-t-elle la base ? (sinon, pas de point de sauvegarde à poser)"""
    if amm is None:
        return True
    if str(record.get("N° AMM origine") or "").strip() and not amm.original_number:
        return True
    if _date(record.get("Date origine")) and not amm.original_start_date:
        return True
    deposited = str(record.get("Statut dossier") or "").startswith("Depos")
    return deposited and amm.pk not in catalog.pending


def _write(record, deposits, ranges, catalog, country, presentation, product, amm):
    control = str(record.get("Controle") or "")
    number = str(record.get("N° AMM origine") or "").strip()
    origin = _date(record.get("Date origine"))
    lines: list[str] = []
    outcome = "SKIPPED"
    if amm is None:
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
        if amm.pk not in catalog.pending:
            Renewal.objects.create(
                amm=amm,
                workflow_status=Renewal.WorkflowStatus.DEPOSE,
                filing_date=filed,
                notes=f"Déposé selon le registre GHPL{' (attestation classée)' if filed else ''}.",
            )
            catalog.pending.add(amm.pk)
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
            total = len(records)
            for number, record in enumerate(records, start=2):
                if batch is not None and (number - 2) % PROGRESS_EVERY == 0:
                    set_progress(batch.pk, number - 2, total)
                sheet = f"{SHEET} — {record.get('Pays') or '?'}"
                counters = sheets.setdefault(sheet, dict.fromkeys(COUNTER_KEYS, 0))
                counters["rows"] += 1
                try:
                    outcome, message, amm = _apply(record, deposits, countries, ranges, catalog)
                    if outcome == "CREATED":
                        catalog.add(amm)
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
    if batch is not None:
        set_progress(batch.pk, len(records), len(records))
    return sheets
