"""Reconnaissance d'un fichier du dossier : pays, produit, période, n°, dates."""

import re
from datetime import timedelta
from pathlib import PurePosixPath

from apps.core.dates import today

from .dates import (
    _MONTH_NAMES,
    _SIGNATURE_PLACES,
    DATE_PATTERN,
    _join_spaced_days,
    _label_value,
    _labeled_date,
    _validity_period,
    parse_date,
)
from .holder import _granted_holder, _product_line
from .numbers import _authorization_number
from .sections import decision_sections, specialty_groups
from .tables import table_rows
from .text import fold, normalize


def country_labels(country) -> list[str]:
    """Noms sous lesquels un pays est imprimé ou nommé dans un dossier (« BURKINA »)."""
    name = normalize(country.name)
    labels = [country.name]
    first = name.split(" ")[0]
    if " " in name and len(first) >= 5 and first not in {"republique", "guinee", "saint"}:
        labels.append(first)  # « Burkina Faso » → « BURKINA »
    if name == "cote d ivoire":
        labels += ["ivoire", "cdi", "rci"]
    return labels


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
    plain = _join_spaced_days(fold(text))
    path = upload.relative_path
    # « : » dans un chemin macOS est un « / » du Finder (« 50MG:5ML » = « 50MG/5ML »).
    path_text = normalize(f"{root_name} {path}".replace(":", "/"))
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
    # « Notification provisoire » / « avis favorable » de la commission : l'AMM n'est pas encore
    # délivrée (« les décisions … vous parviendront ultérieurement ») : pièce annexe.
    provisional = bool(
        re.search(r"notification provisoire", header) or re.match(r"avis favorable\b", basename)
    )
    # Autorisation temporaire d'importation (Mauritanie) : document annexe, jamais une AMM.
    temporary = bool(
        re.search(r"autorisation temporaire d importation", header) or re.match(r"ati\b", basename)
    )
    decision = bool(
        re.search(
            r"\b(decision|arrete|autorisation de mise sur le marche|marketing authori[sz]ation"
            r"|visa (?:de commercialisation|d homologation|d enregistrement)|homologation"
            r"|approval for the registration|numero amm)\b",
            header,
        )
        # Décisions dont l'en-tête est illisible mais qui portent « Numéro AMM : … ».
        or re.search(r"(?:^|\n)\s*numero\s+(?:d['’ ]?)?amm\s*:", plain)
        # Titres de scans aux espaces perdus (« MISE SUR LEMARCHE ») ou en anglais seul.
        or re.search(
            r"autorisationdemisesurlemarche|authori[sz]ationtomarket|marketingauthori[sz]ation",
            header.replace(" ", ""),
        )
    )
    official = (
        decision
        and not ancillary
        and not receipt
        and not letter
        and not temporary
        and not provisional
        and reliability >= 65
    )
    # Une ATI est rangée comme pièce annexe (« Autre ») : elle ne prouve pas l'AMM.
    kind = "RECEPISSE" if receipt else "COURRIER" if letter else "AMM" if official else "AUTRE"

    product_names = [
        (product, [product.name, *[a.raw_name for a in product.aliases.all()]])
        for product in products
    ]
    explicit_product = _label_value(
        plain,
        r"(?:nom\s+(?:du\s+)?(?:produit|medicament)|produit|specialite(?:\s+pharmaceutique)?"
        r"|denomination(?:\s+(?:du\s+)?(?:medicament|produit))?|product(?:\s+name)?)",
        text,
    )
    # Décision bilingue : la dénomination occupe sa propre ligne après « pharmaceutical product ».
    product_line = "" if explicit_product else _product_line(text)
    explicit_product = explicit_product or product_line
    matched_text = _mentions(explicit_product or text, product_names)
    matched_path = _mentions(path_text, product_names)
    # Décision groupée (tableau, ou liste de plusieurs produits du catalogue) : elle ne désigne
    # pas un produit à elle seule ; la ligne du produit du dossier est choisie plus tard.
    rows = table_rows(text)
    sections = decision_sections(text)
    # Recueil de décisions (une par spécialité) : comme une décision groupée, il ne désigne pas
    # un produit à lui seul ; la section du produit du dossier est choisie plus tard.
    # Plusieurs marques : une même marque relue deux fois (« TENSOPLUS ne (… » puis « TENSOPLUS
    # 10/2,5/5 ») ou citée en référence reste une seule décision.
    groups = specialty_groups(sections)
    compilation = len(groups) >= 2 and len({key.split(" ")[0] for key in groups}) >= 2
    grouped = bool(rows) or compilation or (not explicit_product and len(matched_text) >= 3)
    if grouped:
        matched_text = []
    matched_products = matched_text or matched_path
    product_confidence = reliability if matched_text else 60 if matched_path else reliability

    explicit_country = _label_value(plain, r"pays|country", text)
    # Jamais le code ISO à deux lettres : « mg », « ml », « ne », « ci » sont des unités ou des
    # mots courants (« 100 mg » lisait Madagascar, « ne … pas » le Niger : 185 pays faux sur
    # 2 336 scans du corpus, et la question « le dossier mélange plusieurs pays » sur MAGLIFE).
    country_names = [(country, country_labels(country)) for country in countries]
    country_text = _mentions(explicit_country, country_names) if explicit_country else []
    if not country_text:
        # The first lines describe the issuing authority; a manufacturer's address does not.
        authority_lines = "\n".join(
            line
            for line in plain.splitlines()[:14]
            if re.search(r"republique|republic|ministere|pays|country", line)
        )
        country_text = _mentions(authority_lines, country_names)
    # Un dossier nommé du seul code pays (« SN/… », « ML - … ») le désigne sans ambiguïté.
    segments = {
        part.strip() for chunk in f"{root_name}/{path}".split("/") for part in chunk.split(" - ")
    }
    country_path = _mentions(path_text, country_names) or [
        country for country in countries if country.iso2 and country.iso2 in segments
    ]
    matched_countries = country_text or country_path
    country_confidence = reliability if country_text else 65 if country_path else 0

    labeled_number = _label_value(
        plain,
        r"(?:numero|n[°ºo.]*)\s*(?:d['’ ]*)?(?:amm|autorisation(?: de mise sur le marche)?)"
        r"|(?:amm|autorisation de mise sur le marche)\s*(?:n[°ºo.]*|numero)?"
        r"|(?:numero|n[°ºo.]*)\s*(?:du\s+)?renouvellement",
        text,
    )
    # Coupe « 00152 du 28/04/2025 » : recherche sur la forme repliée, découpe sur l'original.
    # Certificat guinéen : « PGHT N° E-AMM Début de validité Fin de validité » puis, ligne
    # suivante, « 22 EURO 5264 21/05/2024 21/05/2029 ».
    certificate = re.search(
        r"n\S{0,2}\s*[a-z]?\W?amm[^\n]*debut\s+de\s+validite[^\n]*\n[^\n]*?(?<![\d,.])(\d{4,6})\s+"
        r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}/\d{1,2}/\d{4})",
        plain,
    )
    if certificate and not labeled_number:
        labeled_number = certificate.group(1)
    cut = re.search(r"\s+(?:du|date|delivre|valable|pour)\b", fold(labeled_number))
    if cut:
        labeled_number = labeled_number[: cut.start()]
    # La décision est l'AMM elle-même : son numéro est le numéro d'AMM (Congo « visa
    # d'homologation », Mali « DECISION N° 2022-002328 … portant autorisation de mise sur le
    # marché »), faute de toute autre mention.
    decision_is_amm = bool(
        re.search(
            r"visa d.?homologation|portant homologation"
            r"|portant\s+autorisation\s+de\s+mise\s+sur\s+le\s+marche",
            plain[:3000],
        )
    )
    number, number_variants = _authorization_number(
        plain, text, labeled_number.upper()[:100], decision_is_amm
    )
    holder = (
        _label_value(
            plain,
            r"titulaire(?:\s+de\s+l['’ ]?amm)?|laboratoire|holder"
            r"|marketing authori[sz]ation holder",
            text,
        )
        or _granted_holder(text)
    )[:255]
    start_date = _labeled_date(
        plain,
        r"date\s+(?:de\s+)?(?:debut|delivrance|de\s+delivrance|prise d['’ ]effet)"
        r"|delivree?\s+le|debut\s+de\s+validite|valable\s+(?:a compter du|du)"
        r"|date\s+d['’ ]effet|start\s+date|registration\s+date|date\s+of\s+registration"
        r"|date\s+d['’ ]enregistrement|date\s+du\s+visa",
    )
    decision_date = _labeled_date(
        plain,
        r"date\s+(?:de\s+)?(?:decision|signature)|decision\s+du|fait\s+a\s+[^\n,]{1,50},?\s+le",
    )
    end_date = _labeled_date(
        plain,
        r"date\s+(?:de\s+)?fin|date\s+d['’ ]expiration|expire\s+le|valable\s+jusqu['’ ]au"
        r"|fin\s+de\s+validite|end\s+date|expiration\s+date|expiry\s+date",
    )
    # « Numéro AMM : 0003/CN/06/2019 du 09 Déc. 2019 au 08 Déc. 2024 »
    # « … renouvelée pour une durée de cinq (5) ans allant du 27 avril 2025 au 27 avril 2030 »
    period_range = re.search(
        rf"(?:amm|visa|numero|n[°º]|allant|valable|validite|periode)[^\n]{{0,60}}?\bdu\s+"
        rf"({DATE_PATTERN})\s+au\s+({DATE_PATTERN})",
        plain,
    )
    ministerial = re.search(
        rf"decision\s+ministerielle[^\n]{{0,70}}?\bdu\s+({DATE_PATTERN})", plain
    )
    if ministerial and not start_date:
        start_date = parse_date(ministerial.group(1))
    if certificate and not start_date:
        start_date = parse_date(certificate.group(2))
        end_date = end_date or parse_date(certificate.group(3))
    if not start_date:
        # Certificat dont le tableau « Début de validité | Fin de validité » est lu colonne par
        # colonne : les deux dates suivent l'en-tête de quelques lignes.
        columns = re.search(
            r"debut\s+de\s+validite\s*\|?\s*fin\s+de\s+validite[\s\S]{0,200}?"
            r"(\d{1,2}/\d{1,2}/\d{4})\s*\|?\s*(\d{1,2}/\d{1,2}/\d{4})",
            plain,
        )
        if columns:
            start_date = parse_date(columns.group(1))
            end_date = end_date or parse_date(columns.group(2))
    if period_range and not start_date:
        start_date = parse_date(period_range.group(1))
        end_date = end_date or parse_date(period_range.group(2))
    if not decision_date:
        # Lieu et date de signature en tête ou en pied (« COTONOU, le 16 AVR 2019 »,
        # « Bamako, le 24 SEP 2020 », « Djibouti le 27/02/2024 »).
        signed = re.search(
            rf"(?:^|\n)[^\n]{{0,60}}?\b(?:{_SIGNATURE_PLACES}|fait\s+a\s+[a-z' -]{{3,25}})"
            rf"\s*,?\s*(?:le|lc|te)\s*[.:,]?\s*({DATE_PATTERN})",
            plain,
        )
        decision_date = parse_date(signed.group(1)) if signed else None
    if not decision_date:
        # Sénégal : tampon d'enregistrement de l'arrêté « 15.04.2026*009037 », « 14 DEC
        # 2018*026674 » (date puis numéro d'ordre) en tête de la première page.
        stamp = re.search(
            rf"(?<![\d/.])(\d{{1,2}}\s?[./]\s?\d{{1,2}}\s?[./]\s?(?:19|20)\d\d"
            rf"|\d{{1,2}}\s?(?:{_MONTH_NAMES})\.?\s?(?:19|20)\d\d)\d?\s*[*+][:;]?\s*[0-9o]",
            plain[:2500],
        ) or re.search(
            # « 10.06.2016 08452 » : tampon sans astérisque, seul en début de ligne.
            r"(?:^|\n)[^\S\n]*(\d{1,2}\.\d{1,2}\.(?:19|20)\d\d)[^\S\n]+\d{4,6}[^\S\n]*(?=\n|$)",
            plain[:2500],
        )
        if stamp:
            raw = re.sub(r"\s+", " ", stamp.group(1))
            # « 15. 04.2026 » se recolle ; « 06 DEC. 2022 » (mois en lettres) se lit tel quel.
            decision_date = parse_date(re.sub(r"\s?([./])\s?", r"\1", raw)) or parse_date(
                re.sub(r"([a-z])\.?\s?(\d)", r"\1 \2", raw)  # « 06 DEC. 2022 », « 01 JUIN2021 »
            )
    if not decision_date:
        # Lieu mal lu (« CORONOU, le 16 AVR 2019 ») : toute ligne courte « Ville, le <date> ».
        signed = re.search(
            rf"(?:^|\n)[^\n]{{0,25}}?\b[a-z][a-z'-]{{3,20}}(?: [a-z'-]{{2,15}})?\s*,\s*"
            rf"(?:le|lc|te)\s*[.:,]?\s*({DATE_PATTERN})[^\n]{{0,20}}(?=\n|$)",
            plain,
        )
        decision_date = parse_date(signed.group(1)) if signed else None
    if not decision_date:
        # Mali : « DECISION N° 2018-001928/MSHP-SG DU 28 DEC 2018 » (date du tampon d'en-tête).
        headed = re.search(
            rf"(?:^|\n)[ \t]*decision\s+n\S{{0,2}}[^\n]{{0,60}}?\bdu\s+({DATE_PATTERN})",
            plain[:3000],
        )
        decision_date = parse_date(headed.group(1)) if headed else None
    # Au Sénégal, l'avis de la « Commission nationale du médicament » précède l'AMM de plusieurs
    # mois ; au Niger, la décision reprend sa date.
    niger_commission = (
        r"|commission\s+nationale\s+du\s+medicament"
        if any(getattr(country, "iso2", "") == "NE" for country in matched_countries)
        else ""
    )
    if not decision_date:
        # Niger : la décision reprend la date de l'avis de la commission d'homologation.
        opinion = re.search(
            rf"(?:commission\s+nationale\s+d.?homologation|\bcnh\w*{niger_commission})"
            rf"[^\n]{{0,120}}?en\s+date\s+du\s*({DATE_PATTERN})",
            plain,
        )
        decision_date = parse_date(opinion.group(1)) if opinion else None
    if not end_date and start_date:
        interval = re.search(rf"valable\s+du\s+{DATE_PATTERN}\s+au\s+({DATE_PATTERN})", plain)
        end_date = parse_date(interval.group(1)) if interval else None
    if not start_date:
        # « La validité de cette autorisation est limitée à cinq (5) ans à partir du … »
        validity_start, validity_end = _validity_period(plain)
        if validity_start:
            start_date = validity_start
            end_date = end_date if end_date and end_date > start_date else validity_end
    # Une décision ne peut être signée demain : une date de signature future est une lecture
    # de tampon fautive (« Bamako, le 21 OCT 2071 », « 29 AOUT 2822 »).
    horizon = (today() + timedelta(days=31)).isoformat()
    decision_date = decision_date if not decision_date or decision_date <= horizon else None
    if (
        not start_date
        and decision_date
        and re.search(r"(?:compter|partir)\s+de\s+la\s+date\s+de\s+(?:sa\s+)?signature", plain)
    ):
        # Mali : « … cinq (5) ans pour compter de la date de signature de la présente décision ».
        start_date = decision_date

    # The nearest renewal directory is stable across files and retains multiple periods.
    renewal_parts = [
        normalize(part)
        for part in PurePosixPath(path).parts[:-1]
        if re.search(r"\b(renouvellement|renouv|renewal)\b", normalize(part))
    ]
    # « La demande de renouvellement de l'AMM doit être déposée… » figure aussi dans une AMM
    # d'origine : cette clause ne fait pas d'une décision un renouvellement.
    renewal_header = re.sub(
        r"demande de renouvellement|application for (?:the )?renewal", " ", header
    )
    renewal_content = bool(re.search(r"\b(renouvellement|renewal)\b", renewal_header)) or bool(
        re.search(
            r"renouvellement de l['’ ]?autorisation|renewal of the authori[sz]ation"
            r"|\best[ -]renouvelee\b|\bis hereby renewed\b",
            plain,
        )
    )
    renewal_filename = bool(re.search(r"\b(renouvellement|renouv|renewal)\b", basename))
    is_renewal = bool(renewal_parts or renewal_content or renewal_filename)
    if not start_date and not decision_date and not is_renewal:
        # « l'AMM n° 5735 du 22/12/2010 », « autorisation de mise sur le marché n°003610 du
        # 23 février 2022 » : la date accolée au n° d'AMM est celle de l'AMM. Pas dans un
        # renouvellement, où elle désigne l'AMM d'origine renouvelée ; pas « dossier enregistré
        # sous le n° … du … » (Bénin), qui date le dépôt.
        dated = re.search(
            r"(?:\bamm\b|autorisation\s+de\s+mise\s+sur\s+le\s+marche)"
            rf"[^\n]{{0,20}}?n\W{{0,3}}\s*[\w/.-]{{3,30}}(?:\s*\(?bis\)?)?\s*,?\s*"
            rf"(?:du|en\s+date\s+du)\s*({DATE_PATTERN})",
            plain,
        )
        if dated:
            start_date = parse_date(re.sub(r"\s?/\s?", "/", dated.group(1)))
    cited_original = None
    if is_renewal:
        # Sénégal : « … l'AMM n° 5735 du 22/12/2010 est renouvelée pour … » : le renouvellement
        # cite l'AMM d'origine, son n° et sa date.
        cited = re.search(
            rf"\bamm\s+n\W{{0,3}}\s*([\w/.-]{{3,30}}(?:\s*\(?bis\)?)?)\s*,?\s*du\s*"
            rf"({DATE_PATTERN})\s*,?\s*(?:est|a\s+ete)\s+renouvele",
            plain,
        )
        if cited:
            cited_original = {
                "number": cited.group(1).strip().upper(),
                "start_date": parse_date(cited.group(2)),
            }
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
        # Libellé « Produit : … » ou simple ligne de dénomination (insuffisante pour créer).
        "explicit_product_labeled": bool(explicit_product) and not product_line,
        "product_source": "text" if matched_text else "path" if matched_path else "",
        "product_confidence": product_confidence,
        "grouped": grouped,
        "temporary_import": temporary,
        "table_rows": rows,
        "sections": sections if compilation else [],
        # Décision unique qui nomme sa spécialité (« … pour la spécialité : PALUCARE 20 mg »).
        "specialty": sections[0]["specialty"] if len(sections) == 1 else "",
        "country_ids": [str(country.pk) for country in matched_countries],
        "country_confidence": country_confidence,
        # Le numéro d'une décision groupée est celui de la ligne du produit, pas celui de l'acte.
        "number": number if official and not grouped else "",
        "number_variants": number_variants if official and not grouped else [],
        "holder": holder if official else "",
        "start_date": start_date if official else None,
        "decision_date": decision_date if official else None,
        "end_date": end_date if official else None,
        # AMM d'origine citée par une décision de renouvellement (n° et date).
        "cited_original": cited_original if official else None,
        # Un récépissé porte la date de dépôt (« Déposé le 01/03/2026 »), pas une date « Date : ».
        "document_date": decision_date
        or start_date
        or _labeled_date(plain, r"date|deposee?\s+le|recu\s+le|received\s+on"),
    }
