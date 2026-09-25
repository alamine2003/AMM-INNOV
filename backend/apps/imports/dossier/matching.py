"""Country-scoped, multiple-criterion matching; an AMM number alone never identifies a record."""

import re
from difflib import SequenceMatcher

from apps.amm.models import MarketingAuthorization, Renewal

from .recognition import normalize


def match_authorizations(user, product, country, evidence: list[dict]) -> list[dict]:
    if not country:
        return []
    queryset = MarketingAuthorization.objects.select_related("product", "country")
    if not user or not user.is_authenticated:
        return []
    if not user.is_global:
        queryset = queryset.filter(country__in=user.countries.all())
    queryset = queryset.filter(country=country)
    if product:
        queryset = queryset.filter(product=product)
    else:
        return []
    candidates = []
    for amm in queryset:
        score, reasons = 75, ["Produit reconnu dans le catalogue", "Pays concordant"]
        official = [row for row in evidence if row["official"]]
        textual_identity = any(
            row["product_confidence"] >= 90 and row["country_confidence"] >= 90 for row in official
        )
        if textual_identity:
            score += 15
            reasons.append("Produit et pays présents dans une décision officielle lisible")
        elif any(row["product_confidence"] >= 65 for row in official):
            score += 5
            reasons.append("Identification documentaire à confirmer")
        else:
            score = 60
            reasons.append("Identification reposant sur les noms de fichiers ou dossiers")
        originals = [row for row in official if row["period"] == "original"]
        if any(
            normalize(row["number"]) == normalize(amm.original_number)
            for row in originals
            if row["number"] and amm.original_number
        ):
            score += 3
            reasons.append("Numéro d'origine concordant")
        if amm.original_start_date and any(
            row["start_date"] == amm.original_start_date.isoformat() for row in originals
        ):
            score += 3
            reasons.append("Date d'origine concordante")
        if getattr(amm, "holder", "") and any(
            SequenceMatcher(None, normalize(row["holder"]), normalize(amm.holder)).ratio() >= 0.95
            for row in official
            if row["holder"]
        ):
            score += 3
            reasons.append("Titulaire concordant")
        if not textual_identity:
            score = min(score, 85)
        candidates.append(
            {
                "id": str(amm.pk),
                "product_name": amm.product.name,
                "country_iso2": amm.country.iso2,
                "confidence": min(score, 98),
                "reasons": reasons,
            }
        )
    return sorted(candidates, key=lambda item: (-item["confidence"], item["id"]))


def resolve_renewal(amm, values: dict, exclude=()):
    """A number may be reused across renewals; dates and linked period must disambiguate.

    `exclude` lists renewal ids already claimed by another period of the same dossier.
    """
    if not amm:
        return None, False
    rows = [row for row in amm.renewals.all() if str(row.pk) not in set(exclude)]
    start = values.get("start_date")
    decision = values.get("decision_date")
    date_matches = [
        row
        for row in rows
        if (
            (start and row.start_date and row.start_date.isoformat() == start)
            or (decision and row.decision_date and row.decision_date.isoformat() == decision)
        )
    ]
    if len(date_matches) == 1:
        return date_matches[0], False
    if len(date_matches) > 1:
        return None, True
    number = normalize(values.get("number", ""))
    number_matches = [row for row in rows if number and normalize(row.number) == number]
    if number_matches:
        # Same number with a different known date is commonly a separate renewal period.
        undated = [row for row in number_matches if not row.start_date and not row.decision_date]
        if len(undated) == 1 and len(number_matches) == 1:
            return undated[0], False
        if not start and not decision:
            return (number_matches[0], False) if len(number_matches) == 1 else (None, True)
    # Un renouvellement déjà suivi dans l'application (planifié, en préparation, déposé, en
    # instruction) sans numéro ni date est le dossier que la décision importée vient conclure :
    # on le complète plutôt que d'en créer un second en parallèle.
    open_undated = [
        row
        for row in rows
        if row.workflow_status in Renewal.OPEN_STATUSES and not row.number and not row.start_date
    ]
    if len(open_undated) == 1 and (start or decision):
        return open_undated[0], False
    return None, False


# Abréviations interchangeables des libellés du catalogue (« FL/100ML » = « F100ML »).
_SYNONYMS = {
    "fl": "f", "flacon": "f", "pdr": "pdre", "poudre": "pdre", "cp": "cpr", "comp": "cpr",
    "comprime": "cpr", "comprimes": "cpr", "sachet": "sach", "sachets": "sach", "coll": "col",
    "collyre": "col", "suspension": "susp", "gelule": "gel", "gelules": "gel", "caps": "capsule",
    "sirop": "sp", "injectable": "inj", "perfusion": "perf", "ampoule": "amp", "ampoules": "amp",
    "goutte": "gtte", "gouttes": "gtte", "effervescent": "effv", "effervescents": "effv",
}  # fmt: skip
_UNITS = {"mg", "g", "mcg", "ml", "ui", "iu"}


