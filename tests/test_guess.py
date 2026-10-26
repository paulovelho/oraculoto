"""Guess functions and backtests without a database: contract, params, reference rules, chance math."""

from datetime import date, timedelta

import pytest

from oraculoto.db.draws import Game
from oraculoto.guess import REGISTRY, GuessContractError, GuessFunction, Param, PastDraw
from oraculoto.guess.backtest import backtest, expected_hits, hit_probability, hits_variance, wins_tier

MS = Game(1, "megasena", "Mega-Sena", 6, 1, 60, 4, 6, 20)


def draws(*balls: tuple[int, ...]) -> list[PastDraw]:
    start = date(2000, 1, 1)
    return [PastDraw(i + 1, start + timedelta(days=i), tuple(sorted(b)), None) for i, b in enumerate(balls)]


HISTORY = draws(
    (1, 2, 3, 4, 5, 6),
    (1, 2, 3, 10, 11, 12),
    (1, 2, 20, 21, 22, 23),
    (1, 30, 31, 32, 33, 34),
)


def run(key: str, history=HISTORY, k: int = 6, **params) -> tuple[int, ...]:
    f = REGISTRY[key]
    return f.guess(MS, history, k, f.resolve_params({n: str(v) for n, v in params.items()}))


# ---------------------------------------------------------------- reference functions


def test_registry():
    assert [f.ref for f in REGISTRY.values()] == ["hot@1", "hot_recent@1", "overdue@1", "repeat_last@1"]


def test_hot_ties_go_to_the_lower_ball():
    # 1 ×4, 2 ×3, 3 ×2, then everything drawn once: 4, 5, 6 are the lowest of those
    assert run("hot") == (1, 2, 3, 4, 5, 6)


def test_hot_recent_counts_only_the_last_draws():
    assert run("hot_recent", last=2) == (1, 2, 20, 21, 22, 23)
    assert run("hot_recent") == run("hot")  # 200 > the whole history


def test_overdue():
    # never drawn first (7, 8, 9, 13, ...), lower ball on ties
    assert run("overdue") == (7, 8, 9, 13, 14, 15)
    seen_everything = draws(*[tuple(range(b, b + 6)) for b in range(1, 56, 6)])
    assert run("overdue", seen_everything) == (1, 2, 3, 4, 5, 6)


def test_repeat_last():
    assert run("repeat_last") == (1, 30, 31, 32, 33, 34)
    # k > 6: the draw before it fills in, newest first, lower balls first within a draw
    assert run("repeat_last", k=8) == (1, 2, 20, 30, 31, 32, 33, 34)
    assert run("repeat_last", [], k=6) == (1, 2, 3, 4, 5, 6)


@pytest.mark.parametrize("key", list(REGISTRY))
@pytest.mark.parametrize("k", [6, 20])
def test_every_function_keeps_the_contract(key, k):
    for n in range(len(HISTORY) + 1):  # including an empty history
        assert len(set(run(key, HISTORY[:n], k=k))) == k


# ---------------------------------------------------------------- contract and params


def test_contract_violations_are_caught():
    def bad(result):
        return GuessFunction("bad", 1, "", lambda game, history, k, params: result)

    for result in (
        [1, 2, 3, 4, 5],
        [1, 1, 2, 3, 4, 5],
        [0, 1, 2, 3, 4, 5],
        [1, 2, 3, 4, 5, 61],
        [1, 2, 3, 4, 5, 6.0],
    ):
        with pytest.raises(GuessContractError, match="bad@1 broke the contract for contest 5"):
            bad(result).guess(MS, HISTORY, 6, {})


def test_params():
    f = GuessFunction(
        "p",
        1,
        "",
        lambda *a: [],
        (Param("n", int, 3, "", min=1, max=10), Param("w", float, 0.5, ""), Param("on", bool, False, "")),
    )
    assert f.resolve_params({}) == {"n": 3, "w": 0.5, "on": False}
    assert f.resolve_params({"n": "10", "w": "2", "on": "true"}) == {"n": 10, "w": 2.0, "on": True}
    for raw, message in [
        ({"n": "11"}, "n: must be <= 10"),
        ({"n": "0"}, "n: must be >= 1"),
        ({"n": "x"}, "n: expected int"),
        ({"on": "yes"}, "on: expected true or false"),
        ({"nope": "1"}, "p has no parameter 'nope'"),
    ]:
        with pytest.raises(ValueError, match=message):
            f.resolve_params(raw)


# ---------------------------------------------------------------- backtest and chance


def test_backtest_never_shows_the_target():
    seen = []

    def spy(game, history, k, params):
        seen.append(history[-1].contest if history else 0)
        return [1, 2, 3, 4, 5, 6]

    r = backtest(MS, HISTORY, GuessFunction("spy", 1, "", spy), 6, {}, 2, 4)
    assert seen == [1, 2, 3]  # targets 2, 3 and 4 each saw only the contests before them
    assert (r.first_contest, r.last_contest, r.draws) == (2, 4, 3)
    # guesses 1-6 against draws 2, 3, 4: 3, 2 and 1 hits
    assert r.hits == {0: 0, 1: 1, 2: 1, 3: 1, 4: 0, 5: 0, 6: 0} and r.average_hits == 2.0
    assert r.tiers == {6: 0, 5: 0, 4: 0}


def test_empty_backtest():
    r = backtest(MS, HISTORY, REGISTRY["hot"], 6, {}, 10, 20)
    assert (r.first_contest, r.draws, r.average_hits, r.z_score(MS)) == (None, 0, None, None)


def test_chance():
    assert hit_probability(MS, 6, 6) == 1 / 50_063_860
    assert sum(hit_probability(MS, 9, h) for h in range(7)) == pytest.approx(1)
    assert expected_hits(MS, 6) == pytest.approx(0.6)
    # §5: the standard error over 2,072 draws "is about 0.015"
    assert (hits_variance(MS, 6) / 2072) ** 0.5 == pytest.approx(0.01544, abs=1e-5)
    # docs/api.md §6: k=6 with 5 hits wins no 4-hit combination; k=8 with 4 hits wins six of them
    assert not wins_tier(MS, 6, 5, 4) and wins_tier(MS, 8, 4, 4)
    assert wins_tier(MS, 7, 6, 5) and wins_tier(MS, 7, 6, 6)
