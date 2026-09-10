"""Produce a deterministic review plan without modifying regulatory records."""

import hashlib
from collections import defaultdict
from difflib import SequenceMatcher

from apps.amm.models import MarketingAuthorization
from apps.catalog.models import Country, Product
from apps.documents.models import Document

from .extraction import extract_file
from .matching import match_authorizations, resolve_renewal
from .recognition import normalize, recognize_file


def _consensus(rows, fields, blockers, label):
    values, proofs, confidences = {}, {}, {}
    for field in fields:
        evidence = [row for row in rows if row["official"] and row.get(field)]
        variants = {normalize(str(row[field])) for row in evidence}
        if len(variants) > 1:
            blockers.append(f"Preuves officielles contradictoires pour {label} : {field}.")
            continue
        if evidence:
            chosen = max(evidence, key=lambda row: (row["confidence"], row["file_id"]))
            values[field], proofs[field] = chosen[field], chosen["file_id"]
            confidences[field] = chosen["confidence"]
    return values, proofs, confidences


def _change(target, field, old, new, proof, confidence):
    if hasattr(old, "isoformat"):
        old = old.isoformat()
    if old == new or (not old and not new):
        return None
    identity = f"{target}:{field}:{proof}:{new}"
    return {
        "id": hashlib.sha256(identity.encode()).hexdigest()[:24],
        "target": target,
        "field": field,
        "old": old,
        "new": new,
        "proof_file_id": proof,
        "confidence": confidence,
        "requires_confirmation": bool(old not in (None, "") or confidence < 90),
    }


