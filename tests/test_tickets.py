"""Ticket rules and scoring (docs/api.md §4 and §6), without a database."""

from collections import Counter
from decimal import Decimal
from itertools import combinations

import pytest

from oraculoto.db.draws import Game
from oraculoto.tickets import TicketError, check_contests, check_numbers, score, winning_combinations

MEGA = Game(1, "megasena", "Mega-Sena", 6, 1, 60, 4, 6, 20)
PRIZES = {6: Decimal("1000000.00"), 5: Decimal("40000.00"), 4: Decimal("500.00")}


@pytest.mark.parametrize("k", range(6, 21))
def test_combinations_match_brute_force(k):
    """Every 6-number game inside a k-number ticket, counted by how many it hits."""
    ticket = list(range(1, k + 1))
    for hits in range(0, 7):
        drawn = set(ticket[:hits]) | set(range(55, 55 + 6 - hits))
        counted = Counter(len(drawn & set(c)) for c in combinations(ticket, 6))
        expected = [(j, counted[j]) for j in (6, 5, 4) if counted[j]]
        assert winning_combinations(MEGA, k, hits) == expected, (k, hits)


def test_the_examples_in_the_docs():
    assert winning_combinations(MEGA, 6, 4) == [(4, 1)]
    assert winning_combinations(MEGA, 7, 6) == [(6, 1), (5, 6)]
    assert winning_combinations(MEGA, 8, 4) == [(4, 6)]
    assert winning_combinations(MEGA, 6, 3) == []


def test_score():
    s = score(MEGA, [1, 2, 3, 4, 5, 6, 7], [1, 2, 3, 4, 5, 6], PRIZES)
    assert (s.hits, s.matched) == (6, (1, 2, 3, 4, 5, 6))
    assert [(w.hits, w.combinations, w.amount) for w in s.wins] == [
        (6, 1, Decimal("1000000.00")),
        (5, 6, Decimal("240000.00")),
    ]
    assert s.total == Decimal("1240000.00")

    nothing = score(MEGA, [1, 2, 3, 4, 5, 6], [1, 2, 3, 40, 50, 60], PRIZES)
    assert (nothing.hits, nothing.wins, nothing.total) == (3, (), Decimal("0.00"))

    unknown = score(MEGA, [1, 2, 3, 4, 5, 6], [1, 2, 3, 4, 50, 60], {6: PRIZES[6]})
    assert unknown.wins[0].amount is None and unknown.total is None  # NULL means unknown


def test_check_numbers():
    assert check_numbers(MEGA, [60, 1, 30, 2, 3, 4]) == (1, 2, 3, 4, 30, 60)
    assert len(check_numbers(MEGA, list(range(1, 21)))) == 20
    for bad, message in [
        ([1, 2, 3, 4, 5], "6-20 numbers, got 5"),
        (list(range(1, 22)), "got 21"),
        ([1, 1, 2, 3, 4, 5], "repeated"),
        ([0, 1, 2, 3, 4, 5], "0 is outside 1-60"),
        ([1, 2, 3, 4, 5, 61], "61 is outside"),
    ]:
        with pytest.raises(TicketError, match=message):
            check_numbers(MEGA, bad)


def test_check_contests():
    assert check_contests(3000, None, 52) == (3000, 3000)
    assert check_contests(3000, 3051, 52) == (3000, 3051)
    with pytest.raises(TicketError, match="at most 52 contests, got 53"):
        check_contests(3000, 3052, 52)
    with pytest.raises(TicketError, match="before"):
        check_contests(3000, 2999, 52)
    with pytest.raises(TicketError, match="1-999999"):
        check_contests(0, None, 52)
