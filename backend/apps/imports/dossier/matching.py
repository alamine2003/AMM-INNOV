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
_SYNONYMS = {"fl": "f", "pdr": "pdre", "cp": "cpr", "comp": "cpr", "sachet": "sach", "coll": "col"}
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


def _numbers_distance(first: list[str], second: list[str]) -> int:
    from .recognition import _edit_distance

    joined = "|".join(first), "|".join(second)
    ordered = "|".join(sorted(first)), "|".join(sorted(second))
    return min(_edit_distance(*joined), _edit_distance(*ordered))


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
            return None, "Plusieurs produits du catalogue correspondent au nom du dossier."
        return best[3], ""
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


def pick_table_row(rows: list[dict], product, products) -> dict | None:
    """Ligne d'une décision groupée qui désigne `product` ; None si absente ou ambiguë."""
    matches = []
    for row in rows:
        if name_compatible(row["label"], product, products):
            words, _ = _parts(row["label"])
            target, _ = _parts(product.name)
            ratio = SequenceMatcher(None, " ".join(words), " ".join(target)).ratio()
            matches.append((ratio, row))
    if not matches:
        return None
    matches.sort(key=lambda item: -item[0])
    if len(matches) > 1 and matches[0][0] - matches[1][0] < 0.05:
        # Même dénomination répétée (colonnes relues deux fois) : même numéro = pas d'ambiguïté.
        if normalize(matches[0][1]["number"]) != normalize(matches[1][1]["number"]):
            return None
    return matches[0][1]
