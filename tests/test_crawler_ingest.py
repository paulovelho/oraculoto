"""The server half of a run: `crawl-plan` and `ingest` (docs/crawler.md §3, §6, §7), on the test database."""

import io
import json
from datetime import date

import httpx2
import pytest
from sqlalchemy import select

from oraculoto import cli
from oraculoto.crawler.caixa import parse_draw
from oraculoto.crawler.ingest import ingest
from oraculoto.crawler.plan import crawl_plan
from oraculoto.crawler.protocol import Plan
from oraculoto.db.draws import save_draw
from oraculoto.db.schema import draw_balls, draws, sync_runs
from oraculoto.importer.caixa_xlsx import import_xlsx
from tests.caixa_fixtures import FORBIDDEN_HTML, JSON, body, fake_body, lines, not_drawn_body
from tests.conftest import TEST_DB
from tests.xlsx_builder import SAMPLE_ROWS, build_xlsx

NOT_DRAWN = not_drawn_body()


def crawl(top: int) -> Plan:
    return Plan(
        game="megasena", kind="crawl", contests=list(range(max(1, top - 2), top + 1)), gap_start=top + 1
    )


def store(engine, game, *contests: int) -> None:
    """Contests saved from the API, as a previous run would have."""
    with engine.begin() as conn:
        for n in contests:
            save_draw(conn, game, parse_draw(game, fake_body(n), n))


def stored(engine) -> dict[int, str]:
    with engine.connect() as conn:
        return dict(conn.execute(select(draws.c.contest_number, draws.c.source)).all())


def runs(engine) -> list[dict]:
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(select(sync_runs).order_by(sync_runs.c.id)).mappings()]


@pytest.fixture
def sample(clean_db, tmp_path):
    """Contests #1-#3 from the xlsx."""
    import_xlsx(clean_db, "megasena", build_xlsx(tmp_path / "s.xlsx", SAMPLE_ROWS))
    return clean_db


# ---------------------------------------------------------------- crawl-plan


def test_plan_for_an_empty_database(clean_db, megasena):
    with clean_db.connect() as conn:
        plan = crawl_plan(conn, megasena)
    assert plan == Plan(game="megasena", kind="crawl", contests=[], gap_start=1, cap=50)


def test_plan_refreshes_the_last_three(clean_db, megasena):
    store(clean_db, megasena, 3069, 3070, 3071)
    with clean_db.connect() as conn:
        plan = crawl_plan(conn, megasena)
    assert (plan.contests, plan.gap_start) == ([3069, 3070, 3071], 3072)


def test_plan_with_fewer_than_three_contests(sample, megasena):
    with sample.connect() as conn:
        assert crawl_plan(conn, megasena).contests == [1, 2, 3]


def test_backfill_plan_skips_contests_already_from_the_api(sample, megasena):
    with sample.begin() as conn:
        save_draw(conn, megasena, parse_draw(megasena, body(1), 1))
        everything = crawl_plan(conn, megasena, backfill=True)
        assert crawl_plan(conn, megasena, backfill=True, first=3, last=99).contests == [3]  # never past max
    assert everything == Plan(game="megasena", kind="backfill", contests=[2, 3], cap=0)


def test_backfill_plan_includes_holes(clean_db, megasena):
    store(clean_db, megasena, 3070, 3072)
    with clean_db.connect() as conn:
        assert crawl_plan(conn, megasena, backfill=True, first=3069).contests == [3069, 3071]


# ---------------------------------------------------------------- ingest


def test_found_contests_are_saved_and_the_gap_closes(clean_db, megasena):
    store(clean_db, megasena, 3069, 3070, 3071)
    report = ingest(
        clean_db,
        "megasena",
        lines(
            crawl(3071),
            *[(n, 200, fake_body(n)) for n in (3069, 3070, 3071)],
            (3072, 200, body(3072)),
            (3073, 500, NOT_DRAWN),
        ),
    )
    assert (report.status, report.inserted, report.unchanged, report.not_drawn) == ("ok", 1, 3, 3073)
    assert stored(clean_db)[3072] == "api"
    with clean_db.connect() as conn:
        draw_id = conn.execute(select(draws.c.id).where(draws.c.contest_number == 3072)).scalar()
        order = conn.execute(
            select(draw_balls.c.ball)
            .where(draw_balls.c.draw_id == draw_id)
            .order_by(draw_balls.c.draw_position)
        ).scalars()
        assert list(order) == [40, 6, 16, 31, 9, 2]
    [run] = runs(clean_db)
    assert (run["kind"], run["status"], run["draws_written"]) == ("crawl", "ok", 1)
    assert run["finished_at"] is not None and "#3073 not drawn yet" in run["message"]


