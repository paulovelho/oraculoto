"""The reference strategies of docs/api.md §5. None of them beats chance; they exist so the
backtest has known answers to reproduce, and as a yardstick for real functions.

Ties always go to the lower ball, so every answer is deterministic.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import chain

from oraculoto.db.draws import Game
from oraculoto.guess.base import GuessFunction, Param, PastDraw


def _most_frequent(game: Game, history: Sequence[PastDraw], k: int) -> list[int]:
    counts = Counter(chain.from_iterable(d.balls for d in history))
    return sorted(range(game.ball_min, game.ball_max + 1), key=lambda b: (-counts[b], b))[:k]


def hot(game: Game, history: Sequence[PastDraw], k: int, params: Mapping) -> list[int]:
    return _most_frequent(game, history, k)


def hot_recent(game: Game, history: Sequence[PastDraw], k: int, params: Mapping) -> list[int]:
    return _most_frequent(game, history[-params["last"] :], k)


def overdue(game: Game, history: Sequence[PastDraw], k: int, params: Mapping) -> list[int]:
    last_seen = {b: d.contest for d in history for b in d.balls}  # later contests overwrite earlier
    # A ball never drawn counts as the most overdue of all.
    return sorted(range(game.ball_min, game.ball_max + 1), key=lambda b: (last_seen.get(b, 0), b))[:k]


def repeat_last(game: Game, history: Sequence[PastDraw], k: int, params: Mapping) -> list[int]:
    """The previous draw's balls. For k above balls_drawn, keep adding balls from the draws
    before it, newest first; past the start of history, the lowest balls not yet picked."""
    picked: dict[int, None] = {}  # insertion-ordered set
    fallback = range(game.ball_min, game.ball_max + 1)
    for b in chain.from_iterable(chain((d.balls for d in reversed(history)), [fallback])):
        picked.setdefault(b)
        if len(picked) == k:
            break
    return list(picked)


FUNCTIONS = (
    GuessFunction("hot", 1, "the k most frequent balls in all earlier draws", hot),
    GuessFunction(
        "hot_recent",
        1,
        "the k most frequent balls in the last `last` draws",
        hot_recent,
        (Param("last", int, 200, "how many of the latest draws to count", min=1),),
    ),
    GuessFunction("overdue", 1, "the k balls whose last appearance is oldest", overdue),
    GuessFunction(
        "repeat_last",
        1,
        "the previous draw's balls (for k above balls drawn, filled from the draws before it)",
        repeat_last,
    ),
)
