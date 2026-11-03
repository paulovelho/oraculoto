"""`guess_oraculoto`: the function behind oraculoto's own bet (docs/api.md §11). A placeholder.

Its randomness depends on the contest: the generator is seeded with the game and the target
contest, so it stays within the §5 contract (same input, same answer) and differs per contest.
It's not in REGISTRY: it's oraculoto's, not one users pick or backtest.
"""

import random
from collections.abc import Mapping, Sequence

from oraculoto.db.draws import Game
from oraculoto.guess.base import GuessFunction, PastDraw


def target_contest(history: Sequence[PastDraw]) -> int:
    return history[-1].contest + 1 if history else 1


def guess_oraculoto(game: Game, history: Sequence[PastDraw], k: int, params: Mapping) -> list[int]:
    rng = random.Random(f"{game.slug}:{target_contest(history)}")
    return rng.sample(range(game.ball_min, game.ball_max + 1), k)


ORACULOTO = GuessFunction(
    "guess_oraculoto",
    1,
    "oraculoto's own bet; a placeholder: k numbers drawn at random, seeded by the target contest",
    guess_oraculoto,
)
