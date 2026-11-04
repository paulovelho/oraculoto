"""`guess_oraculoto`: the function behind oraculoto's own bet (docs/api.md §11). Work in progress.

Over the history before the target contest; the bet is filled in this order, and every step
stops once it holds k balls (in practice steps 0-4 never brought more than 6):

0. Every ball that didn't come out in any of the last RECENT contests goes in, most absent first.
   Over the whole history from here on, until step 5:
1. The absent balls: "Ausente há" (contests since the ball last came out, as in the stats panel)
   above ABSENT_OVER, most absent first.
2. The triples that came out exactly MAX - 1 times, MAX being the count of the most frequent triple.
3. Going through the absent balls, most absent first, the first one that's in any of those triples
   brings its triple into the bet, and the search stops. When it's in several, the triple with the
   largest summed absence wins; a tie there is drawn at random.
4. If none of them is in a triple, every absent ball goes in (most absent first, up to k).
Back to the last RECENT contests:
5. The ball with the second-largest count. Positions go by count value (two balls tied on the
   largest count are both 1st; the next count is 2nd). If more than one ball holds the 2nd, the
   3rd is tried, then the 4th, until a position holds one ball alone; if none does, skipped.
6. The ball absent the longest ("Ausente há" within the window), position 1 and down, by the
   same rule.
   Steps 5 and 6 are skipped when their ball is already in the bet.
7. Last resort: the bet is completed up to k with the hottest balls (oraculoto.guess.heat) not yet
   in it.

Its only randomness is step 3's tie, and the generator is seeded with the game and the target
contest, so it stays within the §5 contract (same input, same answer). It's not in REGISTRY:
it's oraculoto's, not one users pick or backtest.
"""

import random
from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import combinations

from oraculoto.db.draws import Game
from oraculoto.guess.base import GuessFunction, PastDraw
from oraculoto.guess.heat import heat_from_history, ranked

ABSENT_OVER = 30
RECENT = 52  # contests, for steps 0, 5 and 6


def target_contest(history: Sequence[PastDraw]) -> int:
    return history[-1].contest + 1 if history else 1


def current_gaps(game: Game, history: Sequence[PastDraw]) -> dict[int, int]:
    """The stats panel's "Ausente há" over the whole history: contests since the ball last came out,
    0 if it came out in the latest one, the whole history's span if it never did."""
    if not history:
        return {b: 0 for b in range(game.ball_min, game.ball_max + 1)}
    last_seen = {b: d.contest for d in history for b in d.balls}  # later contests overwrite earlier
    latest, span = history[-1].contest, history[-1].contest - history[0].contest + 1
    return {
        b: latest - last_seen[b] if b in last_seen else span for b in range(game.ball_min, game.ball_max + 1)
    }


def absent_balls(gaps: Mapping[int, int]) -> list[int]:
    """Step 1: most absent first, ties by the lower ball."""
    return sorted((b for b, g in gaps.items() if g > ABSENT_OVER), key=lambda b: (-gaps[b], b))


def runner_up_triples(game: Game, history: Sequence[PastDraw]) -> list[tuple[int, ...]]:
    """Step 2: the triples that came out exactly MAX - 1 times, ascending. None if MAX - 1 is 0."""
    counts = Counter(t for d in history for t in combinations(d.balls, 3))
    if not counts:
        return []
    wanted = max(counts.values()) - 1
    return sorted(t for t, n in counts.items() if n == wanted) if wanted > 0 else []


def absent_triple(
    absent: Sequence[int], triples: Sequence[tuple[int, ...]], gaps: Mapping[int, int], rng: random.Random
) -> tuple[int, ...] | None:
    """Step 3: the triple of the most absent ball that has one, or None."""
    for ball in absent:
        candidates = [t for t in triples if ball in t]
        if candidates:
            best = max(sum(gaps[b] for b in t) for t in candidates)
            tied = [t for t in candidates if sum(gaps[b] for b in t) == best]
            return tied[0] if len(tied) == 1 else rng.choice(tied)
    return None


def lone_at_or_after(scores: Mapping[int, int], position: int) -> int | None:
    """Steps 5 and 6: positions by score value, highest first (tied balls share one position).
    The ball alone at `position`, or at the first position after it held by one ball; None if none is."""
    for pos, value in enumerate(sorted(set(scores.values()), reverse=True), 1):
        if pos >= position:
            holders = [b for b, v in scores.items() if v == value]
            if len(holders) == 1:
                return holders[0]
    return None


def recent_counts(game: Game, recent: Sequence[PastDraw]) -> dict[int, int]:
    counts = Counter(b for d in recent for b in d.balls)
    return {b: counts[b] for b in range(game.ball_min, game.ball_max + 1)}


def guess_oraculoto(game: Game, history: Sequence[PastDraw], k: int, params: Mapping) -> list[int]:
    rng = random.Random(f"{game.slug}:{target_contest(history)}")
    picked: dict[int, None] = {}  # insertion-ordered set

    def add(*balls: int) -> None:
        for b in balls:
            if len(picked) < k:
                picked.setdefault(b)

    gaps = current_gaps(game, history)
    recent = history[-RECENT:]
    counts = recent_counts(game, recent)
    add(*sorted((b for b, n in counts.items() if n == 0), key=lambda b: (-gaps[b], b)))  # step 0

    absent = absent_balls(gaps)
    triple = absent_triple(absent, runner_up_triples(game, history), gaps, rng)
    add(*(triple or absent))  # steps 3 and 4

    for ball in (lone_at_or_after(counts, 2), lone_at_or_after(current_gaps(game, recent), 1)):
        if ball is not None and ball not in picked:  # steps 5 and 6
            add(ball)

    add(*ranked(heat_from_history(game, history)))  # step 7
    return list(picked)


ORACULOTO = GuessFunction(
    "guess_oraculoto",
    2,
    "oraculoto's own bet: balls missing from the last 52, the most absent ball's runner-up triple (or the "
    "absent balls), the 2nd most frequent and the longest absent of the last 52, completed by heat",
    guess_oraculoto,
)