def test_the_refresh_turns_xlsx_rows_into_api_rows(sample, megasena):
    report = ingest(sample, "megasena", lines(crawl(3), (1, 200, body(1)), (2, 500, NOT_DRAWN)))
    # #1 came back as the API's version; #2 "not drawn" although stored: Caixa is lying, so stop
    assert stored(sample) == {1: "api", 2: "xlsx", 3: "xlsx"}
    assert report.status == "error" and "#2 was planned as existing" in report.problem


def test_nothing_new(clean_db, megasena):
    store(clean_db, megasena, 3072)
    plan = Plan(game="megasena", kind="crawl", contests=[3072], gap_start=3073)
    raw = lines(plan, (3072, 200, fake_body(3072)), (3073, 500, NOT_DRAWN))
    report = ingest(clean_db, "megasena", raw, today=date(2026, 10, 23))
    assert (report.status, report.unchanged, report.draws_written) == ("nothing_new", 1, 0)


def test_late_prize_data_is_an_update(clean_db, megasena):
    store(clean_db, megasena, 3072)
    plan = Plan(game="megasena", kind="crawl", contests=[3072], gap_start=3073)
    later = fake_body(3072, observacao="rateio corrigido")
    report = ingest(clean_db, "megasena", lines(plan, (3072, 200, later), (3073, 500, NOT_DRAWN)))
    assert (report.status, report.updated) == ("ok", 1)


def test_blocked_writes_nothing_and_says_so(clean_db, megasena):
    report = ingest(clean_db, "megasena", lines(crawl(0), (1, 403, FORBIDDEN_HTML)))
    assert report.status == "error" and "blocked by Caixa on #1 (HTTP 403)" in report.problem
    assert stored(clean_db) == {}
    assert runs(clean_db)[0]["status"] == "error"


def test_saved_contests_survive_a_later_failure(clean_db, megasena):
    report = ingest(
        clean_db,
        "megasena",
        lines(crawl(0), (1, 200, fake_body(1)), (2, 200, fake_body(2)), (3, 403, FORBIDDEN_HTML)),
    )
    assert stored(clean_db) == {1: "api", 2: "api"}
    assert (report.status, report.draws_written) == ("error", 2)
    assert runs(clean_db)[0]["draws_written"] == 2


def test_a_caixa_error_is_reported(clean_db, megasena):
    report = ingest(clean_db, "megasena", lines(crawl(0), (1, 502, "<html>bad gateway</html>")))
    assert report.status == "error" and "Caixa error on #1: HTTP 502" in report.problem


def test_a_response_that_doesnt_parse_stops_the_run(clean_db, megasena):
    report = ingest(clean_db, "megasena", lines(crawl(0), (1, 200, fake_body(2)), (2, 200, fake_body(2))))
    assert report.status == "error" and "asked for #1, got #2" in report.problem
    assert stored(clean_db) == {}


def test_a_draw_that_breaks_the_game_rules_stops_the_run(clean_db, megasena):
    bad = fake_body(1, listaDezenas=["02", "06", "09", "16", "31", "61"])
    report = ingest(clean_db, "megasena", lines(crawl(0), (1, 200, bad)))
    assert report.status == "error" and "out of range" in report.problem


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ([], "no input"),
        (["{not json"], "line 1 is not JSON"),
        (['{"type": "end", "requests": 0}'], "expected the plan line first"),
        (['{"type": "plan", "plan": {"game": "megasena"}}'], "not a plan"),
        (['{"type": "plan", "plan": {"game": "quina", "kind": "crawl"}}'], "not 'megasena'"),
        (lines(crawl(0))[:1] + ['{"type": "response", "contest": 1}'], "http_status, content_type, body"),
        (lines(crawl(0))[:1] + ['{"type": "response", "contest": "1"}'], "bad response line: contest"),
        (lines(crawl(0), (99, 500, NOT_DRAWN)), "#99 is not in the plan"),
        (lines(crawl(0), (1, 500, NOT_DRAWN)) + ['{"type": "end", "requests": 1}'], "after the end line"),
        (lines(crawl(0), (1, 200, fake_body(1)))[:-1], "the input stopped before the fetcher's end line"),
    ],
)
def test_malformed_input_is_an_error(clean_db, raw, message):
    report = ingest(clean_db, "megasena", raw)
    assert report.status == "error" and message in report.problem
    assert runs(clean_db)[0]["status"] == "error"


def test_a_cut_off_run_keeps_what_it_saved(clean_db):
    raw = lines(crawl(0), (1, 200, fake_body(1)))[:-1]  # no end line
    report = ingest(clean_db, "megasena", raw)
    assert stored(clean_db) == {1: "api"} and report.status == "error"


