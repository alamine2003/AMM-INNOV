"""Product merge: moves AMM, aliases and documents of a duplicate onto the kept product."""

from django.db import transaction

from .models import Product, ProductAlias


@transaction.atomic
def merge_products(keep: Product, duplicate: Product) -> Product:
    if keep.pk == duplicate.pk:
        raise ValueError("Impossible de fusionner un produit avec lui-même.")
    from apps.amm.models import MarketingAuthorization

    for amm in MarketingAuthorization.objects.filter(product=duplicate):
        existing = MarketingAuthorization.objects.filter(product=keep, country=amm.country).first()
        if existing is None:
            amm.product = keep
            amm.save()
        else:
            # Both products had an AMM in that country: keep the surviving AMM, move
            # renewals and documents so that history is preserved.
            amm.renewals.update(amm=existing)
            amm.documents.update(amm=existing)
            amm.alerts.update(amm=existing)
            amm.delete()
            existing.save()
    ProductAlias.objects.filter(product=duplicate).update(product=keep)
    ProductAlias.objects.get_or_create(product=keep, raw_name=duplicate.name)
    duplicate.delete()
    return keep
