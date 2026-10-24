"""The single write path for draws (docs/database.md §4, rule 2).

The importer, the crawler and the backfill all call `save_draw()`; nothing else writes
draws, draw_balls, draw_prizes or draw_winner_locations.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import Connection, delete, insert, select, update

from oraculoto.db.schema import draw_balls, draw_prizes, draw_winner_locations, draws, games

SaveResult = Literal["inserted", "updated", "unchanged"]
SOURCES = ("xlsx", "api")
# draws columns that come straight from DrawData (same names)
DRAW_COLUMNS = (
    "draw_date",
    "is_special",
    "total_collected",
    "rollover_amount",
    "next_estimated_prize",
    "special_accumulated",
    "notes",
    "source",
    "source_payload",
)


class DrawValidationError(ValueError):
    """The draw breaks the game's rules or the schema's; nothing was written."""


@dataclass(frozen=True)
class Game:
    id: int
    slug: str
    name: str
    balls_drawn: int
    ball_min: int
    ball_max: int
    min_winning_hits: int
    bet_min_numbers: int
    bet_max_numbers: int

    @property
    def prize_tiers(self) -> list[int]:
        """Hits that pay, top tier first (6, 5, 4 for Mega-Sena)."""
        return list(range(self.balls_drawn, self.min_winning_hits - 1, -1))


@dataclass(frozen=True)
class Prize:
    hits: int
    winners: int
    prize_per_winner: Decimal


@dataclass(frozen=True)
class WinnerLocation:
    raw: str
    city: str | None = None
    uf: str | None = None
    is_online: bool = False
    winners: int | None = None


@dataclass(frozen=True)
class DrawData:
    contest_number: int
    draw_date: date
    balls: tuple[int, ...]
    prizes: tuple[Prize, ...]
    rollover_amount: Decimal
    special_accumulated: Decimal
    source: str
    draw_order: tuple[int, ...] | None = None  # the balls in the order they were drawn, when known
    locations: tuple[WinnerLocation, ...] = ()
    is_special: bool | None = None
    total_collected: Decimal | None = None
    next_estimated_prize: Decimal | None = None
    notes: str | None = None
    source_payload: dict[str, Any] | None = field(default=None, compare=False)


def get_game(conn: Connection, slug: str) -> Game:
    row = conn.execute(select(games).where(games.c.slug == slug)).mappings().first()
    if row is None:
        raise LookupError(f"unknown game: {slug}")
    return Game(**{k: row[k] for k in Game.__dataclass_fields__})


def validate_draw(game: Game, draw: DrawData) -> None:
    def fail(reason: str) -> None:
        raise DrawValidationError(f"{game.slug} #{draw.contest_number}: {reason}")

    if draw.contest_number < 1:
        fail("contest number must be >= 1")
    if draw.source not in SOURCES:
        fail(f"unknown source {draw.source!r}")

    balls = draw.balls
    if len(balls) != game.balls_drawn:
        fail(f"expected {game.balls_drawn} balls, got {len(balls)}")
    if len(set(balls)) != len(balls):
        fail(f"repeated balls {sorted(balls)}")
    if any(b < game.ball_min or b > game.ball_max for b in balls):
        fail(f"balls out of range {game.ball_min}-{game.ball_max}: {sorted(balls)}")
    if draw.draw_order is not None and sorted(draw.draw_order) != sorted(balls):
        fail(f"draw order {list(draw.draw_order)} doesn't hold the same balls as {sorted(balls)}")

    tiers = sorted((p.hits for p in draw.prizes), reverse=True)
    if tiers != game.prize_tiers:
        fail(f"prize tiers {tiers}, expected {game.prize_tiers}")
    for p in draw.prizes:
        if p.winners < 0:
            fail(f"{p.hits} hits: negative winners")
        if (p.prize_per_winner > 0) != (p.winners > 0):
            fail(f"{p.hits} hits: {p.winners} winners but prize {p.prize_per_winner}")

    money = {
        "prize_per_winner": [p.prize_per_winner for p in draw.prizes],
        "total_collected": [draw.total_collected],
        "rollover_amount": [draw.rollover_amount],
        "next_estimated_prize": [draw.next_estimated_prize],
        "special_accumulated": [draw.special_accumulated],
    }
    for name, values in money.items():
        for v in values:
            if v is None:
                continue
            if v < 0:
                fail(f"{name} is negative: {v}")
            if v != v.quantize(Decimal("0.01")):
                fail(f"{name} has more than 2 decimals: {v}")

    for loc in draw.locations:
        if not loc.raw or len(loc.raw) > 255:
            fail(f"bad location text {loc.raw!r}")
        if loc.uf is not None and len(loc.uf) != 2:
            fail(f"bad state {loc.uf!r} in {loc.raw!r}")
        if loc.city is not None and len(loc.city) > 128:
            fail(f"city name too long in {loc.raw!r}")
        if loc.winners is not None and loc.winners < 0:
            fail(f"negative winners in {loc.raw!r}")


def _draw_columns(draw: DrawData) -> dict[str, Any]:
    return {k: getattr(draw, k) for k in DRAW_COLUMNS}


def _ball_rows(draw: DrawData) -> list[tuple[int, int | None]]:
    position = {b: i + 1 for i, b in enumerate(draw.draw_order)} if draw.draw_order else {}
    return sorted((b, position.get(b)) for b in draw.balls)


def _snapshot(columns: dict, balls: list, prizes: list, locations: list) -> tuple:
    return (
        columns,
        sorted(balls),
        sorted(prizes),
        sorted(locations, key=lambda loc: tuple("" if v is None else str(v) for v in loc)),
    )


def _stored_snapshot(conn: Connection, draw_id: int, row) -> tuple:
    columns = {k: row[k] for k in DRAW_COLUMNS}
    balls = conn.execute(
        select(draw_balls.c.ball, draw_balls.c.draw_position).where(draw_balls.c.draw_id == draw_id)
    ).all()
    prizes = conn.execute(
        select(draw_prizes.c.hits, draw_prizes.c.winners, draw_prizes.c.prize_per_winner).where(
            draw_prizes.c.draw_id == draw_id
        )
    ).all()
    locations = conn.execute(
        select(
            draw_winner_locations.c.raw,
            draw_winner_locations.c.city,
            draw_winner_locations.c.uf,
            draw_winner_locations.c.is_online,
            draw_winner_locations.c.winners,
        ).where(draw_winner_locations.c.draw_id == draw_id)
    ).all()
    return _snapshot(columns, *([tuple(r) for r in rows] for rows in (balls, prizes, locations)))


def _new_snapshot(draw: DrawData) -> tuple:
    return _snapshot(
        _draw_columns(draw),
        _ball_rows(draw),
        [(p.hits, p.winners, p.prize_per_winner) for p in draw.prizes],
        [(loc.raw, loc.city, loc.uf, loc.is_online, loc.winners) for loc in draw.locations],
    )


def save_draw(conn: Connection, game: Game, draw: DrawData) -> SaveResult:
    """Validate, then insert or update one draw and replace its balls, prizes and locations.

    Runs on the caller's connection and transaction: the caller decides whether one draw or a
    whole file is all-or-nothing. Writing the same data again changes nothing ("unchanged").
    """
    validate_draw(game, draw)

    row = (
        conn.execute(
            select(draws)
            .where(draws.c.game_id == game.id, draws.c.contest_number == draw.contest_number)
            .with_for_update()
        )
        .mappings()
        .first()
    )
    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)

    if row is None:
        draw_id = conn.execute(
            insert(draws).values(
                game_id=game.id,
                contest_number=draw.contest_number,
                created_at=now,
                updated_at=now,
                **_draw_columns(draw),
            )
        ).inserted_primary_key[0]
        result: SaveResult = "inserted"
    else:
        draw_id = row["id"]
        if _stored_snapshot(conn, draw_id, row) == _new_snapshot(draw):
            return "unchanged"
        conn.execute(update(draws).where(draws.c.id == draw_id).values(updated_at=now, **_draw_columns(draw)))
        for child in (draw_balls, draw_prizes, draw_winner_locations):
            conn.execute(delete(child).where(child.c.draw_id == draw_id))
        result = "updated"

    conn.execute(
        insert(draw_balls),
        [{"draw_id": draw_id, "ball": b, "draw_position": pos} for b, pos in _ball_rows(draw)],
    )
    conn.execute(
        insert(draw_prizes),
        [
            {"draw_id": draw_id, "hits": p.hits, "winners": p.winners, "prize_per_winner": p.prize_per_winner}
            for p in draw.prizes
        ],
    )
    if draw.locations:
        conn.execute(
            insert(draw_winner_locations),
            [
                {
                    "draw_id": draw_id,
                    "raw": loc.raw,
                    "city": loc.city,
                    "uf": loc.uf,
                    "is_online": loc.is_online,
                    "winners": loc.winners,
                }
                for loc in draw.locations
            ],
        )
    return result
