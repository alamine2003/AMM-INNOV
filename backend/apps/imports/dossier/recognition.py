"""Conservative, explainable recognition of regulatory fields and dossier periods."""

import re
import unicodedata
from datetime import date
from pathlib import PurePosixPath


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


MONTHS = {
    "janvier": 1,
    "january": 1,
    "fevrier": 2,
    "february": 2,
    "mars": 3,
    "march": 3,
    "avril": 4,
    "april": 4,
    "mai": 5,
    "may": 5,
    "juin": 6,
    "june": 6,
    "juillet": 7,
    "july": 7,
    "aout": 8,
    "august": 8,
    "septembre": 9,
    "september": 9,
    "octobre": 10,
    "october": 10,
    "novembre": 11,
    "november": 11,
    "decembre": 12,
    "december": 12,
}
DATE_PATTERN = (
    r"(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4}"
    r"|\d{1,2}\s+(?:" + "|".join(MONTHS) + r")\s+\d{4})"
)


def parse_date(value: str) -> str | None:
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    match = re.search(DATE_PATTERN, plain)
    if not match:
        return None
    parts = re.split(r"[-/.\s]+", match.group())
    try:
        if parts[1] in MONTHS:
            day, month, year = int(parts[0]), MONTHS[parts[1]], int(parts[2])
        elif len(parts[0]) == 4:
            year, month, day = map(int, parts)
        else:
            day, month, year = map(int, parts)
        if not 1950 <= year <= 2150:
            return None
        return date(year, month, day).isoformat()
    except (ValueError, KeyError):
        return None


def _label_value(text: str, labels: str) -> str:
    match = re.search(rf"(?:^|\n)\s*(?:{labels})\s*(?::|=|\s[-–]\s)\s*([^\n]{{1,255}})", text, re.I)
    return match.group(1).strip(" \t.;") if match else ""


def _labeled_date(text: str, labels: str) -> str | None:
    match = re.search(rf"(?:{labels})\s*(?::|=|du|le)?\s*({DATE_PATTERN})", text, re.I)
    return parse_date(match.group(1)) if match else None


def _mentions(text: str, names) -> list:
    padded = f" {normalize(text)} "
    matches = []
    for obj, labels in names:
        hits = [normalize(label) for label in labels if normalize(label)]
        hits = [label for label in hits if f" {label} " in padded]
        if hits:
            matches.append((obj, max(hits, key=len)))
    # A presentation's complete name beats its generic-name prefix.
    return [
        obj
        for obj, hit in matches
        if not any(hit != longer and f" {hit} " in f" {longer} " for _, longer in matches)
    ]


