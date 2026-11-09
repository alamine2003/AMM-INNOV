"""Corriger la chronologie d'une page : périodes (origine, renouvellements) et pièces scannées.

Ce que la lecture automatique d'un scan a faussé se reprend ici, à la main, depuis le classeur :
- une période (AMM d'origine ou renouvellement) : n° et dates ;
- un passage qui n'existe pas (renouvellement en double, saisi à tort, dépôt jamais fait), le
  plus récent ou un plus ancien : il est supprimé, ses pièces rejoignent la période choisie (jamais
  archivées) ;
- une interruption de validité qui n'est pas un renouvellement manquant : elle est ignorée ;
- la page elle-même : son titre (nom de la présentation, partout), ou la page supprimée (ses
  pièces reprises par une autre fiche) ;
- une pièce : sa date, son type, la période à laquelle elle appartient ; ou elle est retirée
  (archivée, l'historique la garde) ;
- une pièce manquante : ajoutée directement sur la bonne période, avec la date saisie — sans
  repasser par la lecture automatique.

Chaque écriture garde son auteur (historique) et l'AMM est recalculée (statut, échéance, état
du dossier) une fois la transaction validée.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.permissions import ensure_can, ensure_country_in_scope
from apps.accounts.roles import Action
from apps.amm.models import MarketingAuthorization, Renewal
from apps.documents.models import Document
from apps.documents.services.ingest import ingest_document
from apps.imports.dossier.application import _reconcile_after_commit, _save_with_actor

from .layout import Binder, ensure_in_binder

REASON = "Chronologie corrigée depuis le classeur"
# Retirer une pièce, c'est la supprimer de la page : même règle que la suppression de document
# (CEO et siège depuis la 1.0.7).


def _page(binder: Binder, amm_id, user) -> MarketingAuthorization:
    amm = (
        MarketingAuthorization.objects.select_for_update(of=("self",))
        .select_related("country", "product__range")
        .get(pk=amm_id)
    )
    ensure_country_in_scope(user, amm.country)
    ensure_in_binder(binder, amm)
    return amm


def _renewal(amm, renewal_id, lock=True) -> Renewal:
    queryset = Renewal.objects.select_for_update() if lock else Renewal.objects
    try:
        renewal = queryset.filter(pk=renewal_id, amm=amm).first()
    except (ValueError, ValidationError):  # identifiant mal formé
        renewal = None
    if renewal is None:
        raise ValidationError("Cette période n'appartient pas à cette AMM.")
    return renewal


def _document(amm, document_id) -> Document:
    document = Document.objects.filter(
        pk=document_id, amm=amm, is_current=True, archived_at__isnull=True
    ).first()
    if document is None:
        raise ValidationError("Pièce introuvable sur cette page (déjà retirée ?).")
    return document


def _target_period(amm, period, lock=True):
    """« origin » ou l'identifiant d'un renouvellement de cette AMM."""
    if period in (None, "", "origin"):
        return None
    return _renewal(amm, period, lock=lock)


def _reconcile(amm) -> None:
    transaction.on_commit(lambda: _reconcile_after_commit(amm.pk))


def edit_period(binder: Binder, amm_id, *, period: str, values: dict, user):
    """Corrige le n° et les dates d'une période. Seuls les champs envoyés changent.

    Une date de fin envoyée est tenue pour saisie à la main ; l'effacer la fait recalculer
    à partir de la date de début et de la durée de validité du pays.
    """
    with transaction.atomic():
        amm = _page(binder, amm_id, user)
        target = _target_period(amm, period)
        prefix = "original_" if target is None else ""
        obj = amm if target is None else target
        before_start = getattr(obj, f"{prefix}start_date")
        before_end = getattr(obj, f"{prefix}end_date")
        changed = False
        for field in ("number", "start_date", "end_date"):
            if field not in values:
                continue
            value = values[field]
            if field == "number":
                value = (value or "").strip()
            attr = f"{prefix}{field}"
            if getattr(obj, attr) == value:
                continue
            setattr(obj, attr, value)
            if field == "end_date":
                setattr(obj, f"{attr}_manual", value is not None)
            changed = True
        if not changed:
            return amm
        if (
            "start_date" in values
            and getattr(obj, f"{prefix}start_date") != before_start
            and ("end_date" not in values or values["end_date"] == before_end)
        ):
            # Début corrigé, fin non retouchée : la fin suit (début + durée du pays).
            setattr(obj, f"{prefix}end_date_manual", False)
        start, end = getattr(obj, f"{prefix}start_date"), getattr(obj, f"{prefix}end_date")
        if start and end and end < start:
            raise ValidationError("La date de fin précéderait la date de début.")
        _save_with_actor(obj, user, REASON)
        if target is not None:
            # Un renouvellement redaté reprend sa place ; l'échéance de l'AMM suit la décision
            # en vigueur.
            from apps.amm.services.sequence import resequence

            resequence(amm)
            _save_with_actor(amm, user, REASON)
        _reconcile(amm)
    return amm


def _remove_renewal(amm, renewal, destination, user) -> int:
    """Supprime un renouvellement (n'importe lequel) ; ses pièces rejoignent `destination`.

    Aucune pièce n'est archivée ni supprimée : le scan reste, seul le passage disparaît.
    """
    from apps.amm.services.sequence import resequence
    from apps.imports.models import DossierChange

    if hasattr(renewal, "deposit"):
        raise ValidationError(
            "Ce renouvellement a son dossier de dépôt (menu « Dépôts ») : supprimez ou clôturez "
            "ce dossier d'abord."
        )
    moved = 0
    for document in Document.objects.filter(renewal=renewal):
        document.renewal = destination
        document._history_user = user
        document._change_reason = REASON
        document._skip_signals = True
        document.save(update_fields=["renewal"])
        moved += 1
    # Le journal des imports de dossier garde la modification, sans le renouvellement supprimé.
    DossierChange.objects.filter(renewal=renewal).update(renewal=None)
    renewal._history_user = user
    renewal._change_reason = REASON
    renewal._skip_signals = True
    renewal.delete()
    resequence(amm)
    _save_with_actor(amm, user, REASON)
    return moved


def delete_period(binder: Binder, amm_id, renewal_id, *, move_to: str | None, user):
    """Supprime un passage qui n'existe pas (renouvellement saisi à tort, en double, dépôt
    jamais fait…), le plus récent ou un plus ancien.

    Les pièces qu'il portait ne sont jamais perdues : elles sont rangées sur `move_to` (l'AMM
    d'origine par défaut). L'ordre des renouvellements, l'échéance et le statut sont recalculés.
    """
    ensure_can(user, Action.BINDER_REMOVE_PASSAGE)
    with transaction.atomic():
        amm = _page(binder, amm_id, user)
        renewal = _renewal(amm, renewal_id)
        destination = _target_period(amm, move_to or "origin")
        if destination is not None and destination.pk == renewal.pk:
            raise ValidationError("Choisissez une autre période pour ranger les pièces.")
        _remove_renewal(amm, renewal, destination, user)
        _reconcile(amm)
    return amm


def ignore_gap(binder: Binder, amm_id, *, start_date, end_date, ignored: bool, user):
    """Une interruption de validité n'est pas un renouvellement manquant : on l'ignore (ou on
    revient dessus). Elle reste visible dans la chronologie, sans compter comme un manque."""
    from .models import BinderIgnoredGap

    with transaction.atomic():
        amm = _page(binder, amm_id, user)
        if ignored:
            BinderIgnoredGap.objects.get_or_create(
                amm=amm, start_date=start_date, end_date=end_date, defaults={"ignored_by": user}
            )
        else:
            BinderIgnoredGap.objects.filter(
                amm=amm, start_date=start_date, end_date=end_date
            ).delete()
    return amm


def rename_page(binder: Binder, amm_id, *, name: str, user):
    """Change le titre de la page : le nom de la présentation, partout dans AMM GH.

    Le produit est renommé pour tous les pays qui le suivent ; l'ancien nom devient un alias, si
    bien que les imports et la synchronisation reconnaissent toujours la présentation.
    """
    from apps.catalog.models import Product, ProductAlias
    from apps.catalog.normalize import normalize_product_name

    ensure_can(user, Action.BINDER_RENAME_PAGE)
    name = normalize_product_name(name)
    if not name:
        raise ValidationError("Le titre ne peut pas être vide.")
    with transaction.atomic():
        amm = _page(binder, amm_id, user)
        product = Product.objects.select_for_update().get(pk=amm.product_id)
        if name == product.name:
            return amm
        other = Product.objects.filter(name=name).exclude(pk=product.pk).first()
        if other is not None:
            raise ValidationError(
                f"« {name} » est déjà le nom d'une autre présentation : fusionnez les deux "
                "produits dans le catalogue (menu Produits)."
            )
        old = product.name
        product.name = name
        product._history_user = user
        product._change_reason = f"{REASON} : titre de la page"
        product.save()
        if not ProductAlias.objects.filter(raw_name=old).exists():
            ProductAlias.objects.create(product=product, raw_name=old)
        _reconcile(amm)
    return amm


def _period_for(target, when):
    """La période de la fiche `target` qui correspond à la date d'une pièce (sinon l'origine)."""
    for renewal in target.renewals.all():
        if when and when in (renewal.start_date, renewal.filing_date):
            return renewal
    return None


def delete_page(binder: Binder, amm_id, *, move_to_amm=None, user):
    """Supprime la page : la fiche AMM disparaît de toute l'application (classeurs, fiches,
    alertes, rappels, tableaux de bord).

    Ses pièces (scans, récépissés…) ne sont jamais perdues : elles sont rangées sur la fiche
    `move_to_amm` (même pays), à la période de même date. Une page sans pièce se supprime
    directement. Les imports ne recréent plus cette page (`BinderDeletedPage`).
    """
    from apps.catalog.models import Country
    from apps.imports.models import DossierChange, DossierImport, GhplSyncedFile

    from .models import BinderDeletedPage

    ensure_can(user, Action.BINDER_DELETE_PAGE)
    with transaction.atomic():
        amm = _page(binder, amm_id, user)
        documents = list(Document.objects.filter(amm=amm))
        imports = DossierImport.objects.filter(amm=amm)
        changes = DossierChange.objects.filter(amm=amm)
        if Renewal.objects.filter(amm=amm, deposit__isnull=False).exists():
            raise ValidationError(
                "Cette page a un dossier de dépôt (menu « Dépôts ») : supprimez ou clôturez-le "
                "d'abord."
            )
        target = None
        if move_to_amm:
            target = (
                MarketingAuthorization.objects.select_for_update(of=("self",))
                .select_related("country", "product")
                .filter(pk=move_to_amm)
                .first()
            )
            if target is None or target.pk == amm.pk or target.country_id != amm.country_id:
                raise ValidationError("Choisissez une autre fiche du même pays.")
        if target is None and (documents or imports.exists() or changes.exists()):
            count = len(documents)
            raise ValidationError(
                f"Cette page a {count} pièce{'s' if count > 1 else ''} : choisissez la fiche qui "
                "les reprend (aucun scan n'est supprimé)."
            )
        now = timezone.now()
        for document in documents:
            duplicate = (
                document.archived_at is None
                and Document.objects.filter(
                    amm=target, sha256=document.sha256, archived_at__isnull=True
                ).exists()
            )
            if duplicate:  # le même fichier est déjà sur la fiche : il y reste, celui-ci archivé
                document.is_current = False
                document.archived_at = now
            document.amm = target
            document.renewal = _period_for(target, document.document_date)
            document._history_user = user
            document._change_reason = f"{REASON} : page supprimée, pièce reprise"
            document._skip_signals = True
            document.save()
        if target is not None:
            imports.update(amm=target)
            changes.update(amm=target)
        DossierChange.objects.filter(renewal__amm=amm).update(renewal=None)
        GhplSyncedFile.objects.filter(amm=amm).update(amm=target)
        country = Country.objects.get(pk=amm.country_id)
        BinderDeletedPage.objects.create(
            country=country,
            product_name=amm.product.name,
            product_key=amm.product.key,
            moved_to=target.product.name if target else "",
            deleted_by=user,
        )
        amm._history_user = user
        amm._change_reason = f"{REASON} : page supprimée"
        amm.delete()
        if target is not None:
            _save_with_actor(target, user, REASON)
            _reconcile(target)
    return target


def edit_document(binder: Binder, amm_id, document_id, *, values: dict, user):
    """Corrige la date ou le type d'une pièce, ou la range sur une autre période."""
    with transaction.atomic():
        amm = _page(binder, amm_id, user)
        document = _document(amm, document_id)
        fields = []
        if "period" in values:
            destination = _target_period(amm, values["period"])
            if document.renewal_id != (destination.pk if destination else None):
                document.renewal = destination
                fields.append("renewal")
        for field in ("document_date", "kind"):
            if field in values and values[field] != getattr(document, field):
                setattr(document, field, values[field])
                fields.append(field)
        if fields:
            document._history_user = user
            document._change_reason = REASON
            document._skip_signals = True
            document.save(update_fields=fields)
            _reconcile(amm)
    return amm


def remove_document(binder: Binder, amm_id, document_id, *, user):
    """Retire une pièce de la page : elle est archivée (l'historique la garde)."""
    ensure_can(user, Action.BINDER_REMOVE_PIECE)
    with transaction.atomic():
        amm = _page(binder, amm_id, user)
        document = _document(amm, document_id)
        document.archived_at = timezone.now()
        document._history_user = user
        document._change_reason = "Pièce retirée depuis le classeur"
        document._skip_signals = True
        document.save(update_fields=["archived_at"])
        _reconcile(amm)
    return amm


def add_document(binder: Binder, amm_id, *, file, kind, document_date, period, user):
    """Ajoute une pièce sur une période précise, avec la date saisie (pas de lecture auto)."""
    amm = MarketingAuthorization.objects.select_related("country", "product__range").get(pk=amm_id)
    ensure_country_in_scope(user, amm.country)
    ensure_in_binder(binder, amm)
    renewal = _target_period(amm, period, lock=False)
    # ingest_document gère sa propre transaction (fichier écrit hors transaction) ; le signal du
    # document recalcule l'état du dossier.
    ingest_document(amm, file, kind, document_date=document_date, renewal=renewal, user=user)
    return amm