def _amount(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _parts(name: str) -> tuple[list[str], list[str]]:
    """Mots et nombres d'un libellé ; « 1G » devient 1000 (mg) pour comparer les dosages."""
    text = normalize(re.sub(r"(\d)[.,](\d)", r"\1p\2", name))
    words, numbers = [], []
    for value, unit in re.findall(r"(\d+(?:p\d+)?)\s*([a-z]*)", text):
        amount = float(value.replace("p", "."))
        if unit == "g":
            amount *= 1000
        numbers.append(_amount(amount))
    for word in re.findall(r"[a-z]+", re.sub(r"\d+(?:p\d+)?", " ", text)):
        words.append(_SYNONYMS.get(word, word))
    return words, numbers


def _numbers_distance(first: list[str], second: list[str]) -> float:
    """Écart entre dosages ; l'ordre compte (« 10MG/5MG » n'est pas « 5MG/10MG ») : dans le
    désordre, les mêmes nombres coûtent un demi-point, sous une vraie concordance."""
    from .recognition import _edit_distance

    joined = _edit_distance("|".join(first), "|".join(second))
    unordered = _edit_distance("|".join(sorted(first)), "|".join(sorted(second)))
    return joined if joined <= unordered else unordered + 0.5


# Famille de forme : un comprimé n'est jamais la suspension de la même marque (« GENFORTE CP
# B100 » n'est pas « GENFORTE 100MG/125MG SUSP BUV », malgré le « 100 »).
_FORM_FAMILIES = {
    "cpr": "oral_solide", "gel": "oral_solide", "capsule": "oral_solide", "effv": "oral_solide",
    "sp": "oral_liquide", "susp": "oral_liquide", "buv": "oral_liquide",
    "inj": "injectable", "amp": "injectable", "perf": "injectable", "seringue": "injectable",
    "col": "oculaire",
    "creme": "cutane", "pde": "cutane", "pommade": "cutane", "der": "cutane",
    "suppo": "rectal", "ovule": "vaginal", "vag": "vaginal", "inh": "inhale",
}  # fmt: skip


def _forms(words: list[str]) -> set[str]:
    return {_FORM_FAMILIES[word] for word in words if word in _FORM_FAMILIES}


def _brand_in_country(labels, products, preferred) -> object | None:
    """Dernier recours : la marque et les dosages désignent une seule AMM du pays.

    « GENCLAV 1G 125MG B10 SACHETS » (Congo) est « GENCLAV 1G/125MG PDRE SUSP BUV SACH/10 » ;
    « GENFER » seul est la seule présentation GENFER du pays.
    """
    for label in labels:
        label_words, label_numbers = _parts(label.replace(":", "/"))
        if not label_words or len(label_words[0]) < 4:
            continue
        same_brand = []
        for product in products:
            if str(product.pk) not in preferred:
                continue
            words, numbers = _parts(product.name)
            if not words or (
                words[0] != label_words[0]
                and SequenceMatcher(None, words[0], label_words[0]).ratio() < 0.85
            ):
                continue
            label_forms, forms = _forms(label_words), _forms(words)
            if label_forms and forms and not label_forms & forms:
                continue
            same_brand.append((product, numbers))
        if label_numbers:
            same_brand = [
                (product, numbers)
                for product, numbers in same_brand
                if numbers[: len(label_numbers)] == label_numbers or numbers == label_numbers
            ]
        if len(same_brand) == 1:
            return same_brand[0][0]
    return None


def folder_product(labels: list[str], products, preferred_ids=()) -> tuple[object, str]:
    """Produit du catalogue désigné par un nom de dossier, avec tolérance aux fautes de frappe.

    Les dosages doivent concorder (au plus une faute de frappe : « 159MG » pour « 15MG »,
    « B3:0 » pour « B/30 ») et le reste du libellé être très proche. Les produits ayant une AMM
    dans le pays (`preferred_ids`) sont examinés d'abord. Renvoie (produit, "") ou
    (None, motif) quand le nom est absent, trop éloigné ou ambigu.
    """
    preferred = {str(pk) for pk in preferred_ids}
    scored = []
    for label in labels:
        label_words, label_numbers = _parts(label.replace(":", "/"))
        if not label_words:
            continue
        for product in products:
            words, numbers = _parts(product.name)
            if (
                not words
                or words[0] != label_words[0]
                and SequenceMatcher(None, words[0], label_words[0]).ratio() < 0.85
            ):
                continue
            distance = _numbers_distance(label_numbers, numbers)
            if distance > 1:
                continue
            ratio = SequenceMatcher(None, "".join(label_words), "".join(words)).ratio()
            ordered = SequenceMatcher(
                None, "".join(sorted(label_words)), "".join(sorted(words))
            ).ratio()
            ratio = max(ratio, ordered)
            if ratio >= 0.85:
                scored.append((distance, -ratio, str(product.pk) not in preferred, product))
    if not scored:
        fallback = _brand_in_country(labels, products, preferred)
        if fallback:
            return fallback, ""
        return None, "Aucun produit du catalogue ne correspond au nom du dossier."
    for in_country in (True, False):
        pool = [row for row in scored if row[2] != in_country]
        if not pool:
            continue
        pool.sort(key=lambda row: (row[0], row[1], str(row[3].pk)))
        best = pool[0]
        rivals = {
            str(row[3].pk) for row in pool if row[0] == best[0] and -row[1] >= -best[1] - 0.02
        }
        if len(rivals) > 1:
            fallback = _brand_in_country(labels, products, preferred)
            if fallback and str(fallback.pk) in rivals:
                return fallback, ""
            return None, "Plusieurs produits du catalogue correspondent au nom du dossier."
        return best[3], ""
    fallback = _brand_in_country(labels, products, preferred)
    if fallback:
        return fallback, ""
    return None, "Aucun produit du catalogue ne correspond au nom du dossier."


def name_compatible(explicit: str, product, products) -> bool:
    """La dénomination imprimée (« GENSET 10MG », « ARTRIM-GH ») désigne-t-elle ce produit ?

    Même marque, dosages imprimés présents dans le libellé du catalogue, et aucun mot
    distinctif d'une autre présentation de la marque (« DOLEX SR » n'est pas « DOLEX 50MG »).
    """
    words, numbers = _parts(explicit)
    target_words, target_numbers = _parts(product.name)
    if not words or not target_words:
        return False
    if words[0] != target_words[0] and (
        SequenceMatcher(None, words[0], target_words[0]).ratio() < 0.8 or len(words[0]) < 4
    ):
        return False
    folded = re.sub(r"(\d)[.,](\d)", r"\1p\2", explicit.lower())
    strengths = []
    for match in re.finditer(r"(\d+(?:p\d+)?)\s*(mcg|mg|g|%)?", folded):
        value, unit = match.groups()
        following = folded[match.end() : match.end() + 1]
        if unit and following.isalpha() and following not in "x":
            unit = None if unit != "mg" or not following.isdigit() else unit
        if not unit and (following.isalpha() or strengths):
            break
        amount = float(value.replace("p", ".")) * (1000 if unit == "g" else 1)
        strengths.append(_amount(amount))
        if not unit:
            break
    if any(value not in target_numbers for value in strengths):
        return False
    siblings = set()
    for other in products:
        other_words, _ = _parts(other.name)
        if other.pk != product.pk and other_words and other_words[0] == target_words[0]:
            siblings.update(other_words)
    distinctive = {word for word in words[1:] if len(word) >= 2 and word not in _UNITS} - set(
        target_words
    )
    return not (distinctive & siblings)


def _label_similarity(label: str, product) -> float:
    """Ressemblance d'une ligne de tableau avec un produit : marque, dosages, puis libellé."""
    words, numbers = _parts(label.replace(":", "/"))
    target, target_numbers = _parts(product.name)
    if not words or not target:
        return 0.0
    if words[0] != target[0] and SequenceMatcher(None, words[0], target[0]).ratio() < 0.8:
        return 0.0
    # Les dosages du produit doivent tous figurer sur la ligne (une faute de frappe tolérée).
    missing = [value for value in target_numbers if value not in numbers]
    if len(missing) > 1:
        return 0.0
    ratio = max(
        SequenceMatcher(None, " ".join(words), " ".join(target)).ratio(),
        SequenceMatcher(None, " ".join(sorted(words)), " ".join(sorted(target))).ratio(),
    )
    return ratio - 0.2 * len(missing)


def pick_table_row(rows: list[dict], product, products) -> dict | None:
    """Ligne d'une décision groupée qui désigne `product` ; None si absente ou ambiguë.

    Une ligne n'est retenue que si `product` est, parmi les produits du pays, celui qui lui
    ressemble le plus : la ligne « AMLODIPINE-GH 5MG » n'est jamais attribuée au 10MG.
    """
    others = [item for item in products if item.pk != product.pk]
    matches = []
    for row in rows:
        score = _label_similarity(row["label"], product)
        if name_compatible(row["label"], product, products):
            # Dénomination imprimée compatible (marque, dosages, pas d'autre présentation).
            matches.append((max(score, 0.5) + 1, row))
            continue
        if score < 0.5:
            continue
        if any(_label_similarity(row["label"], other) > score for other in others):
            continue
        matches.append((score, row))
    if not matches:
        return None
    matches.sort(key=lambda item: -item[0])
    best = matches[0]
    rivals = [row for score, row in matches[1:] if best[0] - score < 0.03]
    # Même dénomination relue deux fois (colonnes) : même numéro = pas d'ambiguïté.
    if any(normalize(row["number"]) != normalize(best[1]["number"]) for row in rivals):
        return None
    return best[1]
