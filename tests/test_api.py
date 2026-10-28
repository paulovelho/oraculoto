"""The API on the 3-contest sample (tests/xlsx_builder.py): envelope, auth, draws, validation.

The stats against the real file are in test_api_stats.py.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert

from oraculoto.api.app import PREFIX, create_app
from oraculoto.api.deps import get_engine
from oraculoto.config import DbSettings, db_settings
from oraculoto.db import make_engine
from oraculoto.db.draws import save_draw
from oraculoto.db.schema import sync_runs
from oraculoto.importer.caixa_xlsx import import_xlsx, parse_file
from tests.auth_tokens import MEMBER, bearer, invite
from tests.conftest import TEST_DB
from tests.xlsx_builder import SAMPLE_ROWS, build_xlsx


def api_client(engine, email: str | None = MEMBER) -> TestClient:
    """A client logged in as an invited email, or with no token at all (email=None)."""
    app = create_app()
    app.dependency_overrides[get_engine] = lambda: engine
    if email is None:
        return TestClient(app)
    invite(engine, email)
    return TestClient(app, headers=bearer(email))


@pytest.fixture
def sample(clean_db, tmp_path):
    import_xlsx(clean_db, "megasena", build_xlsx(tmp_path / "s.xlsx", SAMPLE_ROWS))
    return clean_db


@pytest.fixture
def client(sample) -> TestClient:
    return api_client(sample)


def get(client: TestClient, path: str, status: int = 200, **params):
    r = client.get(PREFIX + path, params=params)
    assert r.status_code == status, r.text
    body = r.json()
    assert body["success"] is (status < 400)
    return body["data"] if status < 400 else body["error"]


# ---------------------------------------------------------------- service and auth


def test_health_needs_no_token(client):
    r = client.get(f"{PREFIX}/health")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["database"] == "ok"
    [game] = data["games"]
    assert (game["game"], game["latest_contest"], game["latest_date"]) == ("megasena", 3, "1996-03-25")
    # an xlsx import isn't a crawl: the home fetcher has never run
    assert (game["last_crawl"], game["stale"]) == (None, True)


@pytest.mark.parametrize(("age", "stale"), [(timedelta(hours=1), False), (timedelta(days=2, hours=1), True)])
def test_health_reports_the_last_successful_crawl(sample, age, stale):
    finished = datetime.now(UTC).replace(tzinfo=None, microsecond=0) - age
    with sample.begin() as conn:
        conn.execute(
            insert(sync_runs),
            [
                {
                    "game_id": 1,
                    "kind": "crawl",
                    "status": "nothing_new",
                    "started_at": finished,
                    "finished_at": finished,
                },
                # later, but failed: doesn't count
                {
                    "game_id": 1,
                    "kind": "crawl",
                    "status": "error",
                    "started_at": finished,
                    "finished_at": finished + age,
                },
            ],
        )
    [game] = api_client(sample).get(f"{PREFIX}/health").json()["data"]["games"]
    assert game["last_crawl"] == finished.isoformat() + "Z"
    assert game["stale"] is stale


def test_health_reports_a_dead_database():
    s = db_settings(name=TEST_DB)
    dead = make_engine(DbSettings(host=s.host, port=1, name=s.name, user=s.user, password=s.password))
    r = api_client(dead, None).get(f"{PREFIX}/health")
    assert r.status_code == 503
    assert r.json() == {
        "success": False,
        "error": {"code": "db_unavailable", "message": "database unavailable"},
    }


def protected_routes() -> list[tuple[str, str]]:
    """(method, path) of every route but /health, with sample values in the path."""
    routes = []
    for path, methods in create_app().openapi()["paths"].items():
        if path == f"{PREFIX}/health":
            continue
        path = path.replace("{game}", "megasena").replace("{contest}", "1").replace("{ticket_id}", "1")
        routes += [(method.upper(), path) for method in methods]
    return routes


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": ""},
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer "},
        {"Authorization": "Bearer dev"},
        {"Authorization": "Bearer a.b.c"},
    ],
)
def test_every_route_but_health_needs_a_token(sample, headers):
    client = api_client(sample, None)
    routes = protected_routes()
    assert len(routes) == 18
    for method, path in routes:
        r = client.request(method, path, params={"balls": "10"}, headers=headers, json={})
        assert r.status_code == 401, (method, path)
        assert r.json()["error"]["code"] == "unauthorized"


def test_dev_key_refuses_to_start_outside_dev(monkeypatch):
    monkeypatch.setenv("ORACULOTO_ENV", "production")
    with pytest.raises(RuntimeError, match="ORACULOTO_ENV='production'"):
        create_app()


def test_firebase_needs_a_project_id(monkeypatch):
    monkeypatch.setenv("ORACULOTO_AUTH", "firebase")
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    with pytest.raises(RuntimeError, match="FIREBASE_PROJECT_ID"):
        create_app()
    monkeypatch.setenv("ORACULOTO_AUTH", "magic")
    with pytest.raises(RuntimeError, match="ORACULOTO_AUTH='magic'"):
        create_app()


def test_unknown_path_and_wrong_method_use_the_envelope(client):
    r = client.get(f"{PREFIX}/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = client.post(f"{PREFIX}/games")
    assert r.status_code == 405 and r.json()["error"]["code"] == "method_not_allowed"


# ---------------------------------------------------------------- games and draws


def test_games(client):
    assert get(client, "/games") == [
        {
            "slug": "megasena",
            "name": "Mega-Sena",
            "balls_drawn": 6,
            "ball_min": 1,
            "ball_max": 60,
            "prize_tiers": [6, 5, 4],
            "bet_min_numbers": 6,
            "bet_max_numbers": 20,
        }
    ]


def test_unknown_game_is_404(client):
    assert get(client, "/games/quina/draws", 404)["code"] == "not_found"


def test_one_contest(client):
    d = get(client, "/games/megasena/draws/2")
    assert d == {
        "contest": 2,
        "date": "1996-03-18",
        "balls": [9, 37, 39, 41, 43, 49],
        "draw_order": None,
        "prizes": [
            {"hits": 6, "winners": 2, "prize_per_winner": "2000000.00"},
            {"hits": 5, "winners": 10, "prize_per_winner": "40000.00"},
            {"hits": 4, "winners": 1000, "prize_per_winner": "500.00"},
        ],
        "winner_locations": [
            {"city": "SÃO PAULO", "uf": "SP", "is_online": False, "winners": None, "raw": "SÃO PAULO/SP"},
            {"city": None, "uf": None, "is_online": True, "winners": None, "raw": "Canal Eletrônico"},
        ],
        "total_collected": "50000000.00",
        "rollover_amount": "0.00",
        "next_estimated_prize": "3000000.00",
        "special_accumulated": "0.00",
        "notes": "Estimativa de prêmio para o próximo concurso",
        "is_special": None,
        "source": "xlsx",
    }


def test_unknown_values_are_null(client):
    d = get(client, "/games/megasena/draws/1")
    assert d["total_collected"] is None and d["next_estimated_prize"] is None and d["notes"] is None


def test_draw_order_when_known(sample, megasena, tmp_path, client):
    contests, _ = parse_file(build_xlsx(tmp_path / "s.xlsx", SAMPLE_ROWS), megasena)
    with sample.begin() as c:
        save_draw(c, megasena, replace(contests[0], source="api", draw_order=(41, 4, 52, 5, 33, 30)))
    d = get(client, "/games/megasena/draws/1")
    assert d["balls"] == [4, 5, 30, 33, 41, 52]
    assert d["draw_order"] == [41, 4, 52, 5, 33, 30]


def test_missing_contest(client):
    assert get(client, "/games/megasena/draws/99", 404)["code"] == "not_found"
    assert get(client, "/games/megasena/draws/abc", 400)["code"] == "invalid_input"
    assert get(client, "/games/megasena/draws/0", 400)["code"] == "invalid_input"


def test_latest(client):
    assert get(client, "/games/megasena/draws/latest")["contest"] == 3


def test_latest_without_draws(clean_db):
    r = api_client(clean_db).get(f"{PREFIX}/games/megasena/draws/latest")
    assert r.status_code == 404


def contests(page: dict) -> list[int]:
    return [d["contest"] for d in page["items"]]


def test_draws_newest_first_and_paged(client):
    first = get(client, "/games/megasena/draws")
    assert (contests(first), first["page"], first["limit"], first["total"]) == ([3, 2, 1], 1, 20, 3)
    second = get(client, "/games/megasena/draws", page=2, limit=2)
    assert (contests(second), second["total"]) == ([1], 3)
    assert get(client, "/games/megasena/draws", page=3, limit=2)["items"] == []


def test_draws_filters(client):
    assert contests(get(client, "/games/megasena/draws", **{"from": 2})) == [3, 2]
    assert contests(get(client, "/games/megasena/draws", to=2)) == [2, 1]
    assert contests(get(client, "/games/megasena/draws", **{"from": 2, "to": 2})) == [2]


def test_draws_by_date(client):
    by_date = "/games/megasena/draws/by-date"
    assert contests(get(client, by_date)) == [3, 2, 1]
    assert contests(get(client, by_date, **{"from": "1996-03-18", "to": "1996-03-18"})) == [2]
    assert contests(get(client, by_date, to="1996-03-20")) == [2, 1]
    page = get(client, by_date, **{"from": "1996-03-12"}, limit=1, page=2)
    assert (contests(page), page["total"]) == ([2], 2)  # #1 (1996-03-11) is before from


@pytest.mark.parametrize(
    "params",
    [{"limit": 101}, {"limit": 0}, {"page": 0}, {"from": 3, "to": 2}, {"from": "1996-03-18"}],
)
def test_draws_bad_input(client, params):
    assert get(client, "/games/megasena/draws", 400, **params)["code"] == "invalid_input"


@pytest.mark.parametrize(
    "params",
    [{"from": "1996-03-20", "to": "1996-03-19"}, {"from": "20/03/1996"}, {"from": 2}, {"limit": 101}],
)
def test_draws_by_date_bad_input(client, params):
    assert get(client, "/games/megasena/draws/by-date", 400, **params)["code"] == "invalid_input"


# ---------------------------------------------------------------- stats on the sample


def test_frequency_includes_zeros(client):
    d = get(client, "/games/megasena/stats/frequency")
    assert d["window"] == {"from": 1, "to": 3, "draws": 3}
    assert d["expected"] == 0.3
    assert len(d["items"]) == 60
    assert d["items"][:2] == [{"ball": 30, "times": 2}, {"ball": 41, "times": 2}]
    assert d["items"][-1] == {"ball": 60, "times": 0}


def test_window_last_n_and_from_to(client):
    assert get(client, "/games/megasena/stats/frequency", last=2)["window"] == {
        "from": 2,
        "to": 3,
        "draws": 2,
    }
    assert get(client, "/games/megasena/stats/frequency", last=50)["window"] == {
        "from": 1,
        "to": 3,
        "draws": 3,
    }
    w = get(client, "/games/megasena/stats/frequency", **{"from": 2, "to": 2})["window"]
    assert w == {"from": 2, "to": 2, "draws": 1}


def test_empty_window(client):
    d = get(client, "/games/megasena/stats/frequency", **{"from": 100})
    assert d["window"] == {"from": None, "to": None, "draws": 0}
    assert {i["times"] for i in d["items"]} == {0}
    gaps = get(client, "/games/megasena/stats/gaps", **{"from": 100})["items"]
    assert gaps[0] == {"ball": 1, "last_seen": None, "current_gap": 0, "longest_gap": None}


@pytest.mark.parametrize("params", [{"last": 5, "from": 1}, {"last": 0}, {"from": 3, "to": 1}])
def test_bad_window(client, params):
    assert get(client, "/games/megasena/stats/gaps", 400, **params)["code"] == "invalid_input"


def test_together(client):
    d = get(client, "/games/megasena/stats/together", balls="41")
    assert d["balls"] == [41] and d["jackpot"] is False
    assert d["last"] == {"contest": 2, "date": "1996-03-18"}
    assert [i["contest"] for i in d["items"]] == [2, 1] and d["total"] == 2
    assert d["expected"] == 0.3  # 3 draws x 6/60

    j = get(client, "/games/megasena/stats/together", balls="41", jackpot="true")
    assert [i["contest"] for i in j["items"]] == [2] and j["expected"] == 0.1  # 1 jackpot draw x 6/60

    none = get(client, "/games/megasena/stats/together", balls="41,10")
    assert (none["last"], none["items"], none["total"]) == (None, [], 0)

    paged = get(client, "/games/megasena/stats/together", balls="41", limit=1, page=2)
    assert ([i["contest"] for i in paged["items"]], paged["total"]) == ([1], 2)


@pytest.mark.parametrize("balls", ["", "a", "0", "61", "4,4", "1,2,3,4,5,6,7", "1;2"])
def test_together_bad_balls(client, balls):
    assert get(client, "/games/megasena/stats/together", 400, balls=balls)["code"] == "invalid_input"


def test_together_needs_balls(client):
    assert get(client, "/games/megasena/stats/together", 400)["code"] == "invalid_input"


def test_pairs_and_triples(client):
    pairs = get(client, "/games/megasena/stats/pairs", top=2)
    assert pairs["size"] == 2 and pairs["items"] == [
        {"balls": [4, 5], "times": 1},
        {"balls": [4, 30], "times": 1},
    ]
    assert pairs["expected"] == round(3 * 15 / 1770, 2)
    triples = get(client, "/games/megasena/stats/pairs", size=3, top=1)
    assert triples["items"] == [{"balls": [4, 5, 30], "times": 1}]
    for bad in ({"size": 4}, {"size": 1}, {"top": 0}, {"top": 101}):
        assert get(client, "/games/megasena/stats/pairs", 400, **bad)["code"] == "invalid_input"


def test_gaps(client):
    d = get(client, "/games/megasena/stats/gaps")
    assert d["expected_gap"] == 9.0
    by_ball = {g["ball"]: g for g in d["items"]}
    assert by_ball[41] == {"ball": 41, "last_seen": 2, "current_gap": 1, "longest_gap": 0}
    assert by_ball[30] == {"ball": 30, "last_seen": 3, "current_gap": 0, "longest_gap": 1}
    assert by_ball[1] == {"ball": 1, "last_seen": None, "current_gap": 3, "longest_gap": None}
    assert d["items"][0]["current_gap"] == 3  # never drawn first

    w = {g["ball"]: g for g in get(client, "/games/megasena/stats/gaps", last=2)["items"]}
    assert w[41] == {"ball": 41, "last_seen": 2, "current_gap": 1, "longest_gap": None}
    assert w[4]["current_gap"] == 2 and w[4]["last_seen"] is None


# ---------------------------------------------------------------- guess functions and backtests


def test_functions(client):
    fns = {f["key"]: f for f in get(client, "/functions")}
    assert list(fns) == ["hot", "hot_recent", "overdue", "repeat_last"]
    assert fns["hot_recent"]["ref"] == "hot_recent@1"
    assert fns["hot_recent"]["params"] == [
        {
            "name": "last",
            "type": "int",
            "default": 200,
            "min": 1,
            "max": None,
            "description": "how many of the latest draws to count",
        }
    ]


def test_backtest_on_the_sample(client):
    d = get(client, "/games/megasena/backtest", function="repeat_last", k=7)
    assert d["window"] == {"from": 1, "to": 3, "draws": 3} and d["k"] == 7
    assert len(d["hits"]) == 7  # 0 to 6 hits
    assert d["baseline"]["average_hits"] == 0.7
    assert get(client, "/games/megasena/backtest", function="hot", **{"from": 50})["window"] == {
        "from": None,
        "to": None,
        "draws": 0,
    }


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"function": "nope"}, "unknown 'nope'"),
        ({"function": "hot", "k": 5}, "k: must be 6-20"),
        ({"function": "hot", "k": 21}, "k: must be 6-20"),
        ({"function": "hot", "from": 3, "to": 2}, "is after"),
        ({"function": "hot", "last": 5}, "hot has no parameter 'last'"),
        ({"function": "hot_recent", "last": 0}, "last: must be >= 1"),
        ({"function": "hot_recent", "last": "x"}, "last: expected int"),
        ({"function": "hot_recent", "last": [5, 6]}, "more than once"),
    ],
)
def test_backtest_bad_input(client, params, message):
    err = get(client, "/games/megasena/backtest", 400, **params)
    assert err["code"] == "invalid_input" and message in err["message"]


def test_backtest_needs_a_function(client):
    assert get(client, "/games/megasena/backtest", 400)["code"] == "invalid_input"
