"""Oraculoto's own bet (docs/api.md §11): one per contest, placed before the draw, never changed.

The bet is on the contest after the latest one stored, with the history up to it. It's placed
only while Caixa still takes bets for that contest (until 19:00 Brasília on its draw date), so
a crawler that fell behind makes oraculoto miss contests instead of betting on known results.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, select
from sqlalchemy.exc import IntegrityError

from oraculoto.crawler.caixa import next_draw_date
from oraculoto.db import bets as db
from oraculoto.db.draws import Game
from oraculoto.db.results import load_history
from oraculoto.db.schema import draws
from oraculoto.guess.oraculoto import ORACULOTO

BRASILIA = ZoneInfo("America/Sao_Paulo")
BETS_CLOSE = time(19, 0)  # Brasília; the draw is at 20:00


class BetError(RuntimeError):
    """No bet can be placed now; nothing was written."""


@dataclass(frozen=True)
class BetOutcome:
    result: Literal["placed", "already_placed"]
    bet: db.Bet
    closes_at: datetime | None  # Brasília; None for a bet that was already there


def place_bet(conn: Connection, game: Game, k: int | None = None, now: datetime | None = None) -> BetOutcome:
    """Bet on the next contest and commit. `k` defaults to the game's minimum bet.

    Running it again for the same contest changes nothing: it answers `already_placed` with the
    stored bet, unless `k` was given and differs from it (BetError).
    """
    if k is not None and not game.bet_min_numbers <= k <= game.bet_max_numbers:
        raise BetError(f"k must be {game.bet_min_numbers}-{game.bet_max_numbers}, got {k}")
    latest = conn.execute(
        select(draws.c.contest_number, draws.c.source_payload)
        .where(draws.c.game_id == game.id)
        .order_by(draws.c.contest_number.desc())
        .limit(1)
    ).first()
    if latest is None:
        raise BetError(f"no {game.name} contests stored: nothing to bet after")
    target = latest.contest_number + 1

    existing = db.get_bet(conn, game, target)
    if existing is not None:
        return _already(existing, k)

    due = next_draw_date(latest.source_payload)
    if due is None:
        raise BetError(
            f"can't tell when #{target} is drawn: #{latest.contest_number} has no announced next date "
            "(run the crawler first; xlsx rows don't carry it)"
        )
    closes_at = datetime.combine(due, BETS_CLOSE, tzinfo=BRASILIA)
    now = now or datetime.now(UTC)
    if now >= closes_at:
        raise BetError(
            f"too late for #{target}: bets closed at {closes_at:%Y-%m-%d %H:%M} Brasília "
            f"(is the crawler behind? the latest stored contest is #{latest.contest_number})"
        )

    history = load_history(conn, game, latest.contest_number)
    numbers = ORACULOTO.guess(game, history, game.bet_min_numbers if k is None else k, {})
    try:
        db.create_bet(conn, game, target, numbers, ORACULOTO.ref)
        conn.commit()
    except IntegrityError:
        # Another run placed it between our check and our insert.
        conn.rollback()
        return _already(db.get_bet(conn, game, target), k)
    return BetOutcome("placed", db.get_bet(conn, game, target), closes_at)


def _already(bet: db.Bet, k: int | None) -> BetOutcome:
    if k is not None and k != len(bet.numbers):
        raise BetError(
            f"#{bet.contest} already has oraculoto's bet, with {len(bet.numbers)} numbers; bets never change"
        )
    return BetOutcome("already_placed", bet, None)
