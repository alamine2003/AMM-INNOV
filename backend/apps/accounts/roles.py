"""Qui peut faire quoi : groupes de rôles et actions sensibles, définis en un seul endroit.

Avant la 1.1.9, plusieurs apps recopiaient leurs propres listes de rôles (`REMOVE_ROLES` des
classeurs, `REGULATORY_ROLES` des rappels). Changer une règle obligeait à les retrouver toutes.
Désormais :

- les groupes de rôles sont ici, et nulle part ailleurs ;
- une action sensible a un nom (`Action`) et une liste de rôles (`ACTION_ROLES`) ;
- le code demande `can(user, Action.X)`, ou `ensure_can(...)` côté API
  (`apps/accounts/permissions.py`), sans connaître les rôles.

Ajouter une action = une ligne dans `Action`, une dans `ACTION_ROLES`, une dans `MESSAGES`,
une dans `LABELS`.

Depuis la 1.2.3, `ACTION_ROLES` n'est plus que le réglage par défaut : le CEO coche, pour le
siège et les pays, qui peut faire quoi (Administration › Permissions, table `ActionGrant`). Le CEO
garde toujours tous les droits, et seul lui règle les permissions : personne ne peut s'enfermer
dehors. Le périmètre pays (ce qu'un utilisateur pays voit) ne se règle pas ici.
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
    TRASH_RESTORE = "trash.restore"
    CATALOG_MANAGE = "catalog.manage"
    CATALOG_MERGE = "catalog.merge"
    DOCUMENT_DELETE = "documents.delete"
    ALERT_RULES_MANAGE = "alerts.manage_rules"
    PIECE_TYPES_MANAGE = "deposits.manage_pieces"
    AUDIT_VIEW = "audit.view"
    PERMISSIONS_MANAGE = "permissions.manage"
    ERRORS_VIEW = "errors.view"


ACTION_ROLES: dict[Action, tuple[str, ...]] = {
    # Classeurs : seuls le CEO et le siège modifient ; les autres les lisent.
    Action.BINDER_EDIT: GLOBAL_ROLES,
    Action.BINDER_REMOVE_PASSAGE: GLOBAL_ROLES,
    Action.BINDER_RENAME_PAGE: GLOBAL_ROLES,
    Action.BINDER_DELETE_PAGE: GLOBAL_ROLES,
    Action.BINDER_REMOVE_PIECE: GLOBAL_ROLES,
    Action.BINDER_DOWNLOAD: GLOBAL_ROLES,
    # Corbeille : voir et restaurer ce qui a été supprimé (CEO et siège).
    Action.TRASH_RESTORE: GLOBAL_ROLES,
    # Référentiels : pays, gammes, produits (création, modification, suppression).
    Action.CATALOG_MANAGE: GLOBAL_ROLES,
    Action.CATALOG_MERGE: CEO_ONLY,
    # Retirer un scan (il reste dans l'historique).
    Action.DOCUMENT_DELETE: GLOBAL_ROLES,
    Action.ALERT_RULES_MANAGE: GLOBAL_ROLES,
    Action.PIECE_TYPES_MANAGE: GLOBAL_ROLES,
    # Audit et traçabilité : qui a fait quoi, quand.
    Action.AUDIT_VIEW: GLOBAL_ROLES,
    # Régler les permissions : le CEO seul, et ce droit ne se règle pas.
    Action.PERMISSIONS_MANAGE: CEO_ONLY,
    # Journal des erreurs de production (serveur, tâches, interface).
    Action.ERRORS_VIEW: CEO_ONLY,
}

# Actions que la page Permissions ne modifie pas.
LOCKED: frozenset[Action] = frozenset({Action.PERMISSIONS_MANAGE})
# Rôles réglables : le CEO garde toujours tout.
CONFIGURABLE_ROLES = (Role.HQ_REGULATORY, Role.COUNTRY_REGULATORY)

MESSAGES: dict[Action, str] = {
    Action.BINDER_EDIT: (
        "Les classeurs sont en lecture seule : seuls le CEO et le siège les modifient."
    ),
    Action.BINDER_REMOVE_PASSAGE: "Seuls le CEO et le siège peuvent supprimer.",
    Action.BINDER_RENAME_PAGE: "Seuls le CEO et le siège peuvent modifier le titre d'une page.",
    Action.BINDER_DELETE_PAGE: "Seuls le CEO et le siège peuvent supprimer.",
    Action.BINDER_REMOVE_PIECE: "Seuls le CEO et le siège peuvent retirer une pièce.",
    Action.BINDER_DOWNLOAD: "Le téléchargement des classeurs est réservé au siège.",
    Action.TRASH_RESTORE: "La corbeille est réservée au CEO et au siège.",
    Action.CATALOG_MANAGE: "Vous ne pouvez pas modifier les référentiels.",
    Action.CATALOG_MERGE: "Vous ne pouvez pas fusionner des produits.",
    Action.DOCUMENT_DELETE: "Vous ne pouvez pas retirer un scan.",
    Action.ALERT_RULES_MANAGE: "Vous ne pouvez pas modifier les règles d'alerte.",
    Action.PIECE_TYPES_MANAGE: "Vous ne pouvez pas modifier les pièces demandées.",
    Action.AUDIT_VIEW: "Vous n'avez pas accès à l'audit.",
    Action.PERMISSIONS_MANAGE: "Seul le CEO règle les permissions.",
    Action.ERRORS_VIEW: "Le journal des erreurs est réservé au CEO.",
}

# (rubrique, libellé) affichés sur la page Permissions.
LABELS: dict[Action, tuple[str, str]] = {
    Action.BINDER_EDIT: ("Classeurs", "Modifier les classeurs (constats, cartes, à imprimer)"),
    Action.BINDER_REMOVE_PASSAGE: ("Classeurs", "Supprimer un passage de la chronologie"),
    Action.BINDER_RENAME_PAGE: ("Classeurs", "Renommer une page"),
    Action.BINDER_DELETE_PAGE: ("Classeurs", "Supprimer une page"),
    Action.BINDER_REMOVE_PIECE: ("Classeurs", "Retirer une pièce"),
    Action.BINDER_DOWNLOAD: ("Classeurs", "Télécharger et imprimer un classeur"),
    Action.CATALOG_MANAGE: ("Référentiels", "Gérer pays, gammes et produits"),
    Action.CATALOG_MERGE: ("Référentiels", "Fusionner des produits"),
    Action.DOCUMENT_DELETE: ("Documents", "Retirer un scan"),
    Action.ALERT_RULES_MANAGE: ("Alertes", "Modifier les règles d'alerte"),
    Action.PIECE_TYPES_MANAGE: ("Dépôts", "Modifier les pièces demandées"),
    Action.TRASH_RESTORE: ("Administration", "Voir la corbeille et restaurer"),
    Action.AUDIT_VIEW: ("Administration", "Consulter l'audit"),
    Action.PERMISSIONS_MANAGE: ("Administration", "Régler les permissions"),
    Action.ERRORS_VIEW: ("Administration", "Consulter le journal des erreurs"),
}


def can(user, action: Action) -> bool:
    """L'utilisateur (connecté, actif) a-t-il le droit de faire `action` ?"""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_active", True):
        return False
    if action in LOCKED or user.role not in CONFIGURABLE_ROLES:
        return user.role in ACTION_ROLES[action]
    grants = _role_grants(user)
    if action.value in grants:
        return grants[action.value]
    return user.role in ACTION_ROLES[action]


def _role_grants(user) -> dict[str, bool]:
    """Réglages du CEO pour le rôle de `user`, lus une fois par requête (l'objet utilisateur
    est rechargé à chaque requête : un changement s'applique dès la suivante)."""
    grants = getattr(user, "_action_grants", None)
    if grants is None:
        from .models import ActionGrant

        grants = dict(ActionGrant.objects.filter(role=user.role).values_list("action", "allowed"))
        user._action_grants = grants
    return grants


def matrix() -> dict[tuple[Action, str], bool]:
    """{(action, rôle): autorisé} pour tous les rôles : réglage du CEO, sinon défaut."""
    from .models import ActionGrant

    grants = {
        (action, role): value
        for action, role, value in ActionGrant.objects.values_list("action", "role", "allowed")
    }
    result = {}
    for action in Action:
        for role in ALL_ROLES:
            default = role in ACTION_ROLES[action]
            configurable = action not in LOCKED and role in CONFIGURABLE_ROLES
            result[(action, role)] = (
                grants.get((action.value, role), default) if configurable else default
            )
    return result