def recognize_file(upload, countries, products, root_name: str = "") -> dict:
    extraction = upload.extraction or {}
    text = extraction.get("text", "")[:160_000]
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    path = upload.relative_path
    path_text = normalize(f"{root_name} {path}")
    basename = normalize(PurePosixPath(path).name)
    header = normalize(text[:1200])
    reliability = min(98, int(extraction.get("confidence", 0)))
    if extraction.get("source") == "ocr":
        reliability = min(reliability, 80)

    # A leaflet can quote an authorization number without being the decision that proves it.
    ancillary = bool(re.search(r"\b(rcp|notice|leaflet|resume des caracteristiques)\b", basename))
    ancillary = ancillary or bool(re.match(r"(?:resume des caracteristiques|notice\b)", header))
    receipt = bool(
        re.search(r"\b(recepisse|accuse de reception|receipt)\b", header + " " + basename)
    )
    letter = bool(re.search(r"\b(courrier|lettre|letter)\b", basename))
    decision = bool(
        re.search(
            r"\b(decision|arrete|autorisation de mise sur le marche|marketing authori[sz]ation)\b",
            header,
        )
    )
    official = decision and not ancillary and not receipt and not letter and reliability >= 65
    kind = "RECEPISSE" if receipt else "COURRIER" if letter else "AMM" if official else "AUTRE"

    product_names = [
        (product, [product.name, *[a.raw_name for a in product.aliases.all()]])
        for product in products
    ]
    explicit_product = _label_value(
        plain,
        r"(?:nom\s+(?:du\s+)?(?:produit|medicament)|produit|specialite(?:\s+pharmaceutique)?"
        r"|denomination(?:\s+(?:du\s+)?(?:medicament|produit))?|product(?:\s+name)?)",
    )
    matched_text = _mentions(explicit_product or text, product_names)
    matched_path = _mentions(path_text, product_names)
    matched_products = matched_text or matched_path
    product_confidence = reliability if matched_text else 60 if matched_path else reliability

    explicit_country = _label_value(plain, r"pays|country")
    country_names = [(country, [country.name, country.iso2]) for country in countries]
    country_text = _mentions(explicit_country, country_names) if explicit_country else []
    if not country_text:
        # The first lines describe the issuing authority; a manufacturer's address does not.
        authority_lines = "\n".join(
            line
            for line in plain.splitlines()[:14]
            if re.search(r"republique|republic|ministere|pays|country", line)
        )
        country_text = _mentions(authority_lines, country_names)
    country_path = _mentions(path_text, country_names)
    matched_countries = country_text or country_path
    country_confidence = reliability if country_text else 65 if country_path else 0

    number = _label_value(
        plain,
        r"(?:numero|n[°ºo.]*)\s*(?:d['’ ]*)?(?:amm|autorisation(?: de mise sur le marche)?)"
        r"|(?:amm|autorisation de mise sur le marche)\s*(?:n[°ºo.]*|numero)?"
        r"|(?:numero|n[°ºo.]*)\s*(?:du\s+)?renouvellement",
    )
    if not number:
        number_match = re.search(
            r"(?:amm|autorisation de mise sur le marche)\s*(?:n[°ºo.]*(?:\s*)|numero\s+)"
            r"([a-z0-9][a-z0-9/_.-]{2,99})",
            plain,
            re.I,
        )
        number = number_match.group(1) if number_match else ""
    number = re.split(r"\s+(?:du|date|delivre|valable|pour)\b", number, maxsplit=1)[0]
    number = number.upper()[:100]
    holder = _label_value(
        plain,
        r"titulaire(?:\s+de\s+l['’ ]?amm)?|laboratoire|holder|marketing authori[sz]ation holder",
    )[:255]
    start_date = _labeled_date(
        plain,
        r"date\s+(?:de\s+)?(?:debut|delivrance|de\s+delivrance|prise d['’ ]effet)"
        r"|delivree?\s+le|debut\s+de\s+validite|valable\s+(?:a compter du|du)"
        r"|date\s+d['’ ]effet|start\s+date",
    )
    decision_date = _labeled_date(
        plain,
        r"date\s+(?:de\s+)?(?:decision|signature)|decision\s+du|fait\s+a\s+[^\n,]{1,50},?\s+le",
    )
    end_date = _labeled_date(
        plain,
        r"date\s+(?:de\s+)?fin|date\s+d['’ ]expiration|expire\s+le|valable\s+jusqu['’ ]au"
        r"|fin\s+de\s+validite|end\s+date|expiration\s+date",
    )
    if not end_date and start_date:
        interval = re.search(rf"valable\s+du\s+{DATE_PATTERN}\s+au\s+({DATE_PATTERN})", plain)
        end_date = parse_date(interval.group(1)) if interval else None

    # The nearest renewal directory is stable across files and retains multiple periods.
    renewal_parts = [
        normalize(part)
        for part in PurePosixPath(path).parts[:-1]
        if re.search(r"\b(renouvellement|renouv|renewal)\b", normalize(part))
    ]
    renewal_content = bool(re.search(r"\b(renouvellement|renewal)\b", header))
    renewal_filename = bool(re.search(r"\b(renouvellement|renouv|renewal)\b", basename))
    is_renewal = bool(renewal_parts or renewal_content or renewal_filename)
    period = "original"
    uncertain_period = False
    if is_renewal:
        if renewal_parts:
            period = "renewal-" + renewal_parts[-1].replace(" ", "-")
        elif start_date or decision_date:
            period = "renewal-" + (start_date or decision_date)
        elif number and official:
            period = "renewal-" + normalize(number).replace(" ", "-")
        else:
            period = "renewal-unresolved"
            uncertain_period = True
    original_folder = any(
        re.search(r"\b(origine|original|initiale?)\b", normalize(part))
        for part in PurePosixPath(path).parts[:-1]
    )
    if original_folder and is_renewal and official:
        uncertain_period = True

    return {
        "file_id": str(upload.pk),
        "path": path,
        "kind": kind,
        "official": official,
        "period": period,
        "uncertain_period": uncertain_period,
        "confidence": reliability,
        "product_ids": [str(product.pk) for product in matched_products],
        "product_name": matched_products[0].name
        if len(matched_products) == 1
        else explicit_product,
        "explicit_product_name": explicit_product,
        "product_confidence": product_confidence,
        "country_ids": [str(country.pk) for country in matched_countries],
        "country_confidence": country_confidence,
        "number": number if official else "",
        "holder": holder if official else "",
        "start_date": start_date if official else None,
        "decision_date": decision_date if official else None,
        "end_date": end_date if official else None,
        "document_date": decision_date or start_date or _labeled_date(plain, r"date"),
    }
