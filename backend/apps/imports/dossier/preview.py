"""Plan de rangement d'un dossier, sans aucune écriture.

Objectif (responsable réglementaire) : il dépose les décisions reçues, et c'est fini. Le plan dit
donc seulement :

1. quelle AMM (produit + pays) : si elle n'est pas identifiable sans ambiguïté, une seule
   question — « c'est quelle AMM ? » (`question`, seul cas bloquant) ;
2. où va chaque scan (origine ou renouvellement n), quels renouvellements obtenus créer, quels
   champs vides compléter (`renewals`, `documents`, `changes` sans confirmation) ;
3. les « points à vérifier plus tard » (`review_points`) : écart scan ≠ fiche sur une valeur déjà
   renseignée (la fiche est gardée), lecture douteuse, scan sans période… Jamais bloquants.
"""

import hashlib
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import PurePosixPath

from apps.amm.models import MarketingAuthorization, Renewal
from apps.catalog.models import Country, Product
from apps.documents.models import Document

from .extraction import load_extraction, paged_extraction
from .labels import FIELD_LABELS, fr_date, period_label, show
from .matching import (
    folder_product,
    match_authorizations,
    name_compatible,
    pick_table_row,
    resolve_renewal,
)
from .projection import build_projection
from .recognition import normalize, recognize_file, specialty_key

# Période des scans qu'on ne sait pas placer : rangés dans la fiche comme « autre document ».
UNPLACED = "unplaced"
# 3 : recueils de décisions, documents communs, pays sans code ISO (26/09/2026).
PREVIEW_VERSION = 3
# Décisions posées à la racine d'un dossier pays : jointes par le navigateur à chaque produit.
COMMON_FOLDER = "Documents communs"
# Seuls motifs de question qui laissent au siège l'option de créer l'AMM depuis le dossier.
CREATABLE = {"no_amm", "product_absent"}


def _consensus(rows, fields, points, label):
    values, proofs, confidences = {}, {}, {}
    for field in fields:
        evidence = [row for row in rows if row["official"] and row.get(field)]
        variants = {normalize(str(row[field])) for row in evidence}
        if len(variants) > 1:
            readings = ", ".join(sorted({show(field, row[field]) for row in evidence})[:3])
            name = FIELD_LABELS.get(
                f"original_{field}" if label == "AMM d'origine" else field,
                FIELD_LABELS.get(field, field),
            )
            _point(
                points,
                "contradiction",
                f"{label} : les décisions du dossier se contredisent ({name} : {readings}) ; "
                "valeur non reprise.",
            )
            continue
        if evidence:
            chosen = max(evidence, key=lambda row: (row["confidence"], row["file_id"]))
            values[field], proofs[field] = chosen[field], chosen["file_id"]
            confidences[field] = chosen["confidence"]
    return values, proofs, confidences


def _point(
    points,
    code,
    message,
    *,
    target=None,
    field="",
    recorded=None,
    scan=None,
    proof=None,
    confidence=0,
):
    points.append(
        {
            "code": code,
            "message": message,
            "target": target,
            "field": field,
            "recorded": recorded,
            "scan": scan,
            "proof_file_id": str(proof) if proof else None,
            "confidence": confidence,
        }
    )


def _change(target, field, old, new, proof, confidence, *, replaces=None):
    """Une différence scan / fiche. Champ vide : complété d'office ; sinon point à vérifier."""
    if hasattr(old, "isoformat"):
        old = old.isoformat()
    if old == new or (not old and not new):
        return None
    same_number = field in {"original_number", "number"} and old and new
    if same_number and number_key(old) == number_key(new):
        return None  # « E-2015-0418 » (fiche) et « E-2015- 418 » (scan) : le même numéro
    identity = f"{target}:{field}:{proof}:{new}"
    return {
        "id": hashlib.sha256(identity.encode()).hexdigest()[:24],
        "target": target,
        "field": field,
        "old": old,
        "new": new,
        "proof_file_id": proof,
        "confidence": confidence,
        # Jamais d'écrasement automatique d'une valeur renseignée : elle devient un point.
        "requires_confirmation": bool(old not in (None, "")) if replaces is None else replaces,
    }


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


