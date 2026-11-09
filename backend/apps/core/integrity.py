"""Contrôles d'intégrité : le cadre commun, sans aucun invariant métier.

Chaque app déclare ses invariants dans son `hooks.py` (`@INTEGRITY.register`) ; la commande
`manage.py check_integrity` les exécute tous. Gravités : ERROR (donnée incohérente ou perdue,
code de sortie 1), WARNING (fuite ou retard sans perte, réparable).
"""

from __future__ import annotations

from dataclasses import dataclass

from .registry import INTEGRITY

ERROR, WARNING = "ERROR", "WARNING"
SAMPLE = 20


class Check:
    def __init__(self, code: str, severity: str, question: str):
        self.code, self.severity, self.question = code, severity, question
        self.items: list[str] = []

    def add(self, item) -> None:
        self.items.append(str(item))

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "question": self.question,
            "count": len(self.items),
            "sample": self.items[:SAMPLE],
        }


@dataclass(frozen=True)
class IntegrityOptions:
    stuck_minutes: int = 30
    since: str | None = None  # date ISO : ne juger que ce qui a été créé après
    skip_storage: bool = False  # ne pas interroger le stockage des fichiers


def run_checks(options: IntegrityOptions) -> list[Check]:
    checks: list[Check] = []
    for function in INTEGRITY:
        result = function(options)
        checks.extend(result if isinstance(result, list) else [result])
    return checks