def build_preview(batch) -> dict:
    files = list(batch.files.all().order_by("relative_path", "pk"))
    countries = list(Country.objects.all())
    products = list(Product.objects.prefetch_related("aliases").all())
    blockers, warnings, rows = [], [], []
    for upload in files:
        if not upload.extraction:
            upload.extraction = extract_file(upload)
            upload.save(update_fields=["extraction"])
        row = recognize_file(upload, countries, products, batch.root_name)
        rows.append(row)
        diagnostics = upload.extraction.get("warnings", []) + upload.extraction.get("errors", [])
        warnings.extend(f"{upload.relative_path} : {message}" for message in diagnostics)
        if upload.extraction.get("truncated"):
            blockers.append(f"Extraction incomplète : {upload.relative_path}.")
        if row["uncertain_period"]:
            blockers.append(f"Période de renouvellement incertaine : {upload.relative_path}.")
    if not files:
        blockers.append("Le dossier ne contient aucun document.")

    product_ids = {pk for row in rows for pk in row["product_ids"]}
    country_ids = {pk for row in rows for pk in row["country_ids"]}
    if len(product_ids) > 1:
        blockers.append("Le dossier contient plusieurs produits ou présentations : séparez-les.")
    if len(country_ids) > 1:
        blockers.append("Le dossier contient plusieurs pays : séparez-les.")
    country = next((item for item in countries if str(item.pk) in country_ids), None)
    if batch.country_id:
        if country_ids and country_ids != {str(batch.country_id)}:
            blockers.append("Le pays sélectionné contredit le pays reconnu dans le dossier.")
        country = batch.country
    if not country:
        blockers.append("Pays non reconnu. Sélectionnez le pays avant de relancer l'analyse.")
    elif not batch.created_by or not batch.created_by.can_access_country(country):
        blockers.append("Le pays reconnu est hors de votre périmètre.")

    product = next((item for item in products if str(item.pk) in product_ids), None)
    named = [row for row in rows if row["official"] and row["explicit_product_name"]]
    explicit_names = {normalize(row["explicit_product_name"]) for row in named}
    unknown_names = {
        normalize(row["explicit_product_name"]) for row in named if not row["product_ids"]
    }
    if len(unknown_names) > 1:
        blockers.append("Les décisions officielles désignent des produits différents.")
    if product and any(
        str(product.pk) not in row["product_ids"] or row["product_confidence"] < 65 for row in named
    ):
        blockers.append("Le produit nommé dans une décision contredit le produit du dossier.")
    product_name = product.name if product else (named[0]["explicit_product_name"] if named else "")
    if not product_name:
        blockers.append("Produit non reconnu : une dénomination explicite est nécessaire.")
    if not product and product_name:
        near_products = [
            item
            for item in products
            if any(
                SequenceMatcher(None, name, normalize(item.name)).ratio() >= 0.84
                for name in explicit_names
            )
        ]
        if near_products:
            blockers.append(
                "Nom proche d'un produit existant : normalisez le catalogue avant import."
            )
        if not batch.created_by or not batch.created_by.is_global:
            blockers.append("La création d'un produit nécessite un utilisateur du siège.")

    candidates = match_authorizations(batch.created_by, product, country, rows)
    amm = None
    if len(candidates) > 1:
        blockers.append("Plusieurs AMM correspondent au dossier : rapprochement ambigu.")
    elif candidates:
        amm = MarketingAuthorization.objects.select_related("product", "country").get(
            pk=candidates[0]["id"]
        )
    official = [row for row in rows if row["official"]]
    if candidates:
        confidence = candidates[0]["confidence"]
    elif official and product_name and country:
        identity = [row for row in official if row["product_name"]]
        confidence = min(
            max((row["product_confidence"] for row in identity), default=0),
            max((row["country_confidence"] for row in rows), default=0)
            or (80 if batch.country_id else 0),
            max(row["confidence"] for row in official),
        )
    else:
        confidence = 40 if product_name and country else 0
    if not official:
        blockers.append("Aucune décision officielle lisible : preuves insuffisantes pour l'import.")

    original_rows = [row for row in rows if row["period"] == "original"]
    original_values, original_proofs_raw, original_confidences = _consensus(
        original_rows, ("number", "start_date", "end_date", "holder"), blockers, "l'AMM d'origine"
    )
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
    if not amm and (not original["original_number"] or not original["original_start_date"]):
        blockers.append(
            "Créer une AMM exige sa décision d'origine avec numéro et date de délivrance."
        )
    if (
        original["original_start_date"]
        and original["original_end_date"]
        and (original["original_end_date"] < original["original_start_date"])
    ):
        blockers.append("La date de fin d'origine précède sa date de début.")
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

    grouped = defaultdict(list)
    for row in rows:
        if row["period"] != "original":
            grouped[row["period"]].append(row)
    renewals, renewal_targets, identities = [], {}, {}
    # La période la plus récente est résolue en premier : c'est elle qui peut conclure un
    # renouvellement encore ouvert dans l'application.
    def _group_date(item):
        dates = [
            row["start_date"] or row["decision_date"] or "" for row in item[1] if row["official"]
        ]
        return max(dates, default="")

    ordered = sorted(grouped.items(), key=lambda item: (_group_date(item), item[0]), reverse=True)
    for key, group in ordered:
        values, proofs, confidences = _consensus(
            group, ("number", "start_date", "decision_date", "end_date"), blockers, key
        )
        if not values or not (values.get("start_date") or values.get("decision_date")):
            blockers.append(f"{key} : une décision officielle datée est nécessaire.")
        if (
            values.get("start_date")
            and values.get("end_date")
            and (values["end_date"] < values["start_date"])
        ):
            blockers.append(f"{key} : la date de fin précède la date de début.")
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
        if ambiguous:
            blockers.append(f"{key} : plusieurs renouvellements existants correspondent.")
        if existing and str(existing.pk) in renewal_targets.values():
            blockers.append(
                "Plusieurs périodes du dossier désignent le même renouvellement existant."
            )
        renewal_targets[key] = str(existing.pk) if existing else None
        proof = next(iter(proofs.values()), "")
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
                proposal = _change(
                    key,
                    "workflow_status",
                    existing.workflow_status,
                    "OBTENU",
                    proofs.get("number") or proof,
                    renewal_confidence,
                )
                if proposal:
                    changes.append(proposal)

    renewals.sort(key=lambda item: item["key"])

    documents, seen_hashes = [], {}
    for upload, row in zip(files, rows, strict=True):
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
            if earlier["period"] != row["period"]:
                blockers.append(
                    "Un même fichier apparaît dans des périodes réglementaires différentes."
                )
            else:
                warnings.append(
                    f"Fichier identique présent plusieurs fois : {upload.relative_path}."
                )
        else:
            seen_hashes[upload.sha256] = row
        if duplicate:
            target_renewal = (
                None if row["period"] == "original" else renewal_targets.get(row["period"])
            )
            if (str(duplicate.renewal_id) if duplicate.renewal_id else None) != target_renewal or (
                row["period"] != "original" and not target_renewal
            ):
                blockers.append(
                    f"{upload.relative_path} : fichier déjà rattaché à une autre période."
                )
        documents.append(
            {
                "file_id": str(upload.pk),
                "path": upload.relative_path,
                "kind": row["kind"],
                "period": row["period"],
                "document_date": row["document_date"],
                "duplicate_id": str(duplicate.pk) if duplicate else None,
                "extraction_source": upload.extraction.get("source", "unreadable"),
                "official": row["official"],
                "confidence": row["confidence"],
            }
        )
    if confidence < 65:
        blockers.append("Confiance faible : aucune modification automatique n'est autorisée.")
    return {
        "version": 1,
        "confidence": confidence,
        "level": "HIGH" if confidence >= 90 else "MEDIUM" if confidence >= 65 else "LOW",
        "can_apply": not blockers and confidence >= 65,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
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
        "renewals": renewals,
        "changes": changes,
    }
