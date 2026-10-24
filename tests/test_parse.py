from datetime import date
from decimal import Decimal

import pytest

from oraculoto.db.draws import WinnerLocation
from oraculoto.importer.parse import parse_date, parse_int, parse_locations, parse_money


@pytest.mark.parametrize(("text", "expected"), [("04", 4), (" 60 ", 60), ("3072", 3072), ("4.0", 4)])
def test_parse_int(text, expected):
    assert parse_int(text) == expected


@pytest.mark.parametrize("text", ["", None, "4.5", "-1", "4a", "R$4"])
def test_parse_int_rejects(text):
    with pytest.raises(ValueError):
        parse_int(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("11/03/1996", date(1996, 3, 11)),
        ("20/10/2026", date(2026, 10, 20)),
        ("35135", date(1996, 3, 11)),  # Excel serial, from a re-saved file
        ("1996-03-11", date(1996, 3, 11)),
    ],
)
def test_parse_date(text, expected):
    assert parse_date(text) == expected


@pytest.mark.parametrize("text", ["", "31/02/2020", "1996/03/11", "11-03-1996", "ontem"])
def test_parse_date_rejects(text):
    with pytest.raises(ValueError):
        parse_date(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("R$0,00", Decimal("0.00")),
        ("R$954,26", Decimal("954.26")),
        ("R$1.714.650,23", Decimal("1714650.23")),
        ("R$3.052.431.720,00", Decimal("3052431720.00")),
        ("1714650.23", Decimal("1714650.23")),  # re-saved file
        ("1714650.2300000001", Decimal("1714650.23")),
        ("330.205", Decimal("330.21")),
    ],
)
def test_parse_money(text, expected):
    value = parse_money(text)
    assert value == expected
    assert value.as_tuple().exponent == -2


@pytest.mark.parametrize(
    "text", ["", "R$1714650,23", "R$ 1,00", "R$1.000", "R$1,0", "1.714,65", "R$-1,00", "US$1,00"]
)
def test_parse_money_rejects(text):
    with pytest.raises(ValueError):
        parse_money(text)


def test_locations_every_kind():
    locations, warnings = parse_locations(
        "SÃO PAULO/SP; SAO PAULO/SP;São Paulo/SP; DF; CANAL ELETRONICO; Canal Eletrônico; Cerquilho/ES"
    )
    assert locations == (
        WinnerLocation(raw="SÃO PAULO/SP", city="SÃO PAULO", uf="SP"),
        WinnerLocation(raw="SAO PAULO/SP", city="SAO PAULO", uf="SP"),
        WinnerLocation(raw="São Paulo/SP", city="São Paulo", uf="SP"),
        WinnerLocation(raw="DF", uf="DF"),
        WinnerLocation(raw="CANAL ELETRONICO", is_online=True),
        WinnerLocation(raw="Canal Eletrônico", is_online=True),
        WinnerLocation(raw="Cerquilho/ES", city="Cerquilho", uf="ES"),  # wrong state, kept as is
    )
    assert warnings == []
    assert all(loc.winners is None for loc in locations)


def test_locations_unknown_text_is_kept_with_warning():
    locations, warnings = parse_locations("algum lugar")
    assert locations == (WinnerLocation(raw="algum lugar"),)
    assert warnings == ["unrecognized location 'algum lugar'"]


@pytest.mark.parametrize("text", ["", None, " ", " ; "])
def test_locations_empty(text):
    assert parse_locations(text) == ((), [])
