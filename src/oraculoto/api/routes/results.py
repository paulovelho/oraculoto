"""Games and their draws (docs/api.md §4, Results)."""

from datetime import date

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse
from sqlalchemy import Connection, select

from oraculoto.api.auth import require_user
from oraculoto.api.deps import Paging, get_conn, get_game, paging
from oraculoto.api.envelope import ApiError, day, money, ok, page_of
from oraculoto.db.draws import Game
from oraculoto.db.results import DrawFilter, DrawRecord, get_draw, latest_draw, list_draws
from oraculoto.db.schema import games

router = APIRouter(tags=["results"], dependencies=[Depends(require_user)])


def game_json(game: Game) -> dict:
    return {
        "slug": game.slug,
        "name": game.name,
        "balls_drawn": game.balls_drawn,
        "ball_min": game.ball_min,
        "ball_max": game.ball_max,
        "prize_tiers": game.prize_tiers,
        "bet_min_numbers": game.bet_min_numbers,
        "bet_max_numbers": game.bet_max_numbers,
    }


def draw_json(d: DrawRecord) -> dict:
    return {
        "contest": d.contest_number,
        "date": day(d.draw_date),
        "balls": list(d.balls),
        "draw_order": None if d.draw_order is None else list(d.draw_order),
        "prizes": [
            {"hits": p.hits, "winners": p.winners, "prize_per_winner": money(p.prize_per_winner)}
            for p in d.prizes
        ],
        "winner_locations": [
            {
                "city": loc.city,
                "uf": loc.uf,
                "is_online": loc.is_online,
                "winners": loc.winners,
                "raw": loc.raw,
            }
            for loc in d.locations
        ],
        "total_collected": money(d.total_collected),
        "rollover_amount": money(d.rollover_amount),
        "next_estimated_prize": money(d.next_estimated_prize),
        "special_accumulated": money(d.special_accumulated),
        "notes": d.notes,
        "is_special": d.is_special,
        "source": d.source,
    }


@router.get("/games", summary="games and their rules")
def list_games(conn: Connection = Depends(get_conn)) -> JSONResponse:
    rows = conn.execute(select(games).order_by(games.c.id)).mappings().all()
    return ok([game_json(Game(**{k: r[k] for k in Game.__dataclass_fields__})) for r in rows])


def _draws_page(conn: Connection, game: Game, pg: Paging, flt: DrawFilter) -> JSONResponse:
    records, total = list_draws(conn, game, flt, pg.limit, pg.offset)
    return ok(page_of([draw_json(r) for r in records], pg.page, pg.limit, total))


@router.get("/games/{game}/draws", summary="contests, newest first, by contest number")
def draws_page(
    game: Game = Depends(get_game),
    conn: Connection = Depends(get_conn),
    pg: Paging = Depends(paging),
    from_: int | None = Query(None, alias="from", ge=1, description="first contest number"),
    to: int | None = Query(None, ge=1, description="last contest number"),
) -> JSONResponse:
    if from_ is not None and to is not None and from_ > to:
        raise ApiError(400, "invalid_input", f"from ({from_}) is after to ({to})")
    return _draws_page(conn, game, pg, DrawFilter(first_contest=from_, last_contest=to))


# This and /latest are declared before /draws/{contest}, which would otherwise try to read them as numbers.
@router.get("/games/{game}/draws/by-date", summary="contests, newest first, by draw date")
def draws_by_date(
    game: Game = Depends(get_game),
    conn: Connection = Depends(get_conn),
    pg: Paging = Depends(paging),
    from_: date | None = Query(None, alias="from", description="first draw date, YYYY-MM-DD"),
    to: date | None = Query(None, description="last draw date, YYYY-MM-DD"),
) -> JSONResponse:
    if from_ is not None and to is not None and from_ > to:
        raise ApiError(400, "invalid_input", f"from ({from_}) is after to ({to})")
    return _draws_page(conn, game, pg, DrawFilter(date_from=from_, date_to=to))


@router.get("/games/{game}/draws/latest", summary="the latest contest")
def draw_latest(game: Game = Depends(get_game), conn: Connection = Depends(get_conn)) -> JSONResponse:
    record = latest_draw(conn, game)
    if record is None:
        raise ApiError(404, "not_found", f"no {game.slug} contests yet")
    return ok(draw_json(record))


@router.get("/games/{game}/draws/{contest}", summary="one contest")
def draw_one(
    contest: int = Path(ge=1), game: Game = Depends(get_game), conn: Connection = Depends(get_conn)
) -> JSONResponse:
    record = get_draw(conn, game, contest)
    if record is None:
        raise ApiError(404, "not_found", f"{game.slug} contest {contest} not found")
    return ok(draw_json(record))
