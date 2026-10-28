"""Caixa's JSON → DrawData (docs/crawler.md §4), and the protocol's plan and classification. No database."""

import json
from datetime import date
from decimal import Decimal

import pytest

from oraculoto.crawler.caixa import CaixaFormatError, next_draw_date, parse_draw
from oraculoto.crawler.protocol import Plan, ProtocolError, classify, is_retryable
from oraculoto.db.draws import DrawValidationError, Game, Prize, WinnerLocation, validate_draw
from oraculoto.importer.caixa_xlsx import parse_file
from tests.caixa_fixtures import FORBIDDEN_HTML, JSON, body, fake_body, not_drawn_body, payload

MEGASENA = Game(1, "megasena", "Mega-Sena", 6, 1, 60, 4, 6, 20)


def parse(contest: int, text: str | None = None):
    return parse_draw(MEGASENA, text if text is not None else body(contest), contest)


# ---------------------------------------------------------------- field map


def test_normal_contest_maps_every_field():
    d = parse(3072)
    assert d.contest_number == 3072
    assert d.draw_date == date(2026, 10, 20)
    assert d.balls == (2, 6, 9, 16, 31, 40)
    assert d.draw_order == (40, 6, 16, 31, 9, 2)
    assert d.is_special is False
    assert d.prizes == (
        Prize(6, 0, Decimal("0.00")),
        Prize(5, 140, Decimal("38295.72")),
        Prize(4, 9261, Decimal("954.26")),
    )
    assert d.total_collected == Decimal("134543238.00")
    assert d.rollover_amount == Decimal("187648868.43")
    assert d.next_estimated_prize == Decimal("200000000.00")
    assert d.special_accumulated == Decimal("106119095.67")
    assert d.notes is None
    assert d.locations == ()
    assert d.source == "api"
    validate_draw(MEGASENA, d)


def test_special_contest_with_online_and_city_winners():
    d = parse(2955)
    assert d.is_special is True
    assert d.prizes[0] == Prize(6, 6, Decimal("181892881.09"))
    assert d.total_collected == Decimal("3052431720.00")
    assert d.locations == (
        WinnerLocation(raw="CANAL ELETRONICO", is_online=True, winners=3),
        WinnerLocation(raw="PONTA PORA/MS", city="PONTA PORA", uf="MS", winners=1),
        WinnerLocation(raw="JOAO PESSOA/PB", city="JOAO PESSOA", uf="PB", winners=1),
        WinnerLocation(raw="FRANCO DA ROCHA/SP", city="FRANCO DA ROCHA", uf="SP", winners=1),
    )
    assert sum(loc.winners for loc in d.locations) == d.prizes[0].winners
    validate_draw(MEGASENA, d)


def test_oldest_contest_zero_means_unknown():
    d = parse(1)
    assert d.total_collected is None  # valorArrecadado 0.0
    assert d.next_estimated_prize is None  # valorEstimadoProximoConcurso 0.0
    assert d.rollover_amount == Decimal("1714650.23")
    assert d.special_accumulated == Decimal("0.00")  # a real zero
    assert next_draw_date(d.source_payload) is None  # dataProximoConcurso ""
    validate_draw(MEGASENA, d)


def test_nul_characters_are_stripped_from_the_payload():
    assert "\x00" in payload(3072)["nomeTimeCoracaoMesSorte"]
    d = parse(3072)
    assert d.source_payload["nomeTimeCoracaoMesSorte"] == ""
    assert "\\u0000" not in json.dumps(d.source_payload)
    assert d.source_payload["numero"] == 3072  # everything else kept


def test_next_draw_date_from_the_payload():
    assert next_draw_date(payload(3072)) == date(2026, 10, 22)
    assert next_draw_date(None) is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (38295.72, "38295.72"),
        (0.1 + 0.2, "0.30"),
        (954.255, "954.26"),
        (3052431720.0, "3052431720.00"),
        (5, "5.00"),
    ],
)
def test_money_is_rounded_once_to_cents(value, expected):
    d = parse(3073, fake_body(3073, valorAcumuladoProximoConcurso=value))
    assert d.rollover_amount == Decimal(expected)
    assert isinstance(d.rollover_amount, Decimal)


def test_notes_are_kept_and_stripped():
    assert parse(3073, fake_body(3073, observacao="  Sorteio adiado \x00")).notes == "Sorteio adiado"


