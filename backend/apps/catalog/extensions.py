"""Points d'extension du référentiel (pays, produits).

Le catalogue est dans le socle : il ne connaît ni les AMM ni les documents. Ce qu'il doit leur
demander passe par ces points, remplis par les apps métier dans leur `hooks.py`.
"""

from apps.core.registry import Provider, Registry

# `f(request, country) -> Response` : documents d'un pays (`/countries/SN/documents`).
COUNTRY_DOCUMENTS = Provider("documents d'un pays")

# `f(request, product) -> Response` : documents d'un produit (`/products/<id>/documents`).
PRODUCT_DOCUMENTS = Provider("documents d'un produit")

# `f(keep, duplicate) -> None` : rattache au produit gardé ce qui pointait vers le doublon, avant
# sa suppression (fusion de produits). Appelé dans la transaction de la fusion.
PRODUCT_MERGE = Registry("fusion de produits")

# `f(products) -> dict[product_id, list[iso2]]` : pays où chaque produit a une AMM.
PRODUCT_COUNTRIES = Provider("pays des AMM d'un produit")
