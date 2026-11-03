"""Oraculoto's bets (docs/database.md, `oraculoto_bets` and `oraculoto_bet_numbers`).

One per contest, enforced by the unique key. Nothing here updates or deletes a bet.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Connection, func, insert, select

from oraculoto.db.draws import Game
from oraculoto.db.schema import oraculoto_bet_numbers, oraculoto_bets


@dataclass(frozen=True)
class Bet:
    contest: int
    numbers: tuple[int, ...]  # ascending
    source: str
    created_at: datetime


def _load(conn: Connection, rows: list) -> list[Bet]:
    ids = [r.id for r in rows]
    numbers: dict[int, list[int]] = {i: [] for i in ids}
    if ids:
        for bet_id, ball in conn.execute(
            select(oraculoto_bet_numbers.c.bet_id, oraculoto_bet_numbers.c.ball)
            .where(oraculoto_bet_numbers.c.bet_id.in_(ids))
            .order_by(oraculoto_bet_numbers.c.bet_id, oraculoto_bet_numbers.c.ball)
        ):
            numbers[bet_id].append(ball)
    return [Bet(r.contest_number, tuple(numbers[r.id]), r.source, r.created_at) for r in rows]


def _select(game: Game):
    return select(
        oraculoto_bets.c.id,
        oraculoto_bets.c.contest_number,
        oraculoto_bets.c.source,
        oraculoto_bets.c.created_at,
    ).where(oraculoto_bets.c.game_id == game.id)


def create_bet(conn: Connection, game: Game, contest: int, numbers: tuple[int, ...], source: str) -> None:
    """Insert the bet and its numbers; the caller commits. A second bet for the contest raises
    IntegrityError (the unique key). Checks are the caller's (bets.py)."""
    bet_id = conn.execute(
        insert(oraculoto_bets).values(game_id=game.id, contest_number=contest, source=source)
    ).inserted_primary_key[0]
    conn.execute(insert(oraculoto_bet_numbers), [{"bet_id": bet_id, "ball": n} for n in numbers])


def get_bet(conn: Connection, game: Game, contest: int) -> Bet | None:
    found = _load(conn, conn.execute(_select(game).where(oraculoto_bets.c.contest_number == contest)).all())
    return found[0] if found else None


def list_bets(conn: Connection, game: Game, limit: int, offset: int) -> tuple[list[Bet], int]:
    """A page of the game's bets, newest contest first, and how many there are."""
    total = conn.execute(
        select(func.count()).select_from(oraculoto_bets).where(oraculoto_bets.c.game_id == game.id)
    ).scalar_one()
    rows = conn.execute(
        _select(game).order_by(oraculoto_bets.c.contest_number.desc()).limit(limit).offset(offset)
    ).all()
    return _load(conn, rows), total