def number_key(value: str) -> str:
    """Numéro comparable : sans espaces ni zéros de tête (« E-2015-0418 » = « E-2015- 418 »)."""
    tokens = re.findall(r"[a-z]+|\d+", normalize(str(value)))
    return "-".join(token.lstrip("0") or "0" if token.isdigit() else token for token in tokens)


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
                row = _section_row(
                    upload, line["section"], product, countries, products, root_name
                )
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


def build_preview(batch) -> dict:  # noqa: C901 — un seul parcours lisible, étape par étape
    files = list(batch.files.all().order_by("relative_path", "pk"))
    countries = list(Country.objects.all())
    products = list(Product.objects.prefetch_related("aliases").all())
    user = batch.created_by
    # AMM choisie par le réglementaire en réponse à la question « c'est quelle AMM ? ».
    forced = (
        MarketingAuthorization.objects.select_related("product", "country").get(pk=batch.amm_id)
        if batch.amm_id
        else None
    )
    questions, issues, points, warnings, rows = [], [], [], [], []
    for upload in files:
        if not upload.extraction:
            upload.extraction = load_extraction(upload)
            upload.save(update_fields=["extraction"])
        row = recognize_file(upload, countries, products, batch.root_name)
        if row["sections"]:
            # Recueil de décisions lu avant que les sauts de page soient gardés : relu, pour ne
            # ranger que les pages du produit.
            paged = paged_extraction(upload)
            if paged is not upload.extraction:
                upload.extraction = paged
                upload.save(update_fields=["extraction"])
                row = recognize_file(upload, countries, products, batch.root_name)
        rows.append(row)
        diagnostics = upload.extraction.get("warnings", []) + upload.extraction.get("errors", [])
        warnings.extend(f"{upload.relative_path} : {message}" for message in diagnostics)
        if upload.extraction.get("truncated") and not is_common(upload.relative_path):
            _point(
                points,
                "reading",
                f"{_name(upload.relative_path)} : document trop long, lu en partie ; vérifiez ses "
                "informations sur le scan.",
                proof=upload.pk,
            )
    if not files:
        questions.append(("empty", "Le dossier ne contient aucun document."))
    # Les documents communs du dossier pays (décisions groupées, recueils, AMM d'autres produits
    # posées à la racine) ne disent ni le pays ni le produit de ce dossier : ils sont mis de côté
    # jusqu'à ce que le produit soit connu, puis seule leur partie qui le concerne est gardée.
    pairs = list(zip(files, rows, strict=True))
    shared = [pair for pair in pairs if is_common(pair[0].relative_path)]
    if shared and len(shared) < len(pairs):
        own = [pair for pair in pairs if not is_common(pair[0].relative_path)]
        files, rows = [upload for upload, _ in own], [row for _, row in own]
    else:
        shared = []

    # --- Pays
    country_ids = {pk for row in rows for pk in row["country_ids"]}
    if forced:
        country = forced.country
        if country_ids and country_ids != {str(country.pk)}:
            _point(
                points,
                "identity",
                f"Les documents semblent venir d'un autre pays que l'AMM choisie ({country.name}).",
            )
    else:
        if len(country_ids) > 1:
            questions.append(("countries", "Le dossier mélange plusieurs pays : séparez-les."))
        country = next((item for item in countries if str(item.pk) in country_ids), None)
        if batch.country_id:
            if country_ids and country_ids != {str(batch.country_id)}:
                questions.append(
                    ("country_conflict", "Le pays choisi contredit le pays lu dans les documents.")
                )
            country = batch.country
        if not country:
            questions.append(("country", "Pays non reconnu dans les documents."))
    if country and (not user or not user.can_access_country(country)):
        questions.append(("scope", "Le pays du dossier est hors de votre périmètre."))

    # --- Produit
    if forced:
        product = forced.product
        product_name = product.name
    else:
        if country and not any(row["product_source"] == "text" for row in rows):
            _identify_by_folder(batch, files, rows, products, country, issues, warnings)
        product_ids = {pk for row in rows for pk in row["product_ids"]}
        if len(product_ids) > 1:
            issues.append(("products", "Le dossier mélange plusieurs produits ou présentations."))
        product = next((item for item in products if str(item.pk) in product_ids), None)
    ignored = []
    if product:
        files, rows, ignored = _focus_on_product(
            files + [upload for upload, _ in shared],
            rows + [row for _, row in shared],
            product,
            products,
            countries,
            country,
            batch.root_name,
            points,
        )
        _read_grouped_rows(rows, product, products, country, points)
    else:
        ignored = [
            {
                "file_id": str(upload.pk),
                "path": upload.relative_path,
                "reason": "produit du dossier non identifié",
            }
            for upload, _ in shared
        ]
    named = [row for row in rows if row["official"] and row["explicit_product_name"]]
    explicit_names = {normalize(row["explicit_product_name"]) for row in named}
    unknown_names = {
        normalize(row["explicit_product_name"]) for row in named if not row["product_ids"]
    }
    if not forced and len(unknown_names) > 1:
        issues.append(("products", "Les décisions désignent des produits différents."))
    if product and any(
        str(product.pk) not in row["product_ids"] or row["product_confidence"] < 65 for row in named
    ):
        issues.append(
            ("product_conflict", f"Une décision nomme un autre produit que « {product.name} ».")
        )
    creatable_product = False
    if not forced:
        product_name = (
            product.name if product else (named[0]["explicit_product_name"] if named else "")
        )
        if not product_name:
            questions.append(("product", "Produit non reconnu dans les documents."))
        if not product and product_name:
            near = any(
                SequenceMatcher(None, name, normalize(item.name)).ratio() >= 0.84
                for item in products
                for name in explicit_names
            )
            labeled = any(row["explicit_product_labeled"] for row in named)
            creatable_product = labeled and not near
            questions.append(
                (
                    "product_absent" if creatable_product else "product",
                    f"Produit « {product_name} » absent du catalogue"
                    + (" (nom proche d'un produit existant)." if near else "."),
                )
            )
    # Avec une AMM choisie à la main, un doute sur le produit n'est plus qu'un point.
    for code, message in _dedupe(issues):
        if forced:
            _point(points, "identity", message)
        else:
            questions.append((code, message))

    for row in rows:
        if row.get("number_variants"):
            _point(
                points,
                "number",
                f"{_name(row['path'])} : n° d'AMM mal lisible "
                f"({row['number'] or 'aucune lecture retenue'} ; autres lectures : "
                + ", ".join(row["number_variants"][:3])
                + ").",
                proof=row["file_id"],
            )

    # --- AMM
    amm, candidates = forced, []
    if not forced:
        candidates = match_authorizations(user, product, country, rows)
        if len(candidates) > 1:
            questions.append(("several_amms", "Plusieurs AMM correspondent au dossier."))
        elif candidates:
            amm = MarketingAuthorization.objects.select_related("product", "country").get(
                pk=candidates[0]["id"]
            )
        elif product and country and not questions:
            questions.append(
                (
                    "no_amm",
                    f"Aucune AMM {country.name} n'est enregistrée pour « {product.name} ».",
                )
            )
    official = [row for row in rows if row["official"]]
    if candidates:
        confidence = candidates[0]["confidence"]
    elif official and product_name and country:
        identity = [row for row in official if row["product_name"]]
        confidence = min(
            max((row["product_confidence"] for row in identity), default=0),
            max((row["country_confidence"] for row in rows), default=0)
            or (80 if batch.country_id or forced else 0),
            max(row["confidence"] for row in official),
        )
    else:
        confidence = 40 if product_name and country else 0
    if files and not official:
        _point(
            points,
            "reading",
            "Aucune décision officielle lisible dans le dossier : les scans sont rangés comme "
            "autres documents, vérifiez-les.",
        )

    # --- AMM d'origine
    original_rows = [row for row in rows if row["period"] == "original"]
    original_values, original_proofs_raw, original_confidences = _consensus(
        original_rows, ("number", "start_date", "end_date", "holder"), points, "AMM d'origine"
    )
    if (
        original_values.get("start_date")
        and original_values.get("end_date")
        and original_values["end_date"] < original_values["start_date"]
    ):
        _point(
            points,
            "reading",
            "AMM d'origine : la date de fin lue précède la date de début ; "
            "date de fin non reprise.",
            proof=original_proofs_raw.get("end_date"),
        )
        original_values.pop("end_date")
        original_proofs_raw.pop("end_date")
    original = {
        "original_number": original_values.get("number", ""),
        "original_start_date": original_values.get("start_date"),
        "original_end_date": original_values.get("end_date"),
        "holder": original_values.get("holder", ""),
    }
    field_map = {
        "number": "original_number",
        "start_date": "original_start_date",
        "end_date": "original_end_date",
        "holder": "holder",
    }
    original_proofs = {field_map[field]: proof for field, proof in original_proofs_raw.items()}
    changes = []
    if amm:
        for raw_field, field in field_map.items():
            if field in original_proofs:
                proposal = _change(
                    "amm",
                    field,
                    getattr(amm, field, ""),
                    original[field],
                    original_proofs[field],
                    min(confidence, original_confidences[raw_field]),
                )
                if proposal:
                    changes.append(proposal)

    # Un numéro d'AMM déjà porté par une autre AMM du même pays (ex. « 9601-BIS » lu sur le
    # 1000 mg alors que le 850 mg porte « 9601 BIS ») : à vérifier.
    proposed_number = normalize(original["original_number"] or "")
    if (
        country
        and proposed_number
        and (not amm or normalize(amm.original_number or "") != proposed_number)
    ):
        clashes = [
            other.product.name
            for other in MarketingAuthorization.objects.filter(country=country)
            .exclude(pk=amm.pk if amm else None)
            .select_related("product")
            if normalize(other.original_number or "") == proposed_number
        ]
        if clashes:
            _point(
                points,
                "number",
                f"Le n° d'AMM {original['original_number']} lu sur le scan est déjà attribué "
                "dans ce pays à : " + ", ".join(sorted(clashes)[:5]) + ".",
                proof=original_proofs.get("original_number"),
            )

    # --- Renouvellements
    grouped = defaultdict(list)
    for row in rows:
        if row["period"] != "original":
            grouped[row["period"]].append(row)
    renewals, renewal_targets, identities, unplaced = [], {}, {}, set()

    # La période la plus récente est résolue en premier : c'est elle qui peut conclure un
    # renouvellement encore ouvert dans l'application.
    def _group_date(item):
        dates = [
            row["start_date"] or row["decision_date"] or "" for row in item[1] if row["official"]
        ]
        return max(dates, default="")

    ordered = sorted(grouped.items(), key=lambda item: (_group_date(item), item[0]), reverse=True)
    for key, group in ordered:
        if key == "renewal-unresolved":
            unplaced.add(key)
            continue
        label = period_label(key)
        values, proofs, confidences = _consensus(
            group, ("number", "start_date", "decision_date", "end_date"), points, label
        )
        label = period_label(key, values)
        proof = next(iter(proofs.values()), None)
        if not values or not (values.get("start_date") or values.get("decision_date")):
            _point(
                points,
                "unplaced",
                f"{label} : aucune décision datée lisible ; ses documents sont rangés comme "
                "autres documents de la fiche.",
                proof=group[0]["file_id"],
            )
            unplaced.add(key)
            continue
        if (
            values.get("start_date")
            and values.get("end_date")
            and (values["end_date"] < values["start_date"])
        ):
            _point(
                points,
                "reading",
                f"{label} : la date de fin lue précède la date de début ; date de fin non reprise.",
                proof=proofs.get("end_date"),
            )
            values.pop("end_date")
        identity = (
            normalize(values.get("number", "")),
            values.get("start_date"),
            values.get("decision_date"),
        )
        if any(identity) and identity in identities:
            canonical = identities[identity]
            for row in group:
                row["period"] = canonical
            continue
        identities[identity] = key
        existing, ambiguous = resolve_renewal(
            amm, values, exclude=[pk for pk in renewal_targets.values() if pk]
        )
        conflict = None
        if ambiguous:
            conflict = "plusieurs renouvellements enregistrés dans la fiche correspondent"
        elif existing and str(existing.pk) in renewal_targets.values():
            conflict = "une autre période du dossier désigne déjà ce renouvellement"
        elif (
            not existing
            and amm
            and amm.original_start_date
            and values.get("start_date") == amm.original_start_date.isoformat()
        ):
            # La fiche date l'AMM d'origine du jour de ce renouvellement : on garde la fiche.
            conflict = (
                f"il commence le même jour que l'AMM d'origine enregistrée "
                f"({fr_date(amm.original_start_date)})"
            )
        elif not existing and not (values.get("number") and values.get("start_date")):
            conflict = "n° ou date de début illisible sur la décision : renouvellement non créé"
        if conflict:
            _point(
                points,
                "renewal_conflict",
                f"{label} : {conflict} ; la fiche est gardée et ses documents sont rangés comme "
                "autres documents.",
                proof=proof,
            )
            unplaced.add(key)
            continue
        renewal_targets[key] = str(existing.pk) if existing else None
        renewal_confidence = min(confidence, min(confidences.values(), default=0))
        renewals.append(
            {
                "key": key,
                "existing_id": str(existing.pk) if existing else None,
                "number": values.get("number", ""),
                "start_date": values.get("start_date"),
                "decision_date": values.get("decision_date"),
                "end_date": values.get("end_date"),
                "confidence": renewal_confidence,
                "proof_file_id": proof,
                "proofs": proofs,
            }
        )
        if existing:
            for field, new in values.items():
                proposal = _change(
                    key,
                    field,
                    getattr(existing, field),
                    new,
                    proofs[field],
                    min(confidence, confidences[field]),
                )
                if proposal:
                    changes.append(proposal)
            if (
                existing.workflow_status != "OBTENU"
                and values.get("number")
                and values.get("start_date")
            ):
                # La décision conclut un renouvellement en cours (déposé, en instruction…) : il
                # passe « obtenu ». Un renouvellement rejeté ou abandonné reste un point.
                proposal = _change(
                    key,
                    "workflow_status",
                    existing.workflow_status,
                    "OBTENU",
                    proofs.get("number") or proof,
                    renewal_confidence,
                    replaces=existing.workflow_status not in Renewal.OPEN_STATUSES,
                )
                if proposal:
                    changes.append(proposal)

    renewals.sort(key=lambda item: item["key"])
    labels = {item["key"]: period_label(item["key"], item) for item in renewals}

    # --- Documents
    documents, seen_hashes = [], {}
    for upload, row in zip(files, rows, strict=True):
        period, kind = row["period"], row["kind"]
        if period in unplaced:
            if period == "renewal-unresolved" and row["official"]:
                _point(
                    points,
                    "unplaced",
                    f"{_name(upload.relative_path)} : décision de renouvellement sans date ni "
                    "n° lisibles ; rangée comme autre document de la fiche.",
                    proof=upload.pk,
                )
            period = UNPLACED
            kind = "AUTRE" if kind == "AMM" else kind
        elif row["uncertain_period"] and row["official"]:
            where = labels.get(period, "renouvellement")
            _point(
                points,
                "unplaced",
                f"{_name(upload.relative_path)} : placé dans le dossier d'origine mais c'est une "
                f"décision de renouvellement ; rangé en « {where} ».",
                proof=upload.pk,
            )
        duplicate = None
        if amm:
            duplicate = Document.objects.filter(
                amm=amm, sha256=upload.sha256, archived_at__isnull=True
            ).first()
            if duplicate is None:
                # Imported images retain their source hash on the staged evidence file.
                duplicate = Document.objects.filter(
                    amm=amm,
                    archived_at__isnull=True,
                    dossier_sources__sha256=upload.sha256,
                ).first()
        if upload.sha256 in seen_hashes:
            earlier = seen_hashes[upload.sha256]
            if earlier != period:
                _point(
                    points,
                    "duplicate",
                    f"{_name(upload.relative_path)} : le même fichier figure dans deux périodes du "
                    "dossier ; il n'est rangé qu'une fois.",
                    proof=upload.pk,
                )
            else:
                warnings.append(
                    f"Fichier identique présent plusieurs fois : {upload.relative_path}."
                )
        else:
            seen_hashes[upload.sha256] = period
        if duplicate:
            target_renewal = (
                None if period in {"original", UNPLACED} else renewal_targets.get(period)
            )
            if (str(duplicate.renewal_id) if duplicate.renewal_id else None) != target_renewal:
                _point(
                    points,
                    "duplicate",
                    f"{_name(upload.relative_path)} : déjà rangé dans la fiche à une autre "
                    "période ; laissé à sa place.",
                    proof=upload.pk,
                )
        documents.append(
            {
                "file_id": str(upload.pk),
                "path": upload.relative_path,
                "kind": kind,
                "period": period,
                "document_date": row["document_date"],
                # Recueil de décisions : seules les pages du produit sont rangées.
                "pages": row.get("pages"),
                "duplicate_id": str(duplicate.pk) if duplicate else None,
                "extraction_source": upload.extraction.get("source", "unreadable"),
                "official": row["official"],
                "confidence": row["confidence"],
            }
        )

    # Écart scan ≠ fiche sur une valeur renseignée : la fiche est gardée, le point est noté.
    for change in changes:
        if not change["requires_confirmation"]:
            continue
        where = "AMM d'origine" if change["target"] == "amm" else labels[change["target"]]
        field = change["field"]
        _point(
            points,
            "value_mismatch",
            f"{FIELD_LABELS.get(field, field).capitalize()} ({where}) : la fiche indique "
            f"« {show(field, change['old'])} », le scan indique « {show(field, change['new'])} ».",
            target=change["target"],
            field=field,
            recorded=change["old"],
            scan=change["new"],
            proof=change["proof_file_id"],
            confidence=change["confidence"],
        )

    questions = _dedupe(questions)
    codes = {code for code, _ in questions}
    can_create = bool(
        questions
        and codes <= CREATABLE
        and not forced
        and amm is None
        and country
        and (product or creatable_product)
        and original["original_number"]
        and original["original_start_date"]
    )
    reasons = [message for _, message in questions]
    return {
        # Version des règles de lecture : un aperçu plus ancien est relu automatiquement
        # (`recover_pending_work`), et rangé si l'AMM est désormais identifiée.
        "version": PREVIEW_VERSION,
        # Fiabilité de la lecture : information de détail, n'entre plus dans aucune décision.
        "confidence": confidence,
        "level": "HIGH" if confidence >= 90 else "MEDIUM" if confidence >= 65 else "LOW",
        "can_apply": not questions,
        "blockers": reasons,
        "question": {"reasons": reasons, "codes": sorted(codes), "can_create": can_create}
        if questions
        else None,
        "review_points": _dedupe(points),
        "warnings": sorted(set(warnings)),
        "forced": bool(forced),
        "amm": {
            "id": str(amm.pk) if amm else None,
            "product_id": str(product.pk) if product else None,
            "product_name": product_name,
            "country_id": str(country.pk) if country else None,
            "country_iso2": country.iso2 if country else "",
            "holder": original["holder"],
        },
        "original": original,
        "original_proofs": original_proofs,
        "candidates": candidates,
        "documents": documents,
        # Documents communs du dossier pays sans rapport avec ce produit : ni lus ni rangés.
        "ignored": ignored,
        "renewals": renewals,
        "changes": changes,
        # Indicatif, hors jeton d'aperçu (voir `preview_token`) : dépend de la date du jour.
        "projection": build_projection(
            amm=amm,
            product=product,
            country=country,
            original=original,
            renewals=renewals,
            changes=changes,
            documents=documents,
        ),
    }
