"""Statistics over a window of contests: the queries of docs/database.md §6, plus what chance expects.

Every function takes a resolved `Window`. A window that holds no draws gives zero counts,
not an error.
"""

from dataclasses import dataclass
from datetime import date
from math import comb

from sqlalchemy import Connection, bindparam, text

from oraculoto.db.draws import Game


@dataclass(frozen=True)
class Window:
    first_contest: int | None  # the first and last contests actually present; None when empty
    last_contest: int | None
    draws: int

    @property
    def params(self) -> dict[str, int]:
        return {"lo": self.first_contest or 0, "hi": self.last_contest or 0}


def pool_size(game: Game) -> int:
    return game.ball_max - game.ball_min + 1


def resolve_window(
    conn: Connection, game: Game, last: int | None = None, first: int | None = None, to: int | None = None
) -> Window:
    """`last` N contests, or contests `first`..`to` (either end open), or the whole history."""
    if last is not None:
        first = conn.execute(
            text(
                "SELECT contest_number FROM draws WHERE game_id = :g"
                " ORDER BY contest_number DESC LIMIT 1 OFFSET :skip"
            ),
            {"g": game.id, "skip": last - 1},
        ).scalar()
        to = None
    lo, hi, n = conn.execute(
        text(
            "SELECT MIN(contest_number), MAX(contest_number), COUNT(*) FROM draws"
            " WHERE game_id = :g AND contest_number >= :lo AND contest_number <= :hi"
        ),
        {"g": game.id, "lo": first or 1, "hi": to or 2**31 - 1},
    ).one()
    return Window(lo, hi, n)


def frequency(conn: Connection, game: Game, w: Window) -> list[tuple[int, int]]:
    """(ball, times) for every ball in the game's range, zeros included; most frequent first."""
    counts = dict(
        conn.execute(
            text(
                "SELECT b.ball, COUNT(*) FROM draw_balls b JOIN draws d ON d.id = b.draw_id"
                " WHERE d.game_id = :g AND d.contest_number BETWEEN :lo AND :hi GROUP BY b.ball"
            ),
            {"g": game.id, **w.params},
        ).all()
    )
    rows = [(ball, counts.get(ball, 0)) for ball in range(game.ball_min, game.ball_max + 1)]
    return sorted(rows, key=lambda r: (-r[1], r[0]))


def expected_frequency(game: Game, w: Window) -> float:
    return w.draws * game.balls_drawn / pool_size(game)


_JACKPOT = (
    " AND EXISTS (SELECT 1 FROM draw_prizes p WHERE p.draw_id = d.id AND p.hits = :top AND p.winners > 0)"
)


def together(
    conn: Connection, game: Game, w: Window, balls: list[int], jackpot: bool = False
) -> list[tuple[int, date]]:
    """(contest, date) of every contest that drew all of `balls`, newest first.

    With `jackpot`, only contests where someone hit the top tier.
    """
    sql = (
        "SELECT d.contest_number, d.draw_date FROM draws d JOIN draw_balls b ON b.draw_id = d.id"
        " WHERE d.game_id = :g AND d.contest_number BETWEEN :lo AND :hi AND b.ball IN :balls"
        + (_JACKPOT if jackpot else "")
        + " GROUP BY d.id, d.contest_number, d.draw_date HAVING COUNT(*) = :n ORDER BY d.contest_number DESC"
    )
    query = text(sql).bindparams(bindparam("balls", expanding=True))
    params = {"g": game.id, **w.params, "balls": balls, "n": len(balls), "top": game.balls_drawn}
    return [(c, d) for c, d in conn.execute(query, params)]


def jackpot_draws(conn: Connection, game: Game, w: Window) -> int:
    """How many contests in the window had at least one top-tier winner."""
    return conn.execute(
        text(
            "SELECT COUNT(*) FROM draws d WHERE d.game_id = :g AND d.contest_number BETWEEN :lo AND :hi"
            + _JACKPOT
        ),
        {"g": game.id, **w.params, "top": game.balls_drawn},
    ).scalar_one()


def chance_all_drawn(game: Game, n: int) -> float:
    """Probability that one draw contains n given balls."""
    pool, k = pool_size(game), game.balls_drawn
    return comb(pool - n, k - n) / comb(pool, k)


def combinations(
    conn: Connection, game: Game, w: Window, size: int, top: int
) -> list[tuple[tuple[int, ...], int]]:
    """The `top` most frequent pairs (size 2) or triples (size 3): (balls, times), ties by lowest balls."""
    if size not in (2, 3):
        raise ValueError("size must be 2 or 3")
    cols = "a.ball, b.ball" + (", c.ball" if size == 3 else "")
    third = " JOIN draw_balls c ON c.draw_id = a.draw_id AND c.ball > b.ball" if size == 3 else ""
    rows = conn.execute(
        text(
            f"SELECT {cols}, COUNT(*) AS times FROM draw_balls a"
            " JOIN draw_balls b ON b.draw_id = a.draw_id AND b.ball > a.ball"
            f"{third} JOIN draws d ON d.id = a.draw_id"
            " WHERE d.game_id = :g AND d.contest_number BETWEEN :lo AND :hi"
            f" GROUP BY {cols} ORDER BY times DESC, {cols} LIMIT :top"
        ),
        {"g": game.id, **w.params, "top": top},
    ).all()
    return [(tuple(r[:size]), r[size]) for r in rows]


def expected_combination(game: Game, w: Window, size: int) -> float:
    """How often any given pair or triple turns up by chance over the window."""
    return w.draws * comb(game.balls_drawn, size) / comb(pool_size(game), size)


@dataclass(frozen=True)
class BallGap:
    ball: int
    last_seen: int | None  # last contest in the window that drew it
    current_gap: int  # contests since then, up to the window's end (0 = drawn in the last one)
    longest_gap: int | None  # longest run between two appearances inside the window


def gaps(conn: Connection, game: Game, w: Window) -> list[BallGap]:
    """Per ball, longest current absence first.

    As in docs/database.md §6, `longest_gap` only counts runs between two appearances, so a
    current absence longer than any earlier one doesn't show there. A ball never drawn in the
    window has been absent for the whole window and has no longest gap.
    """
    found = {
        ball: (last_seen, longest)
        for ball, last_seen, longest in conn.execute(
            text(
                "SELECT ball, MAX(contest_number), MAX(gap) FROM ("
                " SELECT b.ball, d.contest_number, d.contest_number"
                "  - LAG(d.contest_number) OVER (PARTITION BY b.ball ORDER BY d.contest_number) - 1 AS gap"
                " FROM draw_balls b JOIN draws d ON d.id = b.draw_id"
                " WHERE d.game_id = :g AND d.contest_number BETWEEN :lo AND :hi"
                ") t GROUP BY ball"
            ),
            {"g": game.id, **w.params},
        )
    }
    rows = []
    for ball in range(game.ball_min, game.ball_max + 1):
        last_seen, longest = found.get(ball, (None, None))
        if last_seen is None:
            current = w.last_contest - w.first_contest + 1 if w.draws else 0
        else:
            current = w.last_contest - last_seen
        rows.append(BallGap(ball, last_seen, current, None if longest is None else int(longest)))
    return sorted(rows, key=lambda g: (-g.current_gap, g.ball))


def expected_gap(game: Game) -> float:
    """Average run of draws between two appearances of a ball, for a fair draw."""
    p = game.balls_drawn / pool_size(game)
    return (1 - p) / p
