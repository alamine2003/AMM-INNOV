#!/usr/bin/env python3
"""Numéro de version d'AMM GH, selon docs/versionnement.md.

    python3 scripts/release.py            affiche la version en cours et la suivante
    python3 scripts/release.py publier    passe à la version suivante (fichiers + CHANGELOG)
    python3 scripts/release.py --check    vérifie la cohérence (lancé par la CI)

Règle : 1.0.0, 1.0.1 … 1.0.9, puis 1.1.0, 1.1.1 … 1.1.9, puis 1.2.0 … jusqu'à 1.9.9, puis 2.0.0.
Le numéro n'est écrit qu'à trois endroits, tenus identiques par ce script :
backend/VERSION (lu par l'API), frontend/package.json et frontend/package-lock.json.
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "backend" / "VERSION"
PACKAGE = ROOT / "frontend" / "package.json"
LOCK = ROOT / "frontend" / "package-lock.json"
CHANGELOG = ROOT / "CHANGELOG.md"

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
SECTION = re.compile(r"^## \[(\d+\.\d+\.\d+)\] — (\d{4}-\d{2}-\d{2})$", re.MULTILINE)
UNRELEASED = "## [Non publié]"


def parse(version: str) -> tuple[int, int, int]:
    match = SEMVER.match(version.strip())
    if not match:
        raise ValueError(f"« {version.strip()} » n'est pas un numéro de la forme 1.0.1")
    major, minor, patch = (int(part) for part in match.groups())
    if minor > 9 or patch > 9:
        raise ValueError(f"« {version.strip()} » sort du plan : chaque chiffre va de 0 à 9")
    return major, minor, patch


def following(version: str) -> str:
    """La seule version permise après `version` : correctif, palier après .9, majeure après .9.9."""
    major, minor, patch = parse(version)
    if patch < 9:
        return f"{major}.{minor}.{patch + 1}"
    if minor < 9:
        return f"{major}.{minor + 1}.0"
    return f"{major + 1}.0.0"


def kind(version: str) -> str:
    _, minor, patch = parse(version)
    if patch:
        return "mise à jour corrective"
    return "palier" if minor else "version majeure"


def current() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def unreleased_body(text: str) -> str:
    start = text.index(UNRELEASED) + len(UNRELEASED)
    following_section = SECTION.search(text, start)
    return text[start : following_section.start() if following_section else len(text)].strip()


def check() -> list[str]:
    problems: list[str] = []
    try:
        version = current()
        parse(version)
    except (OSError, ValueError) as error:
        return [f"backend/VERSION : {error}"]
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))["version"]
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    for label, found in (
        ("frontend/package.json", package),
        ("frontend/package-lock.json", lock["version"]),
        ("frontend/package-lock.json (paquet racine)", lock["packages"][""]["version"]),
    ):
        if found != version:
            problems.append(f"{label} indique {found}, backend/VERSION indique {version}")
    text = CHANGELOG.read_text(encoding="utf-8")
    if UNRELEASED not in text:
        problems.append("CHANGELOG.md : la section « ## [Non publié] » a disparu")
    published = [match.group(1) for match in SECTION.finditer(text)]
    if not published or published[0] != version:
        problems.append(
            f"CHANGELOG.md : la première version datée doit être {version}"
            f" (trouvé : {published[0] if published else 'aucune'})"
        )
    # Du plus récent au plus ancien : chaque version suit la précédente, sans saut ni retour.
    for newer, older in zip(published, published[1:], strict=False):
        if following(older) != newer:
            problems.append(
                f"CHANGELOG.md : après {older} le plan prévoit {following(older)}, pas {newer}"
            )
    return problems


def publish() -> int:
    problems = check()
    if problems:
        print("Publication refusée, le dépôt n'est pas cohérent :")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    text = CHANGELOG.read_text(encoding="utf-8")
    if not unreleased_body(text):
        print("Rien à publier : la section « Non publié » de CHANGELOG.md est vide.")
        print("Notez-y d'abord ce que contient cette version (étape 11 du cycle).")
        return 1
    version = following(current())
    today = datetime.date.today().isoformat()
    CHANGELOG.write_text(
        text.replace(UNRELEASED, f"{UNRELEASED}\n\n## [{version}] — {today}", 1), encoding="utf-8"
    )
    VERSION_FILE.write_text(f"{version}\n", encoding="utf-8")
    for path in (PACKAGE, LOCK):
        # Remplacement ciblé : on ne réécrit pas le fichier, pour garder sa mise en forme.
        content = path.read_text(encoding="utf-8")
        occurrences = 2 if path == LOCK else 1
        updated, count = re.subn(
            r'("name": "amm-innov-frontend",\s*(?:"private": true,\s*)?"version": ")[^"]+(")',
            rf"\g<1>{version}\g<2>",
            content,
            count=occurrences,
        )
        if count != occurrences:
            print(f"{path.name} : numéro de version introuvable, rien n'a été modifié ici.")
            return 1
        path.write_text(updated, encoding="utf-8")
    print(f"AMM GH passe à la version {version} ({kind(version)}).")
    if kind(version) != "mise à jour corrective":
        print("Changement de palier : suivez la liste « Palier » de docs/versionnement.md.")
    print("Suite : relisez CHANGELOG.md, ouvrez la PR, puis après la fusion, ligne par ligne :")
    print("  git checkout main")
    print("  git pull")
    print(f"  cat backend/VERSION        (doit afficher {version})")
    print(f"  git tag v{version}")
    print(f"  git push origin v{version}")
    return 0


def main(argv: list[str]) -> int:
    if argv == ["--check"]:
        problems = check()
        for problem in problems:
            print(f"ERREUR : {problem}")
        if not problems:
            print(f"Version {current()} cohérente.")
        return 1 if problems else 0
    if argv == ["publier"]:
        return publish()
    if argv:
        print(__doc__)
        return 2
    version = current()
    upcoming = following(version)
    print(f"Version en cours : {version}")
    print(f"Version suivante : {upcoming} ({kind(upcoming)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
