"""Règles d'import entre les apps (revue d'architecture du 09/11/2026, version 1.1.9).

Trois couches ; une app n'importe que sa couche ou celles du dessous :

1. socle : core, accounts, catalog, realtime ;
2. métier : amm, documents, alerts, deposits, notifications ;
3. fonctions transverses : imports, binders, analytics.

`core` est plus strict encore : il n'importe aucune autre app. Les apps s'y déclarent
(`apps/core/registry.py`). Quand une couche basse a besoin d'une couche haute, elle ouvre un
point d'extension (`apps/catalog/extensions.py`, `apps/amm/extensions.py`) que la couche haute
remplit dans son `hooks.py`.

Depuis le palier 1.2.0, il n'y a plus aucune exception.
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
    "demo": 3,  # données de démonstration (seed_demo) : outil, aucune app ne l'importe
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
    upward = sorted(
        (path, target) for path, app, target in _imports() if LAYERS[target] > LAYERS[app]
    )
    assert upward == [], (
        "Import vers une couche supérieure : ouvrez un point d'extension dans l'app du dessous "
        f"et remplissez-le dans le hooks.py de l'app du dessus. {upward}"
    )


def test_no_app_imports_the_demo_tools():
    found = sorted({(path, app) for path, app, target in _imports() if target == "demo"})
    assert found == []
