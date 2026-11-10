"""Qui peut faire quoi : groupes de rôles et actions sensibles, définis en un seul endroit.

Avant la 1.1.9, plusieurs apps recopiaient leurs propres listes de rôles (`REMOVE_ROLES` des
classeurs, `REGULATORY_ROLES` des rappels). Changer une règle obligeait à les retrouver toutes.
Désormais :

- les groupes de rôles sont ici, et nulle part ailleurs ;
- une action sensible a un nom (`Action`) et une liste de rôles (`ACTION_ROLES`) ;
- le code demande `can(user, Action.X)`, ou `ensure_can(...)` côté API
  (`apps/accounts/permissions.py`), sans connaître les rôles.

Ajouter une action = une ligne dans `Action`, une dans `ACTION_ROLES`, une dans `MESSAGES`.
"""

from __future__ import annotations

from enum import StrEnum

from .models import User

Role = User.Role

ALL_ROLES = (Role.CEO_ADMIN, Role.HQ_REGULATORY, Role.COUNTRY_REGULATORY)
GLOBAL_ROLES = (Role.CEO_ADMIN, Role.HQ_REGULATORY)  # siège et CEO : tous les pays
CEO_ONLY = (Role.CEO_ADMIN,)
# Destinataires des rappels réglementaires (le CEO n'en reçoit pas).
REGULATORY_ROLES = (Role.HQ_REGULATORY, Role.COUNTRY_REGULATORY)


class Action(StrEnum):
    BINDER_EDIT = "binder.edit"
    BINDER_REMOVE_PASSAGE = "binder.remove_passage"
    BINDER_RENAME_PAGE = "binder.rename_page"
    BINDER_DELETE_PAGE = "binder.delete_page"
    BINDER_REMOVE_PIECE = "binder.remove_piece"
    BINDER_DOWNLOAD = "binder.download"


ACTION_ROLES: dict[Action, tuple[str, ...]] = {
    # Classeurs : seuls le CEO et le siège modifient ; les autres les lisent.
    Action.BINDER_EDIT: GLOBAL_ROLES,
    Action.BINDER_REMOVE_PASSAGE: GLOBAL_ROLES,
    Action.BINDER_RENAME_PAGE: GLOBAL_ROLES,
    Action.BINDER_DELETE_PAGE: GLOBAL_ROLES,
    Action.BINDER_REMOVE_PIECE: GLOBAL_ROLES,
    Action.BINDER_DOWNLOAD: GLOBAL_ROLES,
}

MESSAGES: dict[Action, str] = {
    Action.BINDER_EDIT: (
        "Les classeurs sont en lecture seule : seuls le CEO et le siège les modifient."
    ),
    Action.BINDER_REMOVE_PASSAGE: "Seuls le CEO et le siège peuvent supprimer.",
    Action.BINDER_RENAME_PAGE: "Seuls le CEO et le siège peuvent modifier le titre d'une page.",
    Action.BINDER_DELETE_PAGE: "Seuls le CEO et le siège peuvent supprimer.",
    Action.BINDER_REMOVE_PIECE: "Seuls le CEO et le siège peuvent retirer une pièce.",
    Action.BINDER_DOWNLOAD: "Le téléchargement des classeurs est réservé au siège.",
}


def can(user, action: Action) -> bool:
    """L'utilisateur (connecté, actif) a-t-il le droit de faire `action` ?"""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_active", True):
        return False
    return user.role in ACTION_ROLES[action]
