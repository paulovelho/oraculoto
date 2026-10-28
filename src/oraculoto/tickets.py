"""Ticket rules and scoring (docs/api.md §4, Tickets, and §6). No database here.

A ticket of k numbers that hit h of a draw holds, for each prize tier j,
C(h, j) x C(k - h, balls_drawn - j) winning combinations of balls_drawn numbers.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from math import comb

from oraculoto.db.draws import Game

MAX_CONTEST = 999_999  # far beyond any real contest; keeps typos out of an INT column


class TicketError(ValueError):
    """The ticket breaks the game's rules or the API's limits."""


def check_numbers(game: Game, numbers: Sequence[int]) -> tuple[int, ...]:
    """The numbers, ascending, if a ticket of this game may hold them."""
    if not game.bet_min_numbers <= len(numbers) <= game.bet_max_numbers:
        raise TicketError(
            f"numbers: a {game.name} ticket has {game.bet_min_numbers}-{game.bet_max_numbers} numbers, "
            f"got {len(numbers)}"
        )
    if len(set(numbers)) != len(numbers):
        raise TicketError("numbers: repeated numbers")
    out = [n for n in numbers if not game.ball_min <= n <= game.ball_max]
    if out:
        raise TicketError(f"numbers: {out[0]} is outside {game.ball_min}-{game.ball_max}")
    return tuple(sorted(numbers))


def check_contests(first: int, last: int | None, max_span: int) -> tuple[int, int]:
    """(first, last), last defaulting to first, within the span cap."""
    last = first if last is None else last
    if not 1 <= first <= MAX_CONTEST or not 1 <= last <= MAX_CONTEST:
        raise TicketError(f"contests must be 1-{MAX_CONTEST}")
    if last < first:
        raise TicketError(f"last_contest ({last}) is before first_contest ({first})")
    if last - first + 1 > max_span:
        raise TicketError(f"a ticket covers at most {max_span} contests, got {last - first + 1}")
    return first, last


def winning_combinations(game: Game, k: int, hits: int) -> list[tuple[int, int]]:
    """(tier, combinations) for every tier the ticket wins, top tier first."""
    tiers = []
    for j in game.prize_tiers:
        n = comb(hits, j) * comb(k - hits, game.balls_drawn - j)
        if n:
            tiers.append((j, n))
    return tiers


@dataclass(frozen=True)
class TierWin:
    hits: int
    combinations: int
    prize_per_winner: Decimal | None  # None: the contest's prize for this tier is unknown
    amount: Decimal | None


@dataclass(frozen=True)
class ContestScore:
    hits: int
    matched: tuple[int, ...]
    wins: tuple[TierWin, ...]
    total: Decimal | None  # None if any won tier's prize is unknown


def score(
    game: Game, numbers: Sequence[int], balls: Sequence[int], prizes: Mapping[int, Decimal]
) -> ContestScore:
    """How a ticket did in one drawn contest; prizes maps tier hits to prize_per_winner."""
    matched = tuple(sorted(set(numbers) & set(balls)))
    wins = []
    for tier, n in winning_combinations(game, len(numbers), len(matched)):
        prize = prizes.get(tier)
        wins.append(TierWin(tier, n, prize, None if prize is None else prize * n))
    amounts = [w.amount for w in wins]
    total = None if None in amounts else sum(amounts, Decimal("0.00"))
    return ContestScore(len(matched), matched, tuple(wins), total)
