"""Plan de rangement d'un dossier, sans aucune écriture.

Objectif (responsable réglementaire) : il dépose les décisions reçues, et c'est fini. Le plan dit
donc seulement :

1. quelle AMM (produit + pays) : si elle n'est pas identifiable sans ambiguïté, une seule
   question — « c'est quelle AMM ? » (`question`, seul cas bloquant) ;
2. où va chaque scan (origine ou renouvellement n), quels renouvellements obtenus créer, quels
   champs vides compléter (`renewals`, `documents`, `changes` sans confirmation) ;
3. les « points à vérifier plus tard » (`review_points`) : écart scan ≠ fiche sur une valeur déjà
   renseignée (la fiche est gardée), lecture douteuse, scan sans période… Jamais bloquants."""

from collections import defaultdict
from difflib import SequenceMatcher

from apps.amm.models import MarketingAuthorization, Renewal
from apps.catalog.models import Country, Product
from apps.documents.models import Document

from .evidence import _change, _consensus, _correct_from_scans, _decision, _point
from .extraction import load_extraction, paged_extraction
from .identification import (
    _autonomous,
    _dedupe,
    _focus_on_product,
    _folder_label,
    _identify_by_folder,
    _majority,
    _name,
    _path_country,
    _read_grouped_rows,
    is_common,
)
from .labels import FIELD_LABELS, fr_date, period_label, show
from .matching import (
    _strengths,
    _strengths_fit,
    match_authorizations,
    resolve_renewal,
    same_product_in_country,
)
from .projection import build_projection
from .recognition import normalize, recognize_file

# Période des scans qu'on ne sait pas placer : rangés dans la fiche comme « autre document ».
UNPLACED = "unplaced"
# 3 : recueils de décisions, documents communs, pays sans code ISO (26/09/2026).
# 4 : AMM absente créée d'office quand la décision d'origine est lisible.
# 5 : classement autonome (doutes tranchés seuls, la décision officielle corrige la fiche).
# 6 : dates relues (tampons sénégalais, n° daté, AMM d'origine citée par un renouvellement).
PREVIEW_VERSION = 6
# Seuls motifs de question qui laissent au siège l'option de créer l'AMM depuis le dossier.
CREATABLE = {"no_amm", "product_absent"}
UNKNOWN_PRODUCT = "produit du dossier non identifié"