# ---------------------------------------------------------------- refusals


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"numero": 3074}, "asked for #3073, got #3074"),
        ({"tipoJogo": "QUINA"}, "tipoJogo"),
        ({"indicadorConcursoEspecial": 3}, "indicadorConcursoEspecial"),
        ({"dataApuracao": "2026-10-22"}, "dd/mm/yyyy"),
        ({"dataApuracao": "31/02/2026"}, "not a date"),
        ({"listaDezenas": [2, 6, 9, 16, 31, 40]}, "listaDezenas"),
        ({"valorArrecadado": "134543238.0"}, "valorArrecadado is not a number"),
        ({"valorArrecadado": None}, "valorArrecadado is not a number"),
        (
            {
                "listaRateioPremio": [
                    {"descricaoFaixa": "5 acertos", "faixa": 1, "numeroDeGanhadores": 0, "valorPremio": 0}
                ]
            },
            "should be '6 acertos'",
        ),
        ({"listaMunicipioUFGanhadores": [{"municipio": "X", "uf": "SP", "ganhadores": "1"}]}, "ganhadores"),
    ],
)
def test_unexpected_shapes_are_refused(changes, message):
    with pytest.raises(CaixaFormatError, match=message):
        parse(3073, fake_body(3073, **changes))


def test_a_missing_field_is_refused():
    data = payload(3072)
    del data["valorAcumuladoConcursoEspecial"]
    with pytest.raises(CaixaFormatError, match="missing field valorAcumuladoConcursoEspecial"):
        parse(3072, json.dumps(data))


@pytest.mark.parametrize("text", ["not json", "[]", FORBIDDEN_HTML])
def test_a_body_that_isnt_a_json_object_is_refused(text):
    with pytest.raises(CaixaFormatError):
        parse(3072, text)


def test_draw_order_must_hold_the_same_balls():
    d = parse(3073, fake_body(3073, dezenasSorteadasOrdemSorteio=["40", "06", "16", "31", "09", "03"]))
    with pytest.raises(DrawValidationError, match="draw order"):
        validate_draw(MEGASENA, d)


# ---------------------------------------------------------------- same data from both sources


@pytest.mark.parametrize("contest", [1, 2955, 3072])
def test_api_and_xlsx_agree_except_the_api_only_fields(real_xlsx, contest):
    from_xlsx = {d.contest_number: d for d in parse_file(real_xlsx, MEGASENA)[0]}[contest]
    from_api = parse(contest)
    api_only = ("source", "draw_order", "is_special", "locations", "source_payload")
    for name in from_api.__dataclass_fields__:
        if name not in api_only:
            assert getattr(from_api, name) == getattr(from_xlsx, name), name
    # the xlsx has the same cities, without the winner counts
    assert [(loc.raw, loc.city, loc.uf, loc.is_online) for loc in from_api.locations] == [
        (loc.raw, loc.city, loc.uf, loc.is_online) for loc in from_xlsx.locations
    ]


# ---------------------------------------------------------------- protocol


@pytest.mark.parametrize(
    ("status", "content_type", "text", "expected"),
    [
        (200, JSON, body(3072), "found"),
        (500, JSON, not_drawn_body(), "not_drawn"),
        (404, JSON, '{"StatusCode":404}', "not_drawn"),
        (500, JSON, '{"message":"boom"}', "error"),
        (403, "text/html", FORBIDDEN_HTML, "blocked"),
        (429, "text/plain", "slow down", "blocked"),
        (200, "text/html", "<html>captcha</html>", "blocked"),
        (200, JSON, "[1, 2]", "error"),
        (200, JSON, "{}", "error"),
        (502, "text/html", "<html>bad gateway</html>", "error"),
        (None, None, None, "error"),
    ],
)
def test_classify(status, content_type, text, expected):
    assert classify(status, content_type, text) == expected


def test_retry_only_transport_and_real_server_errors():
    assert is_retryable(None, "error")
    assert is_retryable(503, "error")
    assert not is_retryable(500, "not_drawn")
    assert not is_retryable(403, "blocked")
    assert not is_retryable(200, "error")  # garbage won't improve by asking again


def test_plan_round_trip_and_validation():
    plan = Plan(game="megasena", kind="crawl", contests=[3070, 3071], gap_start=3072)
    assert Plan.from_json(plan.to_json()) == plan
    assert list(plan.gap())[:2] == [3072, 3073] and len(plan.gap()) == 50
    assert len(Plan(game="megasena", kind="backfill", contests=[1], cap=0).gap()) == 0
    for bad in [
        "nope",
        "[]",
        '{"game": "megasena", "kind": "xlsx_import"}',
        '{"game": "megasena", "kind": "crawl", "contests": [0]}',
        '{"game": "megasena", "kind": "crawl", "contests": [true]}',
        '{"game": "megasena", "kind": "crawl", "cap": -1}',
        '{"game": "megasena", "kind": "crawl", "surprise": 1}',
        '{"kind": "crawl"}',
    ]:
        with pytest.raises(ProtocolError):
            Plan.from_json(bad)
