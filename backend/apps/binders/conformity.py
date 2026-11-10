"""Conformité d'un dossier du classeur : les 4 niveaux de vérification, et les compteurs.

1. Visible dans le classeur numérique : la fiche existe dans AMM GH (toujours vrai pour une
   page ; un dossier papier sans fiche est une « page en trop »).
2. Dossier papier dans le classeur : constat de l'archiviste (présent ou absent).
3. Décision en vigueur scannée : dans AMM GH, automatiquement.
4. Bonne date et bon n° d'AMM : relevés sur le papier par l'archiviste (« Conforme » ou
   « Corriger »), renseignés, et inchangés depuis.

« Le dossier est conforme » quand les 4 sont justes ; pas encore vérifié tant que le papier
n'a pas été constaté. Le résultat est recalculé à chaque lecture : un scan ajouté plus tard, ou
une fiche modifiée après le constat, le met à jour.

Chaque niveau est une classe `Criterion` (principe ouvert/fermé) : ajouter un niveau, c'est
ajouter une classe à `CRITERIA`, sans toucher au calcul du résultat ni aux compteurs.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

CONFORMITY_LABELS = {
    "CONFORME": "Le dossier est conforme",
    "NON_CONFORME": "Dossier non conforme",
    "NON_VERIFIE": "Dossier pas encore vérifié",
}


def scan_of_decision(amm, renewal, scans):
    """Le scan de la décision en vigueur (dernier renouvellement obtenu, sinon l'origine)."""
    wanted = renewal.pk if renewal else None
    return next((doc for doc in scans if doc.renewal_id == wanted), None)


@dataclass(frozen=True)
class Dossier:
    """Ce qu'on sait d'une page pour juger sa conformité.

    - `renewal` : dernier renouvellement obtenu (None : l'AMM d'origine est en vigueur) ;
    - `check` : constat de l'archiviste (`BinderCheck`), None s'il n'a pas encore été fait ;
    - `changed` : champs modifiés sur la fiche depuis le constat ;
    - `current_scan` : scan de la décision en vigueur ; `scan` : le scan affiché sur la page.
    """

    amm: object
    renewal: object
    check: object
    changed: list
    current_scan: object
    scan: object = None

    @property
    def number(self):
        return self.renewal.number if self.renewal else self.amm.original_number

    @property
    def start(self):
        return self.renewal.start_date if self.renewal else self.amm.original_start_date

    @property
    def known(self) -> bool:
        """Une décision est-elle enregistrée sur la fiche ?"""
        return bool(self.renewal) or bool(self.amm.original_number or self.amm.original_start_date)

    @property
    def decision(self) -> str:
        return f"renouvellement {self.renewal.sequence}" if self.renewal else "AMM d'origine"

    @cached_property
    def paper(self) -> bool | None:
        """Papier présent (True), absent (False), pas encore constaté (None)."""
        return None if self.check is None else self.check.result != "ABSENT"

    @property
    def scanned(self) -> bool:
        return self.known and self.current_scan is not None


class Criterion:
    """Un niveau de vérification : `evaluate` rend (juste ?, explication)."""

    key: str
    label: str

    def evaluate(self, dossier: Dossier) -> tuple[bool | None, str]:
        raise NotImplementedError

    def as_dict(self, dossier: Dossier) -> dict:
        ok, detail = self.evaluate(dossier)
        return {"key": self.key, "label": self.label, "ok": ok, "detail": detail}


class DigitalCriterion(Criterion):
    key, label = "digital", "Visible dans le classeur numérique"

    def evaluate(self, dossier):
        return True, "fiche dans AMM GH"


class PaperCriterion(Criterion):
    key, label = "paper", "Dossier papier dans le classeur"
    DETAILS = {None: "à constater", True: "présent", False: "absent du classeur"}

    def evaluate(self, dossier):
        return dossier.paper, self.DETAILS[dossier.paper]


class ScanCriterion(Criterion):
    key, label = "scan", "Version scannée"

    def evaluate(self, dossier):
        if not dossier.known:
            return False, "aucune décision enregistrée sur la fiche"
        if dossier.current_scan is not None:
            return True, f"décision scannée ({dossier.decision})"
        if dossier.scan is not None:
            return False, f"la décision en vigueur ({dossier.decision}) n'est pas scannée"
        return False, "aucun scan de décision"


class DataCriterion(Criterion):
    key, label = "data", "Bonne date et bon n° d'AMM"

    def evaluate(self, dossier):
        if dossier.check is None:
            return None, "à relever sur le papier"
        if not dossier.paper:
            return None, "pas de papier pour le vérifier"
        if dossier.changed:
            return False, "la fiche a changé depuis la vérification : à revérifier"
        number, start = dossier.number, dossier.start
        if not number or not start:
            missing = " et ".join(
                label for label, value in (("date", start), ("n° d'AMM", number)) if not value
            )
            return False, f"{missing} manquant{'s' if ' et ' in missing else ''}"
        return True, f"n° {number} du {start:%d/%m/%Y}"


CRITERIA: tuple[Criterion, ...] = (
    DigitalCriterion(),
    PaperCriterion(),
    ScanCriterion(),
    DataCriterion(),
)


def conformity(amm, renewal, check, changed, current_scan, scan=None) -> dict:
    """Les 4 niveaux de vérification d'un dossier, et le résultat (voir le module)."""
    dossier = Dossier(amm, renewal, check, changed, current_scan, scan)
    criteria = [criterion.as_dict(dossier) for criterion in CRITERIA]
    if dossier.paper is None:
        status = "NON_VERIFIE"
    elif all(item["ok"] is True for item in criteria):
        status = "CONFORME"
    else:
        status = "NON_CONFORME"
    return {
        "status": status,
        "label": CONFORMITY_LABELS[status],
        "criteria": criteria,
        "to_scan": bool(dossier.paper) and not dossier.scanned and dossier.known,
        "stale": bool(changed),
    }


# --- Compteurs des classeurs et de l'étagère ----------------------------------------------

COUNT_KEYS = (
    "total",  # pages du classeur
    "checked",  # papier constaté (présent ou absent)
    "conformes",  # les 4 niveaux justes : « Le dossier est conforme »
    "non_conformes",  # constatées, au moins un niveau faux
    "corrected",  # date ou n° corrigé sur la fiche d'après le papier
    "absent",  # dossier papier absent du classeur
    "to_scan",  # papier présent, décision en vigueur non scannée
    "stale",  # fiche modifiée depuis le constat : à revérifier
    "to_print",  # scan à imprimer et ranger dans le classeur papier (sans effet sur la conformité)
)


def empty_counts() -> dict:
    return dict.fromkeys(COUNT_KEYS, 0)


def add_to_counts(counts: dict, verdict: dict, result: str | None, to_print: bool = False) -> None:
    """Les compteurs viennent du même calcul que la page (`conformity`) : pas d'écart possible."""
    counts["total"] += 1
    counts["to_print"] += bool(to_print)  # vérifiée ou non, conforme ou non
    if verdict["status"] == "NON_VERIFIE":
        return
    counts["checked"] += 1
    counts["conformes" if verdict["status"] == "CONFORME" else "non_conformes"] += 1
    if result == "CORRIGE":
        counts["corrected"] += 1
    if result == "ABSENT":
        counts["absent"] += 1
    counts["to_scan"] += verdict["to_scan"]
    counts["stale"] += verdict["stale"]
