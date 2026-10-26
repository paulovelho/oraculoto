"""The reference strategies on the real file reproduce docs/api.md §5, directly and through the API."""

import pytest
from fastapi.testclient import TestClient

from oraculoto.api.app import PREFIX, create_app
from oraculoto.api.deps import get_engine
from oraculoto.db.draws import get_game
from oraculoto.db.results import load_history
from oraculoto.guess import REGISTRY
from oraculoto.guess.backtest import backtest

MS = f"{PREFIX}/games/megasena"


@pytest.fixture(scope="module")
def history(imported):
    engine, _ = imported
    with engine.connect() as conn:
        game = get_game(conn, "megasena")
        return game, load_history(conn, game, 3072)


@pytest.fixture(scope="module")
def client(imported) -> TestClient:
    engine, _ = imported
    app = create_app()
    app.dependency_overrides[get_engine] = lambda: engine
    return TestClient(app, headers={"Authorization": "Bearer dev"})


def test_history(history):
    _, h = history
    assert len(h) == 3072 and [d.contest for d in h[:2]] == [1, 2]
    assert h[0].balls == (4, 5, 30, 33, 41, 52) and h[0].draw_order is None
    assert h[-1].balls == (2, 6, 9, 16, 31, 40)


# §5, over target contests #1001–#3072: average hits, and draws with 4 or more hits
@pytest.mark.parametrize(
    ("key", "average", "four_plus"),
    [("hot", 0.612, 0), ("hot_recent", 0.629, 0), ("overdue", 0.572, 1), ("repeat_last", 0.589, 1)],
)
def test_reference_table(history, key, average, four_plus):
    game, h = history
    f = REGISTRY[key]
    r = backtest(game, h, f, 6, f.resolve_params({}), 1001, 3072)
    assert r.draws == 2072
    assert round(r.average_hits, 3) == average
    assert sum(r.tiers.values()) == four_plus  # with k = 6, the tiers can't overlap
    assert abs(r.z_score(game)) < 2  # "all of them are within about 2 standard errors of random"


def test_backtest_endpoint(client):
    r = client.get(MS + "/backtest", params={"function": "hot_recent", "from": 2573, "to": 3072, "last": 50})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["function"] == {"key": "hot_recent", "version": 1, "ref": "hot_recent@1"}
    assert d["params"] == {"last": 50} and d["k"] == 6
    assert d["window"] == {"from": 2573, "to": 3072, "draws": 500}
    assert sum(x["draws"] for x in d["hits"]) == 500
    assert d["average_hits"] == round(sum(x["hits"] * x["draws"] for x in d["hits"]) / 500, 4)
    assert d["baseline"]["average_hits"] == 0.6 and d["baseline"]["standard_error"] == 0.03144
    assert [t["hits"] for t in d["tiers"]] == [6, 5, 4]
    assert d["tiers"][2]["expected"] == 0.2144  # 500 × P(exactly 4 of 6)


def test_backtest_defaults_to_the_last_100(client):
    d = client.get(MS + "/backtest", params={"function": "hot"}).json()["data"]
    assert d["window"] == {"from": 2973, "to": 3072, "draws": 100} and d["k"] == 6


def test_backtest_cap(client, monkeypatch):
    r = client.get(MS + "/backtest", params={"function": "hot", "from": 1, "to": 501})
    assert r.status_code == 400 and "at most 500" in r.json()["error"]["message"]
    monkeypatch.setenv("ORACULOTO_BACKTEST_MAX_CONTESTS", "1000")
    assert (
        client.get(MS + "/backtest", params={"function": "repeat_last", "from": 1, "to": 501}).status_code
        == 200
    )
