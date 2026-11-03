"""Oraculoto's own bets and how they did (docs/api.md §4, Oraculoto, and §11). Read only:
bets are placed by the `bet` command, never through the API."""

from fastapi import APIRouter, Depends, Path
from fastapi.responses import JSONResponse
from sqlalchemy import Connection, func, select

from oraculoto.api.deps import Paging, get_conn, get_game, paging
from oraculoto.api.envelope import ApiError, day, money, ok, page_of, utc_timestamp
from oraculoto.db import bets as db
from oraculoto.db.draws import Game
from oraculoto.db.results import DrawFilter, list_draws
from oraculoto.db.schema import draws
from oraculoto.tickets import ContestScore, score

router = APIRouter(tags=["oraculoto"])


def prizes_json(s: ContestScore) -> list[dict]:
    return [
        {
            "hits": w.hits,
            "combinations": w.combinations,
            "prize_per_winner": money(w.prize_per_winner),
            "amount": money(w.amount),
        }
        for w in s.wins
    ]


def _bets_json(conn: Connection, game: Game, bets: list[db.Bet]) -> list[dict]:
    if not bets:
        return []
    first, last = min(b.contest for b in bets), max(b.contest for b in bets)
    drawn, _ = list_draws(conn, game, DrawFilter(first, last), last - first + 1, 0)
    by_contest = {d.contest_number: d for d in drawn}
    latest = conn.execute(select(func.max(draws.c.contest_number)).where(draws.c.game_id == game.id)).scalar()

    items = []
    for b in bets:
        item = {
            "contest": b.contest,
            "numbers": list(b.numbers),
            "source": b.source,
            "created_at": utc_timestamp(b.created_at),
            "status": "pending",
            "date": None,
            "hits": None,
            "matched": None,
            "prizes": [],
            "total": None,
        }
        d = by_contest.get(b.contest)
        if d is None:
            if latest is not None and b.contest < latest:
                item["status"] = "missing"  # a gap in our draws, not a future contest
        else:
            s = score(game, b.numbers, d.balls, {p.hits: p.prize_per_winner for p in d.prizes})
            item.update(
                status="drawn",
                date=day(d.draw_date),
                hits=s.hits,
                matched=list(s.matched),
                prizes=prizes_json(s),
                total=money(s.total),
            )
        items.append(item)
    return items


@router.get("/games/{game}/oraculoto", summary="oraculoto's own bets, newest contest first, with results")
def list_bets(
    game: Game = Depends(get_game), conn: Connection = Depends(get_conn), pg: Paging = Depends(paging)
) -> JSONResponse:
    found, total = db.list_bets(conn, game, pg.limit, pg.offset)
    return ok(page_of(_bets_json(conn, game, found), pg.page, pg.limit, total))


@router.get("/games/{game}/oraculoto/{contest}", summary="oraculoto's bet on one contest, with its result")
def get_bet(
    contest: int = Path(ge=1, le=999_999),
    game: Game = Depends(get_game),
    conn: Connection = Depends(get_conn),
) -> JSONResponse:
    bet = db.get_bet(conn, game, contest)
    if bet is None:
        raise ApiError(404, "not_found", f"oraculoto has no bet on #{contest}")
    return ok(_bets_json(conn, game, [bet])[0])
