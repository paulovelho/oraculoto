"""Heat (`calor`): how much more a ball came out lately than its own long-run rate predicts.

    heat(ball) = times in the last WINDOW contests - times overall x (WINDOW / contests overall)

Positive is hot, negative is cold. It's one function for both places that use it, the stats
panel (`GET /games/{game}/stats/heat`) and `guess_oraculoto`'s last-resort filler, so the two
never disagree. Bump HEAT_VERSION whenever the formula or the window changes: it goes into the
panel's HTTP cache key.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import chain

from oraculoto.db.draws import Game
from oraculoto.guess.base import PastDraw

HEAT_WINDOW = 100
HEAT_VERSION = 1


def heat(
    game: Game, recent: Mapping[int, int], overall: Mapping[int, int], contests: int, window: int
) -> dict[int, float]:
    """Per ball. `recent` counts the last `window` contests (fewer if history is shorter, in which
    case pass the real number), `overall` the `contests` of the whole history. No history: all 0."""
    share = window / contests if contests else 0.0
    return {b: recent.get(b, 0) - overall.get(b, 0) * share for b in range(game.ball_min, game.ball_max + 1)}


def ranked(scores: Mapping[int, float]) -> list[int]:
    """Hottest first; ties go to the lower ball."""
    return sorted(scores, key=lambda b: (-scores[b], b))


def heat_from_history(game: Game, history: Sequence[PastDraw], window: int = HEAT_WINDOW) -> dict[int, float]:
    last = history[-window:]
    recent = Counter(chain.from_iterable(d.balls for d in last))
    overall = Counter(chain.from_iterable(d.balls for d in history))
    return heat(game, recent, overall, len(history), len(last))
