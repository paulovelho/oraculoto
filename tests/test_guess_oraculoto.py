"""`guess_oraculoto` and the heat function (docs/api.md §11). Only the real-file bet needs the database."""

import random
from datetime import date, timedelta

import pytest

from oraculoto.db.draws import Game, get_game
from oraculoto.db.results import load_history
from oraculoto.guess.base import PastDraw
from oraculoto.guess.heat import heat, heat_from_history, ranked
from oraculoto.guess.oraculoto import (
    ORACULOTO,
    absent_triple,
    current_gaps,
    lone_at_or_after,
    runner_up_triples,
)

MS = Game(1, "megasena", "Mega-Sena", 6, 1, 60, 4, 6, 20)


def draws(*balls: tuple[int, ...]) -> list[PastDraw]:
    start = date(2000, 1, 1)
    return [PastDraw(i + 1, start + timedelta(days=i), tuple(sorted(b)), None) for i, b in enumerate(balls)]


# (1, 2, 3) comes out twice (MAX = 2); every other triple once (MAX - 1).
HISTORY = draws(
    (1, 2, 3, 10, 20, 30),
    (1, 2, 3, 40, 50, 60),
    (11, 21, 31, 41, 51, 59),
    (12, 22, 32, 42, 52, 58),
)


def guess(history=HISTORY, k=6) -> tuple[int, ...]:
    return ORACULOTO.guess(MS, history, k, {})


# ---------------------------------------------------------------- the steps


def test_gaps_match_the_stats_panel():
    gaps = current_gaps(MS, HISTORY)
    assert (gaps[12], gaps[11], gaps[1], gaps[10]) == (0, 1, 2, 3)
    assert gaps[4] == 4  # never drawn: the whole history's span, as in /stats/gaps


def test_runner_up_triples_are_exactly_max_minus_one():
    triples = runner_up_triples(MS, HISTORY)
    assert (1, 2, 3) not in triples  # MAX itself is left out
    assert (1, 2, 10) in triples and (12, 22, 58) in triples
    assert len(triples) == 4 * 20 - 2  # 20 triples per draw, (1, 2, 3) counted once instead of twice


def test_no_runner_up_when_max_is_one():
    assert runner_up_triples(MS, draws((1, 2, 3, 4, 5, 6))) == []


def test_the_triple_with_the_largest_summed_absence_wins():
    gaps = {1: 40, 2: 5, 3: 9, 4: 7}
    triples = [(1, 2, 3), (1, 3, 4), (2, 3, 4)]
    assert absent_triple([1], triples, gaps, random.Random(0)) == (1, 3, 4)  # 56 against 54


def test_only_the_most_absent_ball_with_a_triple_counts():
    gaps = {1: 50, 2: 40, 3: 0, 4: 0, 5: 0}
    # 1 has no triple; 2 has, and the search stops there even though (1, ...) would sum more
    assert absent_triple([1, 2], [(2, 3, 4), (3, 4, 5)], gaps, random.Random(0)) == (2, 3, 4)
    assert absent_triple([1], [(2, 3, 4)], gaps, random.Random(0)) is None


def test_a_tie_on_the_sum_is_drawn_and_repeatable():
    gaps = {1: 40, 2: 5, 3: 5}
    tied = [(1, 2, 9), (1, 3, 9)]
    gaps[9] = 0
    picks = {absent_triple([1], tied, gaps, random.Random(seed)) for seed in range(20)}
    assert picks == set(tied)
    assert absent_triple([1], tied, gaps, random.Random(7)) == absent_triple(
        [1], tied, gaps, random.Random(7)
    )


def test_lone_position_by_count_value():
    counts = {1: 10, 2: 10, 3: 9, 4: 8, 5: 8, 6: 7}
    assert lone_at_or_after(counts, 1) == 3  # 1 and 2 share the 1st; 3 is alone at the 2nd
    assert lone_at_or_after(counts, 2) == 3
    assert lone_at_or_after(counts, 3) == 6  # 4 and 5 share the 3rd
    assert lone_at_or_after({1: 5, 2: 5, 3: 4, 4: 4}, 2) is None  # skipped


# ---------------------------------------------------------------- the whole bet


def test_balls_missing_from_the_recent_window_come_first():
    # 4 contests: every never-drawn ball missed the whole window, most absent first, then by ball
    assert guess() == (4, 5, 6, 7, 8, 9)
    assert guess([]) == (1, 2, 3, 4, 5, 6)


def test_k_above_the_minimum():
    assert len(guess(k=20)) == 20


def test_same_history_same_bet():
    assert guess() == guess()
    assert ORACULOTO.ref == "guess_oraculoto@2"


@pytest.fixture(scope="module")
def real_history(imported):
    engine, _ = imported
    with engine.connect() as conn:
        game = get_game(conn, "megasena")
        return game, load_history(conn, game, 3072)


def test_the_bet_on_3073(real_history):
    game, history = real_history
    # 0: nothing missed the last 52 (the longest absence is 45).
    # 1-3: 34 (45) is the most absent; of its 4 triples seen 7 times (MAX 8), (8, 23, 34) sums most.
    # 5: last 52: 16 and 43 share the 1st count (11); 11 is alone at the 2nd (10).
    # 6: 34 is alone at the top of the absences, but it's already in: skipped.
    # 7: the hottest, 58 then 27.
    assert ORACULOTO.guess(game, history, 6, {}) == (8, 11, 23, 27, 34, 58)


# ---------------------------------------------------------------- heat


def test_heat_is_recent_minus_the_balls_own_rate():
    scores = heat(MS, recent={1: 5, 2: 1}, overall={1: 20, 2: 20, 3: 4}, contests=200, window=100)
    assert (
        scores[1] == pytest.approx(-5) and scores[2] == pytest.approx(-9) and scores[3] == pytest.approx(-2)
    )
    assert scores[60] == 0 and len(scores) == 60


def test_heat_from_history_uses_the_last_window():
    history = draws((1, 2, 3, 4, 5, 6), (1, 2, 3, 4, 5, 6), (7, 8, 9, 10, 11, 12))
    scores = heat_from_history(MS, history, window=1)
    assert scores[7] == pytest.approx(1 - 1 / 3) and scores[1] == pytest.approx(-2 / 3)
    assert ranked(scores)[:6] == [7, 8, 9, 10, 11, 12]