def test_backfill_run_is_logged_as_backfill(sample):
    plan = Plan(game="megasena", kind="backfill", contests=[1], cap=0)
    report = ingest(sample, "megasena", lines(plan, (1, 200, body(1))))
    assert (report.status, report.updated) == ("ok", 1)
    assert runs(sample)[-1]["kind"] == "backfill"


def test_unknown_game_raises_before_writing(clean_db):
    with pytest.raises(LookupError):
        ingest(clean_db, "quina", lines(crawl(0)))
    assert runs(clean_db) == []


# ---------------------------------------------------------------- staleness alarm (§5)


@pytest.mark.parametrize(
    ("today", "status"), [(date(2026, 10, 24), "nothing_new"), (date(2026, 10, 25), "error")]
)
def test_stale_when_the_announced_draw_is_more_than_two_days_late(clean_db, megasena, today, status):
    with clean_db.begin() as conn:
        save_draw(conn, megasena, parse_draw(megasena, body(3072), 3072))  # next draw announced for 22/10
    plan = Plan(game="megasena", kind="crawl", contests=[], gap_start=3073)
    report = ingest(clean_db, "megasena", lines(plan, (3073, 500, NOT_DRAWN)), today=today)
    assert report.status == status
    if status == "error":
        assert report.problem == "stale: #3073 was due on 2026-10-22, nothing new since"


def test_no_staleness_check_on_xlsx_rows(sample):
    plan = Plan(game="megasena", kind="crawl", contests=[], gap_start=4)
    report = ingest(sample, "megasena", lines(plan, (4, 500, NOT_DRAWN)), today=date(2030, 1, 1))
    assert report.status == "nothing_new"


# ---------------------------------------------------------------- the local pipe, through the CLI


def test_crawl_plan_fetch_ingest_pipe(clean_db, megasena, monkeypatch, capsys):
    """`crawl-plan | fetch --plan - | ingest`, with a fake Caixa."""
    monkeypatch.setenv("DB_NAME", TEST_DB)
    store(clean_db, megasena, 3071)

    assert cli.main(["crawl-plan"]) == 0
    plan_json = capsys.readouterr().out
    assert json.loads(plan_json) == {
        "game": "megasena",
        "kind": "crawl",
        "contests": [3069, 3070, 3071],
        "gap_start": 3072,
        "cap": 50,
    }

    def caixa(request: httpx2.Request) -> httpx2.Response:
        n = int(request.url.path.rsplit("/", 1)[1])
        if n <= 3072:
            return httpx2.Response(200, text=fake_body(n), headers={"content-type": JSON})
        return httpx2.Response(500, text=NOT_DRAWN, headers={"content-type": JSON})

    monkeypatch.setattr(
        "oraculoto.crawler.fetch.make_client", lambda: httpx2.Client(transport=httpx2.MockTransport(caixa))
    )
    monkeypatch.setattr("oraculoto.crawler.fetch.time.sleep", lambda _s: None)
    monkeypatch.setattr("sys.stdin", io.StringIO(plan_json))
    assert cli.main(["fetch", "--plan", "-"]) == 0
    fetched = capsys.readouterr().out
    assert len(fetched.splitlines()) == 7  # plan, 3069-3073, end

    monkeypatch.setattr("sys.stdin", io.StringIO(fetched))
    assert cli.main(["ingest"]) == 0
    assert capsys.readouterr().out.startswith(
        "ok: megasena crawl: 5 responses; inserted 3, updated 0, unchanged 1"
    )
    assert stored(clean_db) == {n: "api" for n in (3069, 3070, 3071, 3072)}  # the refresh fills holes too


def test_ingest_exits_1_on_error(clean_db, monkeypatch, capsys):
    monkeypatch.setenv("DB_NAME", TEST_DB)
    monkeypatch.setattr("sys.stdin", io.StringIO("\n".join(lines(crawl(0), (1, 403, FORBIDDEN_HTML)))))
    assert cli.main(["ingest"]) == 1
    assert "error: " in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["fetch"],
        ["fetch", "--plan", "-", "--contest", "3"],
        ["fetch", "--contest", "3", "--backfill"],
        ["fetch", "--remote", "dh", "--from", "3"],
        ["crawl-plan", "--to", "9"],
    ],
)
def test_bad_option_combinations(argv, capsys):
    assert cli.main(argv) == 2
    assert capsys.readouterr().err


def test_ssh_command_quotes_the_arguments():
    assert cli._ssh("dh", "~/oraculoto/.venv/bin/oraculoto", "ingest", "--game", "mega sena") == [
        "ssh",
        "dh",
        "~/oraculoto/.venv/bin/oraculoto ingest --game 'mega sena'",
    ]