def build_preview(batch) -> dict:  # noqa: C901 — un seul parcours lisible, étape par étape
    autonomous = _autonomous()
    decisions = []
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
    elif autonomous:
        # Le dossier pays déposé (« MALI - … ») fait foi ; sinon le pays le plus cité. Une pièce
        # d'un autre pays devient une annexe (plus bas). Décision identique à chaque relecture.
        folder_country = _path_country(batch, countries)
        chosen = folder_country or next(
            (item for item in countries if str(item.pk) in country_ids), None
        )
        if not folder_country and len(country_ids) > 1:
            majority = _majority(pk for row in rows for pk in row["country_ids"])
            chosen = next(item for item in countries if str(item.pk) == majority)
            _decision(
                decisions,
                f"Pièces de plusieurs pays : rangé pour {chosen.name}, le pays le plus cité.",
            )
        country = chosen
        if batch.country_id and batch.country != chosen:
            country = batch.country
            _decision(decisions, f"Pays choisi au dépôt retenu : {country.name}.")
    else:
        country = next((item for item in countries if str(item.pk) in country_ids), None)
        if len(country_ids) > 1:
            questions.append(("countries", "Le dossier mélange plusieurs pays : séparez-les."))
        if batch.country_id:
            if country_ids and country_ids != {str(batch.country_id)}:
                questions.append(
                    ("country_conflict", "Le pays choisi contredit le pays lu dans les documents.")
                )
            country = batch.country
    if not forced and not country:
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
        # Plusieurs produits cités : celui du nom du dossier, sinon le plus cité par les décisions.
        chosen = next(
            (pk for row in rows if row["product_source"] == "folder" for pk in row["product_ids"]),
            None,
        ) or _majority(
            pk
            for row in sorted(rows, key=lambda item: not item["official"])
            for pk in row["product_ids"]
        )
        product = next((item for item in products if str(item.pk) == chosen), None)
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
                "reason": UNKNOWN_PRODUCT,
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
        folder_name = _folder_label(batch, country) if autonomous and not product else ""
        if not product_name and folder_name:
            # Aucune décision ne nomme le produit : le nom du dossier le désigne.
            product_name = folder_name
            explicit_names = {normalize(folder_name)}
        if not product_name:
            questions.append(("product", "Produit non reconnu dans les documents."))
        if not product and product_name:
            scored = sorted(
                (
                    (SequenceMatcher(None, name, normalize(item.name)).ratio(), item)
                    for item in products
                    for name in explicit_names
                ),
                key=lambda pair: pair[0],
                reverse=True,
            )
            near = bool(scored) and scored[0][0] >= 0.84
            labeled = any(row["explicit_product_labeled"] for row in named)
            known = None
            if autonomous and country:
                # Produit déjà suivi dans ce pays sous un autre libellé (« KETOPROFENE-GH CPR
                # B30 » = « KETOPROFEN GH 100MG CPR B/30 ») : pas de fiche en double.
                in_country = set(
                    MarketingAuthorization.objects.filter(country=country).values_list(
                        "product_id", flat=True
                    )
                )
                known = same_product_in_country(
                    [row["explicit_product_name"] for row in named],
                    _folder_label(batch, country),
                    products,
                    in_country,
                )
            if autonomous and near and not known:
                # Nom proche mais dosage ou volume différent (« F45ML » / « F50ML ») : une autre
                # présentation, jamais rattachée d'office.
                near = _strengths_fit(
                    _strengths(product_name)[0], _strengths(scored[0][1].name)[0]
                ) and _strengths_fit(_strengths(scored[0][1].name)[0], _strengths(product_name)[0])
            if autonomous and (known or near):
                # Nom proche d'un produit du catalogue (coquille, OCR) : rattaché à ce produit.
                product = known or scored[0][1]
                _decision(
                    decisions,
                    f"« {product_name} » rattaché au produit « {product.name} »"
                    + (", déjà suivi dans ce pays." if known else " (nom proche)."),
                )
                product_name = product.name
                files, rows, extra = _focus_on_product(
                    files + [upload for upload, _ in shared],
                    rows + [row for _, row in shared],
                    product,
                    products,
                    countries,
                    country,
                    batch.root_name,
                    points,
                )
                ignored = [item for item in ignored if item.get("reason") != UNKNOWN_PRODUCT]
                ignored += extra
                _read_grouped_rows(rows, product, products, country, points)
            else:
                creatable_product = (labeled or autonomous) and not near
                questions.append(
                    (
                        "product_absent" if creatable_product else "product",
                        f"Produit « {product_name} » absent du catalogue"
                        + (" (nom proche d'un produit existant)." if near else "."),
                    )
                )
    # Avec une AMM choisie à la main, ou en classement autonome, un doute sur le produit n'est
    # plus qu'un point : le produit retenu est celui du dossier.
    for code, message in _dedupe(issues):
        if forced or autonomous:
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

    if autonomous and not forced and product and country:
        in_country = set(
            MarketingAuthorization.objects.filter(country=country).values_list(
                "product_id", flat=True
            )
        )
        if product.pk not in in_country:
            # Produit du catalogue sans AMM dans ce pays (fiche créée ailleurs sous ce libellé) :
            # la présentation déjà suivie ici sous un autre libellé est la bonne fiche.
            known = same_product_in_country(
                [product.name, *(row["explicit_product_name"] for row in named)],
                _folder_label(batch, country),
                products,
                in_country,
            )
            if known:
                _decision(
                    decisions,
                    f"« {product.name} » rattaché au produit « {known.name} », déjà suivi dans "
                    "ce pays.",
                )
                for row in rows:
                    if row["product_ids"] == [str(product.pk)]:
                        row["product_ids"] = [str(known.pk)]
                        row["product_name"] = known.name
                product, product_name = known, known.name

    if autonomous and not forced:
        # Une décision d'un autre produit ou d'un autre pays glissée dans ce dossier n'est pas une
        # preuve pour lui : rangée comme pièce annexe, jamais lue comme sa décision.
        for row in rows:
            other_product = (
                product and row["product_ids"] and str(product.pk) not in row["product_ids"]
            )
            other_country = (
                country and row["country_ids"] and str(country.pk) not in row["country_ids"]
            )
            if row["official"] and (other_product or other_country):
                row["official"] = False
                row["kind"] = "AUTRE"
                _decision(
                    decisions,
                    f"{_name(row['path'])} concerne un autre "
                    f"{'produit' if other_product else 'pays'} : rangé comme pièce annexe.",
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
            "unreadable",
            "Aucune décision officielle lisible dans le dossier : les scans sont rangés comme "
            "autres documents, vérifiez-les.",
        )

    # --- AMM d'origine
    original_rows = [row for row in rows if row["period"] == "original"]
    original_values, original_proofs_raw, original_confidences = _consensus(
        original_rows, ("number", "start_date", "end_date", "holder"), points, "AMM d'origine"
    )
    # Sans décision d'origine lisible, un renouvellement qui la cite (« l'AMM n° 5735 du
    # 22/12/2010 est renouvelée ») donne son n° et sa date, si toutes les citations concordent.
    citations = [row for row in rows if row["official"] and row.get("cited_original")]
    for field in ("number", "start_date"):
        values = {normalize(str(row["cited_original"].get(field) or "")) for row in citations}
        values.discard("")
        if field in original_values or len(values) != 1:
            continue
        row = max(citations, key=lambda item: item["confidence"])
        if row["cited_original"].get(field):
            original_values[field] = row["cited_original"][field]
            original_proofs_raw[field] = row["file_id"]
            original_confidences[field] = row["confidence"]
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

    if autonomous:
        _correct_from_scans(changes, rows, amm, renewals, decisions)
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
    readable = bool(original["original_number"] and original["original_start_date"])
    can_create = bool(
        questions
        and codes <= CREATABLE
        and not forced
        and amm is None
        and country
        and (product or creatable_product)
        and (readable or autonomous)
    )
    if can_create and not readable:
        # Classement autonome : la fiche est créée quand même, à compléter depuis le scan.
        _point(
            points,
            "incomplete",
            "Fiche créée sans n° d'AMM ou date de début lisibles : complétez-les depuis le scan.",
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
        # Doutes tranchés seuls par l'application (classement autonome), pour le récapitulatif.
        "decisions": decisions,
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
