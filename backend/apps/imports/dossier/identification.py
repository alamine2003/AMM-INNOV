"""Identification du dossier : pays et produit (dossier, documents communs, recueils
groupés), partie d'un recueil qui concerne le produit, décisions prises seul."""

import re
from collections import defaultdict
from pathlib import PurePosixPath

from apps.amm.models import MarketingAuthorization

from .evidence import _point
from .matching import (
    folder_product,
    name_compatible,
    pick_table_row,
)
from .recognition import country_labels, normalize, recognize_file, specialty_key

# Décisions posées à la racine d'un dossier pays : jointes par le navigateur à chaque produit.
COMMON_FOLDER = "Documents communs"
def _identify_by_folder(batch, files, rows, products, country, issues, warnings):
    """Produit désigné par le nom du dossier (nommé d'après le catalogue), confirmé par les pièces.

    Une décision dont la dénomination imprimée (« GENSET 10MG ») est compatible avec ce produit,
    ou qui cite sa marque, le confirme : confiance moyenne (75 au plus). Une dénomination
    incompatible n'est pas rattachée : l'identité du produit devient alors une question.
    """
    in_country = set(
        MarketingAuthorization.objects.filter(country=country).values_list("product_id", flat=True)
    )
    labels = [part for part in batch.root_name.split(" - ") if part.strip()]
    for upload in files:
        labels.extend(upload.relative_path.split("/")[1:-1])
    product, reason = folder_product(labels, products, in_country)
    if not product:
        if reason and not any(row["product_ids"] for row in rows):
            warnings.append(reason)
        return
    brand = normalize(product.name).split(" ")[0]
    # Les autres présentations commercialisées dans ce pays sont celles avec lesquelles une
    # dénomination imprimée pourrait être confondue.
    marketed = [item for item in products if item.pk in in_country] or products
    for upload, row in zip(files, rows, strict=True):
        explicit = row["explicit_product_name"]
        if explicit:
            confirmed = name_compatible(explicit, product, marketed)
        else:
            confirmed = f" {brand} " in f" {normalize(upload.extraction.get('text', ''))} "
        if explicit and not confirmed:
            row["product_ids"] = [pk for pk in row["product_ids"] if pk != str(product.pk)]
            if row["official"]:
                issues.append(
                    (
                        "product_conflict",
                        f"La décision {_name(row['path'])} nomme « {explicit} », qui ne correspond "
                        f"pas à « {product.name} » désigné par le nom du dossier.",
                    )
                )
            continue
        row["product_ids"] = [str(product.pk)]
        row["product_name"] = product.name
        row["product_source"] = "folder"
        row["product_confidence"] = (
            min(row["confidence"], 75) if confirmed and row["official"] else 60
        )


def _read_grouped_rows(rows, product, products, country, points):
    """Décision groupée : numéro et date pris sur la ligne du tableau qui nomme le produit.

    Une décision groupée qui ne cite pas le produit du dossier n'est pas une preuve pour lui :
    elle reste rangée comme pièce annexe et un point à vérifier le signale.
    """
    in_country = (
        set(
            MarketingAuthorization.objects.filter(country=country).values_list(
                "product_id", flat=True
            )
        )
        if country
        else set()
    )
    marketed = [item for item in products if item.pk in in_country] or products
    for row in rows:
        if not row.get("table_rows"):
            continue
        line = pick_table_row(row["table_rows"], product, marketed)
        if line:
            row["number"] = line["number"] if row["official"] else ""
            if line["date"] and row["official"]:
                row["start_date"] = line["date"]
                row["period"] = (
                    row["period"] if row["period"] == "original" else ("renewal-" + line["date"])
                )
            row["product_ids"] = [str(product.pk)]
            row["product_name"] = product.name
            row["product_source"] = "table"
            continue
        row["official"] = False
        row["kind"] = "AUTRE"
        _point(
            points,
            "identity",
            f"{_name(row['path'])} : décision groupée où « {product.name} » n'a pas été trouvé ; "
            "elle est rangée comme pièce annexe.",
            proof=row["file_id"],
        )


def is_common(path: str) -> bool:
    """Document commun d'un dossier pays (décision groupée, recueil) : pas une preuve d'identité."""
    return f"/{COMMON_FOLDER}/" in f"/{path}"


def _mentions_product(text: str, product, marketed) -> bool:
    """Une ligne du document désigne-t-elle ce produit (marque et dosages compatibles) ?"""
    brand = normalize(product.name).split(" ")[0]
    if len(brand) < 3 or f" {brand} " not in f" {normalize(text)} ":
        return False
    for line in text.splitlines():
        if brand in normalize(line):
            label = re.sub(r"^\s*[\[(]?\d{1,3}\s*[\]).:_|-]*\s*", "", line).strip()
            if name_compatible(label, product, marketed):
                return True
    return False


def _section_row(upload, section, product, countries, products, root_name):
    """Lecture de la seule décision du produit dans un recueil (numéro, dates, période)."""
    text = upload.extraction.get("text", "")
    focused = recognize_file(
        _Part(upload, text[section["start"] : section["end"]]), countries, products, root_name
    )
    focused.update(
        product_ids=[str(product.pk)],
        product_name=product.name,
        product_source="section",
        product_confidence=min(focused["confidence"], 75),
        sections=[],
        pages=[section["first_page"], section["last_page"]] if section["first_page"] else None,
        section_label=section["specialty"],
    )
    return focused


