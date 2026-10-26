"""Backtests (docs/api.md §5): how a function would have scored, always next to chance.

For each target contest N, the function sees only the contests before N, and its k numbers
are scored against draw N. The random baseline is exact (hypergeometric), not simulated.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import comb, sqrt

from oraculoto.db.draws import Game
from oraculoto.guess.base import GuessFunction, PastDraw


def pool_size(game: Game) -> int:
    return game.ball_max - game.ball_min + 1


def hit_probability(game: Game, k: int, h: int) -> float:
    """Chance that a fair draw holds exactly h of a ticket's k numbers."""
    pool, d = pool_size(game), game.balls_drawn
    return comb(k, h) * comb(pool - k, d - h) / comb(pool, d)


def wins_tier(game: Game, k: int, h: int, tier: int) -> bool:
    """Whether a k-number ticket with h hits holds at least one winning combination of that tier
    (docs/api.md §6: C(h, tier) × C(k − h, balls_drawn − tier) > 0)."""
    return comb(h, tier) * comb(k - h, game.balls_drawn - tier) > 0


def expected_hits(game: Game, k: int) -> float:
    return k * game.balls_drawn / pool_size(game)


def hits_variance(game: Game, k: int) -> float:
    pool, d = pool_size(game), game.balls_drawn
    return k * d * (pool - k) * (pool - d) / (pool * pool * (pool - 1))


@dataclass(frozen=True)
class BacktestResult:
    function: GuessFunction
    params: dict
    k: int
    first_contest: int | None  # the target contests actually scored; None when there were none
    last_contest: int | None
    draws: int
    hits: dict[int, int]  # hits -> draws, from 0 up to min(k, balls_drawn)
    tiers: dict[int, int]  # prize tier -> draws where the guess won at least one combination of it

    @property
    def average_hits(self) -> float | None:
        return sum(h * n for h, n in self.hits.items()) / self.draws if self.draws else None

    def expected_tier(self, game: Game, tier: int) -> float:
        top = min(self.k, game.balls_drawn)
        p = sum(hit_probability(game, self.k, h) for h in range(top + 1) if wins_tier(game, self.k, h, tier))
        return self.draws * p

    def standard_error(self, game: Game) -> float | None:
        return sqrt(hits_variance(game, self.k) / self.draws) if self.draws else None

    def z_score(self, game: Game) -> float | None:
        """How many standard errors the average sits above (or below) chance."""
        if not self.draws:
            return None
        return (self.average_hits - expected_hits(game, self.k)) / self.standard_error(game)


def backtest(
    game: Game,
    history: Sequence[PastDraw],
    function: GuessFunction,
    k: int,
    params: Mapping,
    first_contest: int,
    last_contest: int,
) -> BacktestResult:
    """Score `function` on every contest in history between first_contest and last_contest.

    `history` is oldest first and must hold every contest up to last_contest; each guess gets
    only the slice before its target.
    """
    history = tuple(history)
    hits = dict.fromkeys(range(min(k, game.balls_drawn) + 1), 0)
    tiers = dict.fromkeys(game.prize_tiers, 0)
    scored = []
    for i, target in enumerate(history):
        if not first_contest <= target.contest <= last_contest:
            continue
        h = len(set(function.guess(game, history[:i], k, params)) & set(target.balls))
        hits[h] += 1
        for tier in tiers:
            if wins_tier(game, k, h, tier):
                tiers[tier] += 1
        scored.append(target.contest)
    return BacktestResult(
        function=function,
        params=dict(params),
        k=k,
        first_contest=scored[0] if scored else None,
        last_contest=scored[-1] if scored else None,
        draws=len(scored),
        hits=hits,
        tiers=tiers,
    )
