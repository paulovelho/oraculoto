"""The importer against the database: the sample file, then the real file with the expected
values from docs/database.md §7 and the example queries from §6."""

from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text

from oraculoto.db.draws import save_draw
from oraculoto.db.schema import draw_balls, draw_prizes, draw_winner_locations, draws, sync_runs
from oraculoto.importer.caixa_xlsx import ImportFileError, import_xlsx, parse_file
from tests.xlsx_builder import SAMPLE_ROWS, build_xlsx, megasena_row


def count(engine, table) -> int:
    with engine.connect() as c:
        return c.execute(select(func.count()).select_from(table)).scalar_one()


def runs(engine):
    with engine.connect() as c:
        return c.execute(select(sync_runs.c.status, sync_runs.c.draws_written).order_by(sync_runs.c.id)).all()


def test_import_sample_then_again(clean_db, tmp_path):
    path = build_xlsx(tmp_path / "s.xlsx", SAMPLE_ROWS)
    first = import_xlsx(clean_db, "megasena", path)
    assert (first.inserted, first.updated, first.unchanged) == (3, 0, 0)
    second = import_xlsx(clean_db, "megasena", path)
    assert (second.inserted, second.updated, second.unchanged) == (0, 0, 3)
    assert (
        count(clean_db, draws) == 3
        and count(clean_db, draw_balls) == 18
        and count(clean_db, draw_prizes) == 9
    )
    assert count(clean_db, draw_winner_locations) == 2
    assert runs(clean_db) == [("ok", 3), ("nothing_new", 0)]


def test_dry_run_writes_nothing(clean_db, tmp_path):
    report = import_xlsx(clean_db, "megasena", build_xlsx(tmp_path / "s.xlsx", SAMPLE_ROWS), dry_run=True)
    assert report.rows == 3
    assert count(clean_db, draws) == 0 and runs(clean_db) == []


def test_bad_file_writes_nothing_but_the_error_log(clean_db, tmp_path):
    rows = [*SAMPLE_ROWS, megasena_row(4, "01/04/1996", ["01", "02", "03", "04", "05", "99"])]
    with pytest.raises(ImportFileError, match="row 5"):
        import_xlsx(clean_db, "megasena", build_xlsx(tmp_path / "bad.xlsx", rows))
    assert count(clean_db, draws) == 0
    assert runs(clean_db) == [("error", 0)]


def test_api_rows_are_skipped_unless_forced(clean_db, megasena, tmp_path):
    path = build_xlsx(tmp_path / "s.xlsx", SAMPLE_ROWS)
    sample, _ = parse_file(path, megasena)
    with clean_db.begin() as c:
        save_draw(c, megasena, replace(sample[1], source="api", draw_order=(49, 9, 37, 39, 41, 43)))

    report = import_xlsx(clean_db, "megasena", path)
    assert (report.inserted, report.skipped_api) == (2, 1)
    with clean_db.connect() as c:
        assert c.execute(select(draws.c.source).where(draws.c.contest_number == 2)).scalar_one() == "api"

    forced = import_xlsx(clean_db, "megasena", path, force=True)
    assert (forced.updated, forced.unchanged, forced.skipped_api) == (1, 2, 0)
    with clean_db.connect() as c:
        assert c.execute(select(draws.c.source).where(draws.c.contest_number == 2)).scalar_one() == "xlsx"


# ---------------------------------------------------------------- the real file


# `imported` (conftest.py): the real file, imported once per module.


def q(engine, sql: str, **params):
    with engine.connect() as c:
        return c.execute(text(sql), params).all()


def test_real_file_counts(imported):
    engine, report = imported
    assert (report.rows, report.inserted, report.first_contest, report.last_contest) == (3072, 3072, 1, 3072)
    assert report.warnings == []
    assert [count(engine, t) for t in (draws, draw_balls, draw_prizes, draw_winner_locations)] == [
        3072,
        18432,
        9216,
        903,
    ]
    assert q(
        engine,
        "SELECT SUM(city IS NOT NULL AND uf IS NOT NULL), SUM(city IS NULL AND uf IS NOT NULL),"
        " SUM(is_online), SUM(city IS NULL AND uf IS NULL AND NOT is_online) FROM draw_winner_locations",
    ) == [(597, 263, 43, 0)]
    assert q(
        engine,
        "SELECT SUM(total_collected IS NULL), SUM(next_estimated_prize IS NULL), SUM(is_special IS NULL) FROM draws",
    ) == [(1069, 860, 3072)]


def test_real_file_first_and_last_contest(imported):
    engine, _ = imported
    rows = q(
        engine,
        "SELECT d.contest_number, GROUP_CONCAT(b.ball ORDER BY b.ball), d.rollover_amount, d.total_collected,"
        " d.next_estimated_prize, d.special_accumulated"
        " FROM draws d JOIN draw_balls b ON b.draw_id = d.id WHERE d.contest_number IN (1, 3072)"
        " GROUP BY d.id, d.contest_number ORDER BY d.contest_number",
    )
    assert rows == [
        (1, "4,5,30,33,41,52", Decimal("1714650.23"), None, None, Decimal("0.00")),
        (
            3072,
            "2,6,9,16,31,40",
            Decimal("187648868.43"),
            Decimal("134543238.00"),
            Decimal("200000000.00"),
            Decimal("106119095.67"),
        ),
    ]
    prizes = q(
        engine,
        "SELECT d.contest_number, p.hits, p.winners, p.prize_per_winner FROM draw_prizes p"
        " JOIN draws d ON d.id = p.draw_id WHERE d.contest_number IN (1, 3072)"
        " ORDER BY d.contest_number, p.hits DESC",
    )
    assert prizes == [
        (1, 6, 0, Decimal("0.00")),
        (1, 5, 17, Decimal("39158.92")),
        (1, 4, 2016, Decimal("330.21")),
        (3072, 6, 0, Decimal("0.00")),
        (3072, 5, 140, Decimal("38295.72")),
        (3072, 4, 9261, Decimal("954.26")),
    ]


