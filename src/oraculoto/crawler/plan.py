"""`crawl-plan`: what the home fetcher should request, read from the database (docs/crawler.md §3, §6)."""

from sqlalchemy import Connection, func, select

from oraculoto.crawler.protocol import GAP_CAP, Plan
from oraculoto.db.draws import Game
from oraculoto.db.schema import draws

REFRESH = 3  # the last contests are fetched again: late prize data and corrections


def crawl_plan(
    conn: Connection, game: Game, *, backfill: bool = False, first: int | None = None, last: int | None = None
) -> Plan:
    """A normal run: refresh max-2..max, then the gap from max+1.

    A backfill: every contest in first..last (default 1..max) that isn't saved from the API yet,
    oldest first. It never goes past max; contests after that are the normal run's job.
    """
    top = conn.execute(select(func.max(draws.c.contest_number)).where(draws.c.game_id == game.id)).scalar()
    top = top or 0
    if not backfill:
        return Plan(
            game=game.slug,
            kind="crawl",
            contests=list(range(max(1, top - REFRESH + 1), top + 1)),
            gap_start=top + 1,
            cap=GAP_CAP,
        )

    lo, hi = max(1, first or 1), min(last or top, top)
    from_api = set(
        conn.execute(
            select(draws.c.contest_number).where(
                draws.c.game_id == game.id,
                draws.c.source == "api",
                draws.c.contest_number.between(lo, hi),
            )
        ).scalars()
    )
    return Plan(
        game=game.slug,
        kind="backfill",
        contests=[n for n in range(lo, hi + 1) if n not in from_api],
        cap=0,
    )
