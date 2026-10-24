"""The API on the real file: the values of docs/database.md §6 and §7, as the endpoints return them."""

import pytest
from fastapi.testclient import TestClient

from oraculoto.api.app import PREFIX, create_app
from oraculoto.api.deps import get_engine

MS = f"{PREFIX}/games/megasena"


@pytest.fixture(scope="module")
def client(imported) -> TestClient:
    engine, _ = imported
    app = create_app()
    app.dependency_overrides[get_engine] = lambda: engine
    return TestClient(app, headers={"Authorization": "Bearer dev"})


def data(client: TestClient, path: str, **params):
    r = client.get(MS + path, params=params)
    assert r.status_code == 200, r.text
    return r.json()["data"]


FULL = {"from": 1, "to": 3072, "draws": 3072}


def test_frequency(client):
    d = data(client, "/stats/frequency")
    assert d["window"] == FULL and d["expected"] == 307.2
    pairs = [(i["ball"], i["times"]) for i in d["items"]]
    assert pairs[:3] == [(10, 359), (53, 350), (5, 335)]
    assert pairs[-3:] == [(55, 264), (21, 261), (26, 250)]


def test_frequency_last_100(client):
    d = data(client, "/stats/frequency", last=100)
    assert d["window"] == {"from": 2973, "to": 3072, "draws": 100}
    assert d["expected"] == 10.0
    assert sum(i["times"] for i in d["items"]) == 600 and len(d["items"]) == 60


def test_together(client):
    d = data(client, "/stats/together", balls="53,10")
    assert d["balls"] == [10, 53] and d["total"] == 38
    assert d["last"] == {"contest": 3065, "date": "2026-10-01"}
    assert d["expected"] == 26.03  # "about 26 expected by chance"
    assert len(d["items"]) == 20 and d["items"][0] == d["last"]


def test_together_with_jackpot(client):
    assert data(client, "/stats/together", balls="10,53", jackpot="true")["last"] == {
        "contest": 3043,
        "date": "2026-08-11",
    }
    assert data(client, "/stats/together", balls="26", jackpot="true")["last"] == {
        "contest": 3015,
        "date": "2026-06-06",
    }


def test_pairs_and_triples(client):
    pairs = data(client, "/stats/pairs", top=3)
    assert [(tuple(i["balls"]), i["times"]) for i in pairs["items"]] == [
        ((5, 27), 43),
        ((4, 52), 42),
        ((23, 53), 42),
    ]
    assert pairs["expected"] == 26.03
    assert len(data(client, "/stats/pairs")["items"]) == 20

    triples = data(client, "/stats/pairs", size=3, top=3)
    assert [(tuple(i["balls"]), i["times"]) for i in triples["items"]] == [
        ((4, 17, 52), 8),
        ((4, 27, 52), 8),
        ((4, 28, 30), 8),
    ]
    assert triples["expected"] == 1.8


def test_gaps(client):
    d = data(client, "/stats/gaps")
    assert d["window"] == FULL
    assert [(g["ball"], g["last_seen"], g["current_gap"]) for g in d["items"][:3]] == [
        (34, 3027, 45),
        (32, 3031, 41),
        (59, 3035, 37),
    ]
    longest = sorted(d["items"], key=lambda g: -g["longest_gap"])[:3]
    assert [(g["ball"], g["longest_gap"]) for g in longest] == [(42, 108), (26, 88), (19, 82)]


def test_contest_3072(client):
    d = data(client, "/draws/3072")
    assert d["balls"] == [2, 6, 9, 16, 31, 40] and d["date"] == "2026-10-20"
    assert d["prizes"] == [
        {"hits": 6, "winners": 0, "prize_per_winner": "0.00"},
        {"hits": 5, "winners": 140, "prize_per_winner": "38295.72"},
        {"hits": 4, "winners": 9261, "prize_per_winner": "954.26"},
    ]
    assert (
        d["rollover_amount"],
        d["total_collected"],
        d["next_estimated_prize"],
        d["special_accumulated"],
    ) == (
        "187648868.43",
        "134543238.00",
        "200000000.00",
        "106119095.67",
    )
    assert data(client, "/draws/latest") == d


def test_contest_1(client):
    d = data(client, "/draws/1")
    assert d["balls"] == [4, 5, 30, 33, 41, 52]
    assert d["rollover_amount"] == "1714650.23" and d["total_collected"] is None
    assert [(p["winners"], p["prize_per_winner"]) for p in d["prizes"]] == [
        (0, "0.00"),
        (17, "39158.92"),
        (2016, "330.21"),
    ]


def test_draws_page(client):
    d = data(client, "/draws", limit=100, page=2)
    assert d["total"] == 3072 and [x["contest"] for x in d["items"]][:2] == [2972, 2971]
    assert len(d["items"]) == 100
    by_date = data(client, "/draws/by-date", **{"from": "2026-01-01", "to": "2026-01-01"})
    assert [x["contest"] for x in by_date["items"]] == [2955]  # Mega da Virada 2025
