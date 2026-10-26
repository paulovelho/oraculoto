"""Reading draws back: one contest, the latest, or a filtered page, with balls, prizes and locations."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import groupby

from sqlalchemy import Connection, func, select

from oraculoto.db.draws import Game, Prize, WinnerLocation
from oraculoto.db.schema import draw_balls, draw_prizes, draw_winner_locations, draws
from oraculoto.guess.base import PastDraw


@dataclass(frozen=True)
class DrawRecord:
    contest_number: int
    draw_date: date
    balls: tuple[int, ...]  # ascending
    draw_order: tuple[int, ...] | None  # as drawn; None unless every position is known
    prizes: tuple[Prize, ...]  # top tier first
    locations: tuple[WinnerLocation, ...]
    is_special: bool | None
    total_collected: Decimal | None
    rollover_amount: Decimal
    next_estimated_prize: Decimal | None
    special_accumulated: Decimal
    notes: str | None
    source: str


@dataclass(frozen=True)
class DrawFilter:
    first_contest: int | None = None
    last_contest: int | None = None
    date_from: date | None = None
    date_to: date | None = None

    def where(self, game: Game) -> list:
        conditions = [draws.c.game_id == game.id]
        if self.first_contest is not None:
            conditions.append(draws.c.contest_number >= self.first_contest)
        if self.last_contest is not None:
            conditions.append(draws.c.contest_number <= self.last_contest)
        if self.date_from is not None:
            conditions.append(draws.c.draw_date >= self.date_from)
        if self.date_to is not None:
            conditions.append(draws.c.draw_date <= self.date_to)
        return conditions


def _records(conn: Connection, rows: list) -> list[DrawRecord]:
    """Load the children of these draws rows with one query per child table."""
    ids = [r["id"] for r in rows]
    if not ids:
        return []
    balls: dict[int, list] = {i: [] for i in ids}
    prizes: dict[int, list] = {i: [] for i in ids}
    locations: dict[int, list] = {i: [] for i in ids}

    for draw_id, ball, position in conn.execute(
        select(draw_balls.c.draw_id, draw_balls.c.ball, draw_balls.c.draw_position)
        .where(draw_balls.c.draw_id.in_(ids))
        .order_by(draw_balls.c.draw_id, draw_balls.c.ball)
    ):
        balls[draw_id].append((ball, position))
    for draw_id, hits, winners, prize in conn.execute(
        select(
            draw_prizes.c.draw_id, draw_prizes.c.hits, draw_prizes.c.winners, draw_prizes.c.prize_per_winner
        )
        .where(draw_prizes.c.draw_id.in_(ids))
        .order_by(draw_prizes.c.draw_id, draw_prizes.c.hits.desc())
    ):
        prizes[draw_id].append(Prize(hits, winners, prize))
    for loc in conn.execute(
        select(draw_winner_locations)
        .where(draw_winner_locations.c.draw_id.in_(ids))
        .order_by(draw_winner_locations.c.draw_id, draw_winner_locations.c.id)
    ).mappings():
        locations[loc["draw_id"]].append(
            WinnerLocation(
                raw=loc["raw"],
                city=loc["city"],
                uf=loc["uf"],
                is_online=bool(loc["is_online"]),
                winners=loc["winners"],
            )
        )

    records = []
    for r in rows:
        drawn = balls[r["id"]]
        known = all(pos is not None for _, pos in drawn)
        records.append(
            DrawRecord(
                contest_number=r["contest_number"],
                draw_date=r["draw_date"],
                balls=tuple(b for b, _ in drawn),
                draw_order=tuple(b for b, _ in sorted(drawn, key=lambda bp: bp[1]))
                if drawn and known
                else None,
                prizes=tuple(prizes[r["id"]]),
                locations=tuple(locations[r["id"]]),
                is_special=None if r["is_special"] is None else bool(r["is_special"]),
                total_collected=r["total_collected"],
                rollover_amount=r["rollover_amount"],
                next_estimated_prize=r["next_estimated_prize"],
                special_accumulated=r["special_accumulated"],
                notes=r["notes"],
                source=r["source"],
            )
        )
    return records


# source_payload stays in the database: it's the raw API response, not part of a result.
_COLUMNS = [c for c in draws.c if c.name != "source_payload"]


def get_draw(conn: Connection, game: Game, contest_number: int) -> DrawRecord | None:
    rows = (
        conn.execute(
            select(*_COLUMNS).where(draws.c.game_id == game.id, draws.c.contest_number == contest_number)
        )
        .mappings()
        .all()
    )
    found = _records(conn, rows)
    return found[0] if found else None


def latest_draw(conn: Connection, game: Game) -> DrawRecord | None:
    rows = (
        conn.execute(
            select(*_COLUMNS)
            .where(draws.c.game_id == game.id)
            .order_by(draws.c.contest_number.desc())
            .limit(1)
        )
        .mappings()
        .all()
    )
    found = _records(conn, rows)
    return found[0] if found else None


def load_history(conn: Connection, game: Game, last_contest: int) -> list[PastDraw]:
    """Every contest up to last_contest, oldest first, in the shape guess functions take."""
    rows = conn.execute(
        select(draws.c.contest_number, draws.c.draw_date, draw_balls.c.ball, draw_balls.c.draw_position)
        .join(draw_balls, draw_balls.c.draw_id == draws.c.id)
        .where(draws.c.game_id == game.id, draws.c.contest_number <= last_contest)
        .order_by(draws.c.contest_number, draw_balls.c.ball)
    )
    history = []
    for (contest, drawn_on), group in groupby(rows, key=lambda r: (r[0], r[1])):
        drawn = [(ball, position) for _, _, ball, position in group]
        known = all(pos is not None for _, pos in drawn)
        history.append(
            PastDraw(
                contest=contest,
                date=drawn_on,
                balls=tuple(b for b, _ in drawn),
                draw_order=tuple(b for b, _ in sorted(drawn, key=lambda bp: bp[1])) if known else None,
            )
        )
    return history


def list_draws(
    conn: Connection, game: Game, flt: DrawFilter, limit: int, offset: int
) -> tuple[list[DrawRecord], int]:
    """A page of draws, newest first, and how many match in total."""
    where = flt.where(game)
    total = conn.execute(select(func.count()).select_from(draws).where(*where)).scalar_one()
    rows = (
        conn.execute(
            select(*_COLUMNS)
            .where(*where)
            .order_by(draws.c.contest_number.desc())
            .limit(limit)
            .offset(offset)
        )
        .mappings()
        .all()
    )
    return _records(conn, rows), total
