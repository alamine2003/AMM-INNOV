"""Points d'extension des fiches AMM, remplis par les fonctions transverses (imports…).

L'app AMM est dans la couche métier : elle ne connaît pas les imports de dossiers. Ce qu'ils
ajoutent à la fiche passe par ces points, remplis dans leur `hooks.py`.
"""

from apps.core.registry import Registry

# `f(amm) -> list[dict]` : entrées ajoutées à l'historique d'une fiche (même format que
# `apps/amm/history.py` : date, user_email, type, model, object_id, changes…).
HISTORY_SOURCES = Registry("historique d'une fiche AMM")

# `f() -> dict[str, Expression]` : annotations ajoutées à la liste des AMM (colonnes calculées
# par une autre app, par exemple le nombre de points à vérifier laissés par un import).
LIST_ANNOTATIONS = Registry("colonnes calculées de la liste des AMM")


def list_annotations() -> dict:
    annotations: dict = {}
    for function in LIST_ANNOTATIONS:
        annotations.update(function())
    return annotations
