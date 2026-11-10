"""1.1.9 : droits centralisés (`apps/accounts/roles.py`), registre du socle, conformité en
critères."""

from types import SimpleNamespace

import pytest
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import User
from apps.accounts.permissions import ensure_can
from apps.accounts.roles import ACTION_ROLES, LABELS, MESSAGES, Action, can
from apps.binders.conformity import CRITERIA, conformity
from apps.core.registry import INTEGRITY, METRICS, PENDING_WORK, RECOVERY, WORKER_START, Registry

# --- Droits -------------------------------------------------------------------------------


def _user(role, active=True, authenticated=True):
    return SimpleNamespace(role=role, is_active=active, is_authenticated=authenticated)


def test_every_action_has_roles_a_message_and_a_label():
    assert set(ACTION_ROLES) == set(Action) == set(MESSAGES) == set(LABELS)


@pytest.mark.django_db
@pytest.mark.parametrize("action", list(Action))
def test_defaults_ceo_everything_hq_but_merge_and_permissions_country_nothing(action):
    assert can(_user(User.Role.CEO_ADMIN), action)
    ceo_only = {Action.CATALOG_MERGE, Action.PERMISSIONS_MANAGE}
    assert can(_user(User.Role.HQ_REGULATORY), action) is (action not in ceo_only)
    assert not can(_user(User.Role.COUNTRY_REGULATORY), action)


def test_inactive_or_anonymous_users_can_do_nothing():
    assert not can(_user(User.Role.CEO_ADMIN, active=False), Action.BINDER_DELETE_PAGE)
    assert not can(_user(User.Role.CEO_ADMIN, authenticated=False), Action.BINDER_DELETE_PAGE)
    assert not can(None, Action.BINDER_DELETE_PAGE)


@pytest.mark.django_db
def test_ensure_can_refuses_with_the_action_message():
    with pytest.raises(PermissionDenied) as error:
        ensure_can(_user(User.Role.COUNTRY_REGULATORY), Action.BINDER_DOWNLOAD)
    assert str(error.value.detail) == MESSAGES[Action.BINDER_DOWNLOAD]


# --- Registre du socle --------------------------------------------------------------------


def test_registry_keeps_order_and_ignores_a_second_registration():
    registry = Registry("essai")

    def first(now):
        return {}

    def second(now):
        return {}

    registry.register(first)
    registry.register(second)
    registry.register(first)
    assert list(registry) == [first, second]


def test_apps_declare_their_work_to_core():
    """Ce que `core` faisait lui-même avant la 1.1.9, déclaré par chaque app."""
    names = {registry.name: {f.__module__ for f in registry} for registry in (
        RECOVERY, INTEGRITY, WORKER_START, PENDING_WORK, METRICS
    )}
    assert names[RECOVERY.name] == {
        "apps.documents.hooks",
        "apps.notifications.hooks",
        "apps.imports.hooks",
        "apps.binders.hooks",
    }
    assert names[INTEGRITY.name] == {
        "apps.amm.hooks",
        "apps.documents.hooks",
        "apps.notifications.hooks",
        "apps.imports.hooks",
    }
    assert names[WORKER_START.name] == names[PENDING_WORK.name] == {"apps.imports.hooks"}
    assert names[METRICS.name] == {"apps.amm.hooks"}


def test_integrity_checks_keep_their_order():
    codes = [f.__name__ for f in INTEGRITY]
    assert codes == [
        "check_amm_state",
        "check_single_open_renewal",
        "check_renewal_sequences",
        "check_history_matches_rows",
        "check_document_versions",
        "check_document_links",
        "check_duplicate_notifications",
        "check_alerts_without_notification",
        "check_unsent_emails",
        "check_stuck_jobs",
        "check_storage",
    ]


# --- Conformité ---------------------------------------------------------------------------


def _amm(**fields):
    defaults = {"original_number": "", "original_start_date": None}
    return SimpleNamespace(**{**defaults, **fields})


def test_conformity_lists_the_four_criteria_in_order():
    verdict = conformity(_amm(), None, None, [], None)
    assert [c["key"] for c in verdict["criteria"]] == ["digital", "paper", "scan", "data"]
    assert [c.key for c in CRITERIA] == ["digital", "paper", "scan", "data"]
    assert verdict["status"] == "NON_VERIFIE"


def test_conformity_conforme_when_every_criterion_is_right():
    from datetime import date

    amm = _amm(original_number="12/34", original_start_date=date(2024, 1, 2))
    check = SimpleNamespace(result="CONFORME")
    scan = SimpleNamespace(renewal_id=None)
    verdict = conformity(amm, None, check, [], scan, scan)
    assert verdict["status"] == "CONFORME"
    assert verdict["criteria"][3]["detail"] == "n° 12/34 du 02/01/2024"
    assert verdict["to_scan"] is False


def test_conformity_paper_present_but_decision_not_scanned():
    from datetime import date

    amm = _amm(original_number="12/34", original_start_date=date(2024, 1, 2))
    verdict = conformity(amm, None, SimpleNamespace(result="CONFORME"), [], None)
    assert verdict["status"] == "NON_CONFORME"
    assert verdict["to_scan"] is True
    assert verdict["criteria"][2] == {
        "key": "scan",
        "label": "Version scannée",
        "ok": False,
        "detail": "aucun scan de décision",
    }


def test_lower_layers_extension_points_are_filled():
    """1.2.0 : le catalogue et la fiche AMM ne connaissent plus les couches du dessus."""
    from apps.amm.extensions import HISTORY_SOURCES, LIST_ANNOTATIONS, list_annotations
    from apps.catalog.extensions import (
        COUNTRY_DOCUMENTS,
        PRODUCT_COUNTRIES,
        PRODUCT_DOCUMENTS,
        PRODUCT_MERGE,
    )

    assert [f.__module__ for f in PRODUCT_MERGE] == ["apps.amm.hooks"]
    assert [f.__module__ for f in HISTORY_SOURCES] == ["apps.imports.hooks"]
    assert [f.__module__ for f in LIST_ANNOTATIONS] == ["apps.imports.hooks"]
    assert set(list_annotations()) == {"open_review_points"}
    for provider in (COUNTRY_DOCUMENTS, PRODUCT_DOCUMENTS, PRODUCT_COUNTRIES):
        assert provider._function is not None, provider.name


def test_provider_without_supplier_says_what_is_missing():
    from apps.core.registry import Provider

    with pytest.raises(RuntimeError, match="essai"):
        Provider("essai")()


# --- /me : actions permises, lues par l'interface (useCan) ----------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("ceo", {a.value for a in Action}),
        ("hq", {a.value for a in Action} - {"catalog.merge", "permissions.manage"}),
        ("country", set()),
    ],
)
def test_me_lists_the_actions_the_user_can_do(users, role, expected):
    from tests.conftest import client_for

    body = client_for(users[role]).get("/api/v1/me").json()
    assert set(body["actions"]) == expected