class _Part:
    """Une section d'un document, lue comme un document à part (même fichier de preuve)."""

    def __init__(self, upload, text):
        self.pk = upload.pk
        self.relative_path = upload.relative_path
        self.extraction = {**upload.extraction, "text": text}


def _focus_on_product(files, rows, product, products, countries, country, root_name, points):
    """Ne garde de chaque document que ce qui concerne le produit du dossier.

    - Recueil de décisions (« AMM groupée 23 DEC 2023 » : six décisions, une par spécialité) :
      seule la décision du produit est lue, et seules ses pages sont rangées.
    - Document commun (racine du dossier pays) qui ne cite pas le produit : il n'est ni lu ni
      rangé dans cette fiche (le 25/09/2026, les AMM de PALUCARE et les recueils de 2015 et 2023
      étaient rangés dans la fiche de chaque produit du Mali).
    Renvoie les documents écartés (affichés dans les détails de la lecture).
    """
    in_country = (
        set(
            MarketingAuthorization.objects.filter(country=country).values_list(
                "product_id", flat=True
            )
        )
        if country
        else set()
    )
    marketed = [item for item in products if item.pk in in_country] or products
    kept_files, kept_rows, ignored = [], [], []
    for upload, row in zip(files, rows, strict=True):
        common = is_common(upload.relative_path)
        concerned = True
        if row.get("sections"):
            candidates = [
                {"label": section["specialty"], "number": specialty_key(section["specialty"]),
                 "section": section}
                for section in row["sections"]
            ]  # fmt: skip
            line = pick_table_row(candidates, product, marketed)
            if line:
                row = _section_row(upload, line["section"], product, countries, products, root_name)
            elif common:
                concerned = False
            else:
                row["official"] = False
                row["kind"] = "AUTRE"
                _point(
                    points,
                    "identity",
                    f"{_name(row['path'])} : recueil de décisions où « {product.name} » n'a pas "
                    "été trouvé ; il est rangé comme pièce annexe.",
                    proof=row["file_id"],
                )
        elif common and row.get("table_rows"):
            concerned = pick_table_row(row["table_rows"], product, marketed) is not None
        elif common and row.get("specialty"):
            concerned = name_compatible(row["specialty"], product, marketed) or bool(
                pick_table_row([{"label": row["specialty"], "number": ""}], product, marketed)
            )
        elif common:
            concerned = _mentions_product(upload.extraction.get("text", ""), product, marketed)
        if not concerned:
            ignored.append(
                {
                    "file_id": str(upload.pk),
                    "path": upload.relative_path,
                    "reason": f"ne concerne pas « {product.name} »",
                }
            )
            continue
        if common and not row["product_ids"]:
            row["product_ids"] = [str(product.pk)]
            row["product_name"] = product.name
        kept_files.append(upload)
        kept_rows.append(row)
    return kept_files, kept_rows, ignored


def _name(path: str) -> str:
    return PurePosixPath(path).name


def _dedupe(items):
    seen, result = set(), []
    for item in items:
        key = repr(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _autonomous() -> bool:
    """Classement autonome (DOSSIER_AUTONOMOUS, actif par défaut) : l'application tranche seule
    les doutes d'identité (pays ou produits mêlés, nom proche, produit absent, décision
    illisible) et note sa décision ; seul ce qu'elle ne peut pas trancher reste une question."""
    from django.conf import settings

    return bool(getattr(settings, "DOSSIER_AUTONOMOUS", False))


GENERIC_FOLDER = re.compile(
    r"^(amm|amm produit|dossiers?|documents?( communs)?|decisions?|renouvellements?|origine|"
    r"scans?|pieces?|autres?|produits?|nouveau dossier|pret a importer|gamme.*|.*afrique)$"
)


def _folder_label(batch, country) -> str:
    """Nom du produit tel que le dossier le donne : son dossier le plus profond.

    « CARDIO AFRIQUE - MALI - VITAGEN INJ » → « VITAGEN INJ ». Un nom générique (« AMM »,
    « Documents ») ou un nom de pays ne désigne pas un produit.
    """
    parts = [part.strip() for part in batch.root_name.split(" - ") if part.strip()]
    label = parts[-1] if parts else ""
    key = normalize(label).replace("_", " ").strip()
    countries = {normalize(item) for item in country_labels(country)} if country else set()
    if not re.search(r"[a-z]{3}", key) or key in countries or GENERIC_FOLDER.match(key):
        return ""
    return label


def _path_country(batch, countries):
    """Pays désigné par le dossier déposé (« MALI - VITAGEN », « CARDIO AFRIQUE - MALI - … »)."""
    parts = [normalize(part) for part in batch.root_name.split(" - ") if part.strip()]
    found = [
        country
        for country in countries
        if any(part in {normalize(label) for label in country_labels(country)} for part in parts)
    ]
    return found[0] if len(found) == 1 else None


def _majority(values):
    counts = defaultdict(int)
    for value in values:
        counts[value] += 1
    return max(counts, key=lambda value: counts[value]) if counts else None


