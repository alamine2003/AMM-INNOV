"""Reconnaissance prudente et explicable des champs réglementaires d'un dossier.

Découpée par sujet (palier 1.2.0) :

- `text` : texte sans accents ni casse, distance d'édition ;
- `dates` : dates en lettres ou en chiffres, lues par OCR, validité imprimée ;
- `numbers` : n° d'AMM et source de chaque lecture ;
- `holder` : titulaire et ligne du produit ;
- `tables` : tableaux des recueils (une ligne par présentation) ;
- `sections` : recueils découpés en décisions, regroupés par spécialité ;
- `files` : reconnaissance d'un fichier du dossier (pays, produit, période, n°, dates).

Ce module garde les noms utilisés ailleurs : `from .recognition import recognize_file` marche
comme avant.
"""

from .dates import _validity_period, parse_date
from .files import country_labels, recognize_file
from .numbers import _authorization_number
from .sections import PAGE_BREAK, decision_sections, specialty_groups, specialty_key
from .tables import table_rows
from .text import _edit_distance, fold, normalize

__all__ = [
    "PAGE_BREAK",
    "_authorization_number",
    "_edit_distance",
    "_validity_period",
    "country_labels",
    "decision_sections",
    "fold",
    "normalize",
    "parse_date",
    "recognize_file",
    "specialty_groups",
    "specialty_key",
    "table_rows",
]
