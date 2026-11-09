"""Role matrix and country-scope filtering shared by every API view.

- CEO_ADMIN: everything.
- HQ_REGULATORY: everything except document deletion and management of CEO accounts.
- COUNTRY_REGULATORY: read/write on AMM, renewals, documents and alerts of its own
  countries only; read-only on referentials; no user management.
"""

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .roles import ALL_ROLES, CEO_ONLY, GLOBAL_ROLES, MESSAGES, Action, can

__all__ = [
    "ALL_ROLES",
    "CEO_ONLY",
    "GLOBAL_ROLES",
    "CountryScopedQuerysetMixin",
    "IsGlobalRole",
    "RolePermission",
    "ensure_can",
    "ensure_country_in_scope",
]


class RolePermission(BasePermission):
    """Checks the request method against the view's role attributes.

    View attributes (all optional):
    - `write_roles`: roles allowed for POST/PUT/PATCH (default: every role);
    - `delete_roles`: roles allowed for DELETE (default: `write_roles`);
    - `action_roles`: {action_name: roles} for custom actions.
    """

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        action = getattr(view, "action", None)
        action_roles = getattr(view, "action_roles", {})
        if action in action_roles:
            return user.role in action_roles[action]
        if request.method in SAFE_METHODS:
            return True
        roles = getattr(view, "write_roles", ALL_ROLES)
        if request.method == "DELETE":
            roles = getattr(view, "delete_roles", roles)
        return user.role in roles


class IsGlobalRole(BasePermission):
    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.is_global)


class CountryScopedQuerysetMixin:
    """Filters the queryset on `user.countries` for COUNTRY_REGULATORY users.

    `country_lookup` is the ORM path to the country FK (e.g. "country", "amm__country").
    """

    country_lookup = "country"

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if user.is_authenticated and not user.is_global:
            queryset = queryset.filter(**{f"{self.country_lookup}__in": user.countries.all()})
        return queryset


def ensure_can(user, action: Action) -> None:
    """Refuse (403) une action sensible à un rôle qui n'y a pas droit (`apps/accounts/roles.py`)."""
    if not can(user, action):
        raise PermissionDenied(MESSAGES[action])


def ensure_country_in_scope(user, country) -> None:
    """Raises 403 when a COUNTRY_REGULATORY user targets a country outside its scope."""
    if country is None or user.is_global:
        return
    if not user.can_access_country(country):
        raise PermissionDenied("Ce pays est hors de votre périmètre.")
