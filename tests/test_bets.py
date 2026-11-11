"""Oraculoto's own bet (docs/api.md §11): the `bet` command, its rules and the read endpoints."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from oraculoto import cli
from oraculoto.bets import BetError, place_bet
from oraculoto.crawler.caixa import parse_draw
from oraculoto.db.draws import save_draw
from oraculoto.db.schema import draws, oraculoto_bets
from oraculoto.guess.base import PastDraw
from oraculoto.guess.oraculoto import ORACULOTO
from oraculoto.importer.caixa_xlsx import import_xlsx
from tests.caixa_fixtures import fake_body
from tests.conftest import TEST_DB
from tests.test_api import api_client, get
from tests.xlsx_builder import SAMPLE_ROWS, build_xlsx

# fake_body() announces the next draw for 2026-10-22; bets close at 19:00 Brasília (22:00 UTC).
BEFORE = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
LAST_MINUTE = datetime(2026, 10, 22, 21, 59, tzinfo=UTC)
CLOSED = datetime(2026, 10, 22, 22, 0, tzinfo=UTC)


def store(engine, game, *contests: int, **changes) -> None:
    with engine.begin() as conn:
        for n in contests:
            save_draw(conn, game, parse_draw(game, fake_body(n, **changes), n))


def bet(engine, game, k=None, now=BEFORE):
    with engine.connect() as conn:
        return place_bet(conn, game, k, now)


def bet_count(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(oraculoto_bets)).scalar_one()


@pytest.fixture
def crawled(clean_db, megasena):
    store(clean_db, megasena, 3071, 3072)
    return clean_db


def test_bets_on_the_next_contest(crawled, megasena):
    out = bet(crawled, megasena)
    assert out.result == "placed"
    assert out.bet.contest == 3073
    assert len(out.bet.numbers) == 6 and list(out.bet.numbers) == sorted(out.bet.numbers)
    assert out.bet.source == "guess_oraculoto@3"
    assert f"{out.closes_at:%Y-%m-%d %H:%M}" == "2026-10-22 19:00"


def test_a_second_run_changes_nothing(crawled, megasena):
    first = bet(crawled, megasena).bet
    again = bet(crawled, megasena, now=CLOSED)  # even after the close: it only reads
    assert again.result == "already_placed" and again.bet == first
    assert bet_count(crawled) == 1


def test_a_different_k_on_an_existing_bet_is_refused(crawled, megasena):
    bet(crawled, megasena)
    with pytest.raises(BetError, match="never change"):
        bet(crawled, megasena, k=8)
    assert bet(crawled, megasena, k=6).result == "already_placed"


def test_more_numbers_when_asked(crawled, megasena):
    assert len(bet(crawled, megasena, k=8).bet.numbers) == 8


@pytest.mark.parametrize("k", [5, 21])
def test_k_outside_the_bet_sizes(crawled, megasena, k):
    with pytest.raises(BetError, match="k must be 6-20"):
        bet(crawled, megasena, k=k)
    assert bet_count(crawled) == 0


def test_last_minute_is_still_in_time(crawled, megasena):
    assert bet(crawled, megasena, now=LAST_MINUTE).result == "placed"


def test_too_late_writes_nothing(crawled, megasena):
    with pytest.raises(BetError, match="too late for #3073"):
        bet(crawled, megasena, now=CLOSED)
    assert bet_count(crawled) == 0


def test_no_announced_date_no_bet(clean_db, megasena, tmp_path):
    import_xlsx(clean_db, "megasena", build_xlsx(tmp_path / "s.xlsx", SAMPLE_ROWS))
    with pytest.raises(BetError, match="can't tell when #4 is drawn"):
        bet(clean_db, megasena)


def test_no_draws_no_bet(clean_db, megasena):
    with pytest.raises(BetError, match="no Mega-Sena contests"):
        bet(clean_db, megasena)


def test_the_same_history_gives_the_same_bet(megasena):
    history = [PastDraw(n, BEFORE.date(), (1, 2, 3, 4, 5, 6), None) for n in range(1, 11)]
    assert ORACULOTO.guess(megasena, history, 6, {}) == ORACULOTO.guess(megasena, history, 6, {})


# ---------------------------------------------------------------- command line


def test_bet_command(crawled, monkeypatch, capsys):
    monkeypatch.setenv("DB_NAME", TEST_DB)
    monkeypatch.setattr("oraculoto.bets.datetime", _frozen(BEFORE))
    assert cli.main(["bet"]) == 0
    assert capsys.readouterr().out.startswith("placed: megasena #3073: ")
    assert cli.main(["bet"]) == 0
    assert capsys.readouterr().out.startswith("already_placed: megasena #3073: ")
    assert cli.main(["bet", "--k", "9"]) == 1
    assert "bets never change" in capsys.readouterr().err


def _frozen(at: datetime):
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return at.astimezone(tz)

    return Frozen


# ---------------------------------------------------------------- API


def test_pending_then_scored(crawled, megasena):
    placed = bet(crawled, megasena).bet
    client = api_client(crawled)

    page = get(client, "/games/megasena/oraculoto")
    assert page["total"] == 1
    (item,) = page["items"]
    assert item["contest"] == 3073 and item["status"] == "pending" and item["hits"] is None
    assert item["numbers"] == list(placed.numbers) and item["source"] == "guess_oraculoto@3"
    assert item["date"] == "2026-10-22"  # announced with #3072

    drawn = list(placed.numbers[:4]) + [n for n in range(1, 61) if n not in placed.numbers][:2]
    balls = [f"{n:02d}" for n in drawn]
    store(crawled, megasena, 3073, listaDezenas=balls, dezenasSorteadasOrdemSorteio=balls)
    item = get(client, "/games/megasena/oraculoto/3073")
    assert item["status"] == "drawn" and item["hits"] == 4
    assert item["date"] == get(client, "/games/megasena/draws/3073")["date"]  # now the real one
    assert item["matched"] == sorted(placed.numbers[:4])
    assert [p["hits"] for p in item["prizes"]] == [4]


def test_no_bet_on_that_contest(crawled):
    assert get(api_client(crawled), "/games/megasena/oraculoto/3000", 404)["code"] == "not_found"


def test_pending_date_unknown_without_an_announcement(clean_db, megasena):
    store(clean_db, megasena, 3072)
    bet(clean_db, megasena)
    with clean_db.begin() as conn:  # e.g. the latest row came from an xlsx re-import
        conn.execute(draws.update().values(source_payload=None))
    (item,) = get(api_client(clean_db), "/games/megasena/oraculoto")["items"]
    assert item["status"] == "pending" and item["date"] is None


def test_empty_list(crawled):
    assert get(api_client(crawled), "/games/megasena/oraculoto")["items"] == []
