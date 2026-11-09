"""Règles d'import entre les apps (revue d'architecture du 09/11/2026, version 1.1.9).

Trois couches ; une app n'importe que sa couche ou celles du dessous :

1. socle : core, accounts, catalog, realtime ;
2. métier : amm, documents, alerts, deposits, notifications ;
3. fonctions transverses : imports, binders, analytics.

`core` est plus strict encore : il n'importe aucune autre app. Les apps s'y déclarent
(`apps/core/registry.py`).

Les écarts qui existent encore sont listés dans `KNOWN_EXCEPTIONS`, à corriger dans le palier
1.2.0. La liste ne peut que raccourcir : un nouvel écart fait échouer le test, et un écart
corrigé aussi, tant qu'il reste dans la liste.
"""

import ast
from pathlib import Path

APPS_DIR = Path(__file__).resolve().parent.parent / "apps"

LAYERS = {
    "core": 1,
    "accounts": 1,
    "catalog": 1,
    "realtime": 1,
    "amm": 2,
    "documents": 2,
    "alerts": 2,
    "deposits": 2,
    "notifications": 2,
    "imports": 3,
    "binders": 3,
    "analytics": 3,
}

# (fichier, app importée) : imports qui remontent les couches, à supprimer en 1.2.0.
KNOWN_EXCEPTIONS = {
    # Données de démonstration : l'outil de développement remplit toutes les apps.
    ("accounts/management/commands/seed_demo.py", "alerts"),
    ("accounts/management/commands/seed_demo.py", "amm"),
    ("accounts/management/commands/seed_demo.py", "documents"),
    ("accounts/management/commands/seed_demo.py", "imports"),
    # L'historique et la liste des AMM lisent les changements et points des imports de dossiers.
    ("amm/history.py", "imports"),
    ("amm/views.py", "imports"),
    # Le référentiel produits compte les AMM et documents d'un produit (fusion de doublons).
    ("catalog/services.py", "amm"),
    ("catalog/views.py", "documents"),
}


def _imports():
    """(fichier relatif à apps/, app qui importe, app importée) pour chaque import absolu."""
    for path in sorted(APPS_DIR.rglob("*.py")):
        relative = path.relative_to(APPS_DIR)
        if "migrations" in relative.parts:
            continue
        app = relative.parts[0]
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module]
            elif isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            else:
                continue
            for module in modules:
                parts = module.split(".")
                if parts[0] == "apps" and len(parts) > 1 and parts[1] != app:
                    yield relative.as_posix(), app, parts[1]


def test_every_app_has_a_layer():
    apps = {path.name for path in APPS_DIR.iterdir() if (path / "apps.py").exists()}
    assert apps == set(LAYERS)


def test_core_imports_no_other_app():
    found = sorted({(path, target) for path, app, target in _imports() if app == "core"})
    assert found == [], (
        "apps/core ne doit importer aucune app : déclarez le besoin dans le hooks.py de l'app "
        f"(apps/core/registry.py). Imports trouvés : {found}"
    )


def test_apps_only_import_their_layer_or_below():
    upward = {
        (path, target) for path, app, target in _imports() if LAYERS[target] > LAYERS[app]
    }
    new = sorted(upward - KNOWN_EXCEPTIONS)
    fixed = sorted(KNOWN_EXCEPTIONS - upward)
    assert not new, f"Import vers une couche supérieure : {new}"
    assert not fixed, f"Écart corrigé : retirez-le de KNOWN_EXCEPTIONS : {fixed}"
