import pytest

from apps.catalog.normalize import normalize_product_name, normalize_range


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  artegen   120mg  ", "ARTEGEN 120MG"),
        ("Alfa\tGH\n10mg", "ALFA GH 10MG"),
        ("", ""),
        (None, ""),
        ("DÉJÀ NORMALISÉ", "DÉJÀ NORMALISÉ"),
    ],
)
def test_normalize_product_name(raw, expected):
    assert normalize_product_name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("GAMME GENERALE", "GENERALE"),
        ("GAMME GENERAL", "GENERALE"),
        ("gamme générale", "GENERALE"),
        ("GAMME CARDIO", "CARDIO"),
        ("GAME CARDIO", "CARDIO"),
        ("CARDIO", "CARDIO"),
        ("GAMME BIEN ETRE", "BIEN_ETRE"),
        ("GAMME BIEN-ÊTRE", "BIEN_ETRE"),
        ("BIEN_ETRE", "BIEN_ETRE"),
        ("", None),
        (None, None),
        ("AUTRE CHOSE", None),
    ],
)
def test_normalize_range(raw, expected):
    assert normalize_range(raw) == expected
