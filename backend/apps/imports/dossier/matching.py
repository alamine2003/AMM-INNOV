"""Country-scoped, multiple-criterion matching; an AMM number alone never identifies a record."""

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