def test_real_file_again_changes_nothing(imported, real_xlsx):
    engine, _ = imported
    again = import_xlsx(engine, "megasena", real_xlsx)
    assert (again.inserted, again.updated, again.unchanged) == (0, 0, 3072)


# docs/database.md §6: every example query, with the results written there.


def test_query_last_time_balls_together(imported):
    engine, _ = imported
    sql = (
        "SELECT d.contest_number, d.draw_date FROM draws d JOIN draw_balls b ON b.draw_id = d.id"
        " WHERE d.game_id = 1 AND b.ball IN (10, 53) GROUP BY d.id, d.contest_number, d.draw_date"
        " HAVING COUNT(*) = 2 ORDER BY d.contest_number DESC"
    )
    rows = q(engine, sql)
    assert len(rows) == 38
    assert (rows[0][0], str(rows[0][1])) == (3065, "2026-10-01")


def test_query_last_jackpot_with_balls(imported):
    engine, _ = imported
    sql = (
        "SELECT d.contest_number, d.draw_date FROM draws d JOIN games g ON g.id = d.game_id"
        " JOIN draw_balls b ON b.draw_id = d.id WHERE d.game_id = 1 AND b.ball IN ({balls})"
        " AND EXISTS (SELECT 1 FROM draw_prizes p WHERE p.draw_id = d.id AND p.hits = g.balls_drawn"
        " AND p.winners > 0) GROUP BY d.id, d.contest_number, d.draw_date HAVING COUNT(*) = {n}"
        " ORDER BY d.contest_number DESC LIMIT 1"
    )
    assert [(c, str(d)) for c, d in q(engine, sql.format(balls="10, 53", n=2))] == [(3043, "2026-08-11")]
    assert [(c, str(d)) for c, d in q(engine, sql.format(balls="26", n=1))] == [(3015, "2026-06-06")]


def test_query_frequency(imported):
    engine, _ = imported
    rows = q(
        engine,
        "SELECT b.ball, COUNT(*) AS times FROM draw_balls b JOIN draws d ON d.id = b.draw_id"
        " WHERE d.game_id = 1 GROUP BY b.ball ORDER BY times DESC, b.ball",
    )
    assert rows[:3] == [(10, 359), (53, 350), (5, 335)]
    assert rows[-3:] == [(55, 264), (21, 261), (26, 250)]


def test_query_pairs_and_triples(imported):
    engine, _ = imported
    pairs = q(
        engine,
        "SELECT a.ball, b.ball, COUNT(*) AS times FROM draw_balls a"
        " JOIN draw_balls b ON b.draw_id = a.draw_id AND b.ball > a.ball JOIN draws d ON d.id = a.draw_id"
        " WHERE d.game_id = 1 GROUP BY a.ball, b.ball ORDER BY times DESC, a.ball, b.ball LIMIT 3",
    )
    assert pairs == [(5, 27, 43), (4, 52, 42), (23, 53, 42)]
    triples = q(
        engine,
        "SELECT a.ball, b.ball, c.ball, COUNT(*) AS times FROM draw_balls a"
        " JOIN draw_balls b ON b.draw_id = a.draw_id AND b.ball > a.ball"
        " JOIN draw_balls c ON c.draw_id = a.draw_id AND c.ball > b.ball JOIN draws d ON d.id = a.draw_id"
        " WHERE d.game_id = 1 GROUP BY a.ball, b.ball, c.ball ORDER BY times DESC, a.ball, b.ball, c.ball LIMIT 3",
    )
    assert triples == [(4, 17, 52, 8), (4, 27, 52, 8), (4, 28, 30, 8)]


def test_query_gaps(imported):
    engine, _ = imported
    current = q(
        engine,
        "SELECT b.ball, MAX(d.contest_number) AS last_seen,"
        " (SELECT MAX(contest_number) FROM draws WHERE game_id = 1) - MAX(d.contest_number) AS current_gap"
        " FROM draw_balls b JOIN draws d ON d.id = b.draw_id WHERE d.game_id = 1"
        " GROUP BY b.ball ORDER BY current_gap DESC, b.ball LIMIT 3",
    )
    assert current == [(34, 3027, 45), (32, 3031, 41), (59, 3035, 37)]
    longest = q(
        engine,
        "SELECT ball, MAX(gap) AS longest_gap FROM (SELECT b.ball, d.contest_number - LAG(d.contest_number)"
        " OVER (PARTITION BY b.ball ORDER BY d.contest_number) - 1 AS gap FROM draw_balls b"
        " JOIN draws d ON d.id = b.draw_id WHERE d.game_id = 1) t GROUP BY ball ORDER BY longest_gap DESC LIMIT 3",
    )
    assert longest == [(42, 108), (26, 88), (19, 82)]


def test_view_draw_balls_flat(imported):
    engine, _ = imported
    assert q(
        engine,
        "SELECT game, contest_number, ball, draw_position FROM draw_balls_flat"
        " WHERE contest_number = 1 ORDER BY ball LIMIT 2",
    ) == [("megasena", 1, 4, None), ("megasena", 1, 5, None)]
