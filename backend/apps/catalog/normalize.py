"""Normalisation of product labels and range labels coming from the Excel workbook."""

import re
import unicodedata

_SPACES = re.compile(r"\s+")

RANGE_GENERALE = "GENERALE"
RANGE_CARDIO = "CARDIO"
RANGE_BIEN_ETRE = "BIEN_ETRE"


def normalize_product_name(raw: str | None) -> str:
    """Upper-case, trimmed, single spaces. Returns "" for empty input."""
    if raw is None:
        return ""
    return _SPACES.sub(" ", str(raw)).strip().upper()


def _ascii_upper(raw: str) -> str:
    text = unicodedata.normalize("NFKD", str(raw)).encode("ascii", "ignore").decode()
    return _SPACES.sub(" ", text).strip().upper()


def normalize_range(raw: str | None) -> str | None:
    """Maps the workbook range labels to a ProductRange code, or None when unknown.

    `GAMME GENERAL(E)` -> GENERALE ; `GAM(M)E CARDIO` -> CARDIO ; `GAMME BIEN ETRE` -> BIEN_ETRE.
    """
    if raw is None:
        return None
    text = _ascii_upper(raw).replace("-", " ").replace("_", " ")
    text = _SPACES.sub(" ", text)
    if not text:
        return None
    if "CARDIO" in text:
        return RANGE_CARDIO
    if "BIEN" in text and "ETRE" in text:
        return RANGE_BIEN_ETRE
    if "GENERAL" in text:
        return RANGE_GENERALE
    if text in {RANGE_GENERALE, RANGE_CARDIO, RANGE_BIEN_ETRE, "BIEN ETRE"}:
        return text.replace(" ", "_")
    return None
