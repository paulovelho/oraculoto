"""`guess_oraculoto` and the heat function (docs/api.md §11). Only the real-file bet needs the database."""

from datetime import date, timedelta

import pytest

from oraculoto.db.draws import Game, get_game
from oraculoto.db.results import load_history
from oraculoto.guess.base import PastDraw
from oraculoto.guess.heat import heat, heat_from_history, ranked
from oraculoto.guess.oraculoto import (
    CONFIG,
    ORACULOTO,
    ConfigError,
    absent_triple,
    current_gaps,
    explain_oraculoto,
    load_config,
    lone_at_or_after,
    parse_config,
    parse_config_text,
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
    triples = runner_up_triples(HISTORY)
    assert (1, 2, 3) not in triples  # MAX itself is left out
    assert (1, 2, 10) in triples and (12, 22, 58) in triples
    assert len(triples) == 4 * 20 - 2  # 20 triples per draw, (1, 2, 3) counted once instead of twice


def test_no_runner_up_when_max_is_one():
    assert runner_up_triples(draws((1, 2, 3, 4, 5, 6))) == []


def test_the_triple_with_the_largest_summed_absence_wins():
    gaps = {1: 40, 2: 5, 3: 9, 4: 7}
    triples = [(1, 2, 3), (1, 3, 4), (2, 3, 4)]
    assert absent_triple([1], triples, gaps) == (1, 3, 4)  # 56 against 54


def test_only_the_most_absent_ball_with_a_triple_counts():
    gaps = {1: 50, 2: 40, 3: 0, 4: 0, 5: 0}
    # 1 has no triple; 2 has, and the search stops there even though (1, ...) would sum more
    assert absent_triple([1, 2], [(2, 3, 4), (3, 4, 5)], gaps) == (2, 3, 4)
    assert absent_triple([1], [(2, 3, 4)], gaps) is None


def test_a_tie_on_the_sum_goes_to_the_lowest_triple():
    gaps = {1: 40, 2: 5, 3: 5, 9: 0}
    assert absent_triple([1], [(1, 3, 9), (1, 2, 9)], gaps) == (1, 2, 9)


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
    assert ORACULOTO.ref == "guess_oraculoto@3"


def test_the_explanation_is_the_bet():
    ex = explain_oraculoto(MS, HISTORY, 6)
    assert tuple(sorted(ex.numbers)) == guess()
    assert [b for s in ex.steps for b in s.added] == ex.numbers  # every ball is owned by one step
    assert [s.number for s in ex.steps] == ["0", "1", "2", "3", "4"]  # 4 configured steps + heat


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


# ---------------------------------------------------------------- the config


def config(*steps: dict, version: int = 9) -> dict:
    return {"version": version, "step": list(steps)}


MISSING = {"type": "missing", "window": 52}
TRIPLE = {"type": "absent_triple", "absent_over": 30, "offset": 1, "fallback": True}
FREQUENT = {"type": "lone_position", "measure": "count", "window": 52, "start": 2}


def test_the_shipped_config_is_the_version_on_record():
    assert load_config() == CONFIG
    assert ORACULOTO.ref == f"guess_oraculoto@{CONFIG.version}"
    assert [s.type for s in CONFIG.steps] == ["missing", "absent_triple", "lone_position", "lone_position"]


# 1, 2, 3 came out 4 times (1st); 4 alone at 3 times (2nd); 13-60 never: missing from the window.
ORDERED = draws((1, 2, 3, 4, 5, 6), (1, 2, 3, 4, 5, 7), (1, 2, 3, 4, 8, 9), (1, 2, 3, 10, 11, 12))


def test_steps_run_in_the_configured_order():
    missing_first = explain_oraculoto(MS, ORDERED, 6, parse_config(config(MISSING, FREQUENT)))
    assert missing_first.numbers == [13, 14, 15, 16, 17, 18]  # full before the frequent step runs
    assert missing_first.steps[1].notes[-1].startswith("bet already full")

    frequent_first = explain_oraculoto(MS, ORDERED, 6, parse_config(config(FREQUENT, MISSING)))
    assert frequent_first.numbers == [4, 13, 14, 15, 16, 17]
    assert [s.number for s in frequent_first.steps] == ["0", "1", "2"]  # heat last, always


def test_a_step_type_can_repeat_with_other_options():
    third = {**FREQUENT, "start": 3}  # 5 alone at 2 times
    ex = explain_oraculoto(MS, ORDERED, 6, parse_config(config(FREQUENT, third)))
    assert ex.numbers[:2] == [4, 5]


def test_options_change_the_bet():
    wide = explain_oraculoto(MS, ORDERED, 60, parse_config(config(MISSING)))
    assert len(wide.steps[0].added) == 60 - 12  # 13-60
    # window 1: only the last draw counts, so 4-9 are missing too, after 13-60 (less absent)
    narrow = explain_oraculoto(MS, ORDERED, 60, parse_config(config({**MISSING, "window": 1})))
    assert len(narrow.steps[0].added) == 60 - 6 and narrow.steps[0].added[-6:] == [6, 5, 7, 4, 8, 9]


def test_no_steps_is_pure_heat():
    ex = explain_oraculoto(MS, HISTORY, 6, parse_config(config()))
    assert [s.title for s in ex.steps] == ["hottest balls not yet in, until the bet is full"]
    assert len(ex.numbers) == 6


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"step": []}, "version"),
        (config(version=0), "version"),
        ({**config(), "extra": 1}, "unknown key"),
        (config({"type": "nope"}), "unknown type 'nope'"),
        (config({"type": "missing"}), "missing window"),
        (config({**MISSING, "size": 3}), "unknown option size"),
        (config({**MISSING, "window": 0}), "at least 1"),
        (config({**MISSING, "window": True}), "must be int"),
        (config({**TRIPLE, "fallback": 1}), "must be bool"),
        (config({**FREQUENT, "measure": "heat"}), "one of count, absence"),
    ],
)
def test_a_wrong_config_is_refused(data, message):
    with pytest.raises(ConfigError, match=message):
        parse_config(data)


def test_a_config_from_text_names_its_source():
    assert parse_config_text("version = 7\n", "stdin") == parse_config(config(version=7))
    with pytest.raises(ConfigError, match="^stdin: version"):
        parse_config_text("version = 0\n", "stdin")


def test_a_broken_file_is_refused(tmp_path):
    path = tmp_path / "oraculoto.toml"
    path.write_text("version = 3\n[[step]\n")
    with pytest.raises(ConfigError, match="oraculoto.toml"):
        load_config(path)


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
