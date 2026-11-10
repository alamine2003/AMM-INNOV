"""Product merge and duplicate detection.

Duplicates come from the workbook: the same product spelled with a different punctuation on
two sheets (`B/100` vs `B100`). They share the same `Product.key`. A group is a *conflict*
when two of its products hold an AMM in the same country: merging would drop one AMM's
dates, so that decision is left to a person.
"""

from collections import Counter, defaultdict

from django.db import transaction
from django.db.models import Count

from .extensions import PRODUCT_COUNTRIES, PRODUCT_MERGE
from .models import Product, ProductAlias


@transaction.atomic
def merge_products(keep: Product, duplicate: Product) -> Product:
    if keep.pk == duplicate.pk:
        raise ValueError("Impossible de fusionner un produit avec lui-même.")
    for merge in PRODUCT_MERGE:  # les AMM du doublon (apps/amm/hooks.py)
        merge(keep, duplicate)
    ProductAlias.objects.filter(product=duplicate).update(product=keep)
    ProductAlias.objects.get_or_create(product=keep, raw_name=duplicate.name)
    if keep.range_id is None and duplicate.range_id is not None:
        keep.range = duplicate.range
        keep.save(update_fields=["range"])
    duplicate.delete()
    return keep


def _primary(products: list[dict]) -> dict:
    """The product to keep: most AMM, then most aliases, then the shortest name."""
    return sorted(
        products, key=lambda p: (-p["amm_count"], -p["alias_count"], len(p["name"]), p["name"])
    )[0]


def duplicate_groups() -> list[dict]:
    """Groups of products sharing the same key, with AMM counts, countries and conflict flag."""
    keys = [
        row["key"]
        for row in Product.objects.values("key").annotate(n=Count("id")).filter(n__gt=1)
        if row["key"]
    ]
    if not keys:
        return []
    products = list(
        Product.objects.filter(key__in=keys)
        .select_related("range")
        .annotate(alias_count=Count("aliases", distinct=True))
        .order_by("key", "name")
    )
    countries_by_product: dict = defaultdict(list, PRODUCT_COUNTRIES(products))
    by_key: dict[str, list[dict]] = defaultdict(list)
    for product in products:
        by_key[product.key].append(
            {
                "id": str(product.pk),
                "name": product.name,
                "range_code": product.range.code if product.range_id else None,
                "amm_count": len(countries_by_product[product.pk]),
                "alias_count": product.alias_count,
                "countries": sorted(countries_by_product[product.pk]),
            }
        )
    groups = []
    for key, members in by_key.items():
        seen = Counter(iso2 for member in members for iso2 in member["countries"])
        conflicts = sorted(iso2 for iso2, n in seen.items() if n > 1)
        groups.append(
            {
                "key": key,
                "products": members,
                "suggested_keep_id": _primary(members)["id"],
                "conflict_countries": conflicts,
                "conflict": bool(conflicts),
            }
        )
    groups.sort(key=lambda g: (g["conflict"], g["products"][0]["name"]))
    return groups


def merge_duplicates(dry_run: bool = False) -> dict:
    """Merges every conflict-free group into its suggested product. Conflicts are reported."""
    merged_groups = merged_products = 0
    skipped = []
    for group in duplicate_groups():
        if group["conflict"]:
            skipped.append(group)
            continue
        keep = Product.objects.get(pk=group["suggested_keep_id"])
        for member in group["products"]:
            if member["id"] == group["suggested_keep_id"]:
                continue
            if not dry_run:
                merge_products(keep, Product.objects.get(pk=member["id"]))
            merged_products += 1
        merged_groups += 1
    return {
        "dry_run": dry_run,
        "merged_groups": merged_groups,
        "merged_products": merged_products,
        "conflicts": skipped,
    }
