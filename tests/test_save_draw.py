from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from oraculoto.db.draws import DrawData, DrawValidationError, Prize, WinnerLocation, save_draw
from oraculoto.db.schema import draw_balls, draw_prizes, draw_winner_locations, draws


def make_draw(**changes) -> DrawData:
    base = DrawData(
        contest_number=3073,
        draw_date=date(2026, 10, 22),
        balls=(4, 13, 23, 28, 41, 58),
        prizes=(
            Prize(6, 0, Decimal("0.00")),
            Prize(5, 50, Decimal("40000.00")),
            Prize(4, 3000, Decimal("900.00")),
        ),
        rollover_amount=Decimal("200000000.00"),
        special_accumulated=Decimal("110000000.00"),
        source="api",
        draw_order=(41, 4, 58, 13, 28, 23),
        is_special=False,
        total_collected=Decimal("100000000.00"),
        next_estimated_prize=Decimal("215000000.00"),
        locations=(),
        source_payload={"numero": 3073},
    )
    return replace(base, **changes)


def stored(conn, contest=3073):
    draw = conn.execute(select(draws).where(draws.c.contest_number == contest)).mappings().one()
    balls = conn.execute(
        select(draw_balls.c.ball, draw_balls.c.draw_position).where(draw_balls.c.draw_id == draw["id"])
    ).all()
    prizes = conn.execute(
        select(draw_prizes.c.hits, draw_prizes.c.winners, draw_prizes.c.prize_per_winner).where(
            draw_prizes.c.draw_id == draw["id"]
        )
    ).all()
    locations = conn.execute(
        select(draw_winner_locations).where(draw_winner_locations.c.draw_id == draw["id"])
    ).all()
    return draw, sorted(balls), sorted(prizes, reverse=True), locations


def test_insert_with_draw_order(conn, megasena):
    assert save_draw(conn, megasena, make_draw()) == "inserted"
    draw, balls, prizes, _ = stored(conn)
    assert balls == [(4, 2), (13, 4), (23, 6), (28, 5), (41, 1), (58, 3)]
    assert prizes == [(6, 0, Decimal("0.00")), (5, 50, Decimal("40000.00")), (4, 3000, Decimal("900.00"))]
    assert draw["source"] == "api" and draw["is_special"] is False
    assert draw["source_payload"] == {"numero": 3073}
    assert draw["total_collected"] == Decimal("100000000.00")


def test_same_data_again_is_unchanged(conn, megasena):
    save_draw(conn, megasena, make_draw(locations=(WinnerLocation(raw="SP", uf="SP"),)))
    before = stored(conn)
    assert save_draw(conn, megasena, make_draw(locations=(WinnerLocation(raw="SP", uf="SP"),))) == "unchanged"
    assert stored(conn) == before


def test_update_replaces_children(conn, megasena):
    save_draw(
        conn,
        megasena,
        make_draw(locations=(WinnerLocation(raw="SP", uf="SP"), WinnerLocation(raw="RJ", uf="RJ"))),
    )
    newer = make_draw(
        prizes=(
            Prize(6, 1, Decimal("215000000.00")),
            Prize(5, 50, Decimal("40000.00")),
            Prize(4, 3000, Decimal("900.00")),
        ),
        locations=(WinnerLocation(raw="CANAL ELETRONICO/--", is_online=True, winners=1),),
        rollover_amount=Decimal("0.00"),
    )
    assert save_draw(conn, megasena, newer) == "updated"
    draw, _, prizes, locations = stored(conn)
    assert prizes[0] == (6, 1, Decimal("215000000.00"))
    assert [(loc.raw, loc.is_online, loc.winners) for loc in locations] == [("CANAL ELETRONICO/--", True, 1)]
    assert draw["rollover_amount"] == 0


def test_xlsx_row_has_no_positions(conn, megasena):
    save_draw(conn, megasena, make_draw(draw_order=None, source="xlsx", is_special=None, source_payload=None))
    draw, balls, _, _ = stored(conn)
    assert [pos for _, pos in balls] == [None] * 6
    assert draw["is_special"] is None


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"balls": (4, 13, 23, 28, 41)}, "expected 6 balls"),
        ({"balls": (4, 13, 23, 28, 41, 41)}, "repeated balls"),
        ({"balls": (4, 13, 23, 28, 41, 61)}, "out of range"),
        ({"draw_order": (41, 4, 58, 13, 28, 22)}, "draw order"),
        ({"prizes": (Prize(6, 0, Decimal("0")), Prize(5, 1, Decimal("1")))}, "prize tiers"),
        (
            {
                "prizes": (
                    Prize(6, 1, Decimal("0.00")),
                    Prize(5, 1, Decimal("1.00")),
                    Prize(4, 1, Decimal("1.00")),
                )
            },
            "6 hits: 1 winners but prize 0.00",
        ),
        ({"rollover_amount": Decimal("1.005")}, "more than 2 decimals"),
        ({"total_collected": Decimal("-1.00")}, "negative"),
        ({"source": "csv"}, "unknown source"),
        ({"contest_number": 0}, "contest number"),
        ({"locations": (WinnerLocation(raw="X", uf="XYZ"),)}, "bad state"),
    ],
)
def test_invalid_draws_write_nothing(conn, megasena, changes, message):
    with pytest.raises(DrawValidationError, match=message):
        save_draw(conn, megasena, make_draw(**changes))
    assert conn.execute(select(draws)).first() is None
