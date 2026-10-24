"""Statistics over a window: last=N contests or from/to, default the whole history (docs/api.md §4, Stats).

Every response carries the window it covered and what a fair draw would give, so a number
never shows up without its baseline.
"""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import Connection

from oraculoto.api.auth import require_user
from oraculoto.api.deps import Paging, WindowParams, get_conn, get_game, paging, window_params
from oraculoto.api.envelope import ApiError, day, ok, page_of
from oraculoto.db import stats
from oraculoto.db.draws import Game

router = APIRouter(prefix="/games/{game}/stats", tags=["stats"], dependencies=[Depends(require_user)])


def _window(conn: Connection, game: Game, wp: WindowParams) -> stats.Window:
    return stats.resolve_window(conn, game, last=wp.last, first=wp.first_contest, to=wp.last_contest)


def window_json(w: stats.Window) -> dict:
    return {"from": w.first_contest, "to": w.last_contest, "draws": w.draws}


def parse_balls(raw: str, game: Game) -> list[int]:
    try:
        balls = [int(part) for part in raw.split(",") if part.strip()]
    except ValueError:
        raise ApiError(
            400, "invalid_input", f"balls: expected comma-separated numbers, got {raw!r}"
        ) from None
    if not 1 <= len(balls) <= game.balls_drawn:
        raise ApiError(400, "invalid_input", f"balls: give 1 to {game.balls_drawn} balls")
    if len(set(balls)) != len(balls):
        raise ApiError(400, "invalid_input", "balls: repeated ball")
    if any(b < game.ball_min or b > game.ball_max for b in balls):
        raise ApiError(400, "invalid_input", f"balls: must be within {game.ball_min}-{game.ball_max}")
    return sorted(balls)


@router.get("/frequency", summary="how often each ball was drawn, plus the fair-draw expectation")
def frequency(
    game: Game = Depends(get_game),
    conn: Connection = Depends(get_conn),
    wp: WindowParams = Depends(window_params),
) -> JSONResponse:
    w = _window(conn, game, wp)
    return ok(
        {
            "window": window_json(w),
            "expected": round(stats.expected_frequency(game, w), 2),
            "items": [{"ball": ball, "times": times} for ball, times in stats.frequency(conn, game, w)],
        }
    )


@router.get("/together", summary="contests that drew all the given balls")
def together(
    balls: str = Query(description="1 to balls_drawn distinct balls, comma-separated, e.g. 10,53"),
    jackpot: bool = Query(False, description="only contests where the jackpot was won"),
    game: Game = Depends(get_game),
    conn: Connection = Depends(get_conn),
    wp: WindowParams = Depends(window_params),
    pg: Paging = Depends(paging),
) -> JSONResponse:
    wanted = parse_balls(balls, game)
    w = _window(conn, game, wp)
    found = stats.together(conn, game, w, wanted, jackpot=jackpot)
    considered = stats.jackpot_draws(conn, game, w) if jackpot else w.draws
    items = [{"contest": c, "date": day(d)} for c, d in found[pg.offset : pg.offset + pg.limit]]
    return ok(
        {
            "window": window_json(w),
            "balls": wanted,
            "jackpot": jackpot,
            # over the contests considered (all, or the jackpot ones), if the balls were independent of it
            "expected": round(considered * stats.chance_all_drawn(game, len(wanted)), 2),
            "last": {"contest": found[0][0], "date": day(found[0][1])} if found else None,
            **page_of(items, pg.page, pg.limit, len(found)),
        }
    )


@router.get("/pairs", summary="most frequent pairs (size=2) or triples (size=3)")
def pairs(
    size: int = Query(2, ge=2, le=3),
    top: int = Query(20, ge=1, le=100),
    game: Game = Depends(get_game),
    conn: Connection = Depends(get_conn),
    wp: WindowParams = Depends(window_params),
) -> JSONResponse:
    w = _window(conn, game, wp)
    return ok(
        {
            "window": window_json(w),
            "size": size,
            "expected": round(stats.expected_combination(game, w, size), 2),
            "items": [
                {"balls": list(b), "times": t} for b, t in stats.combinations(conn, game, w, size, top)
            ],
        }
    )


@router.get("/gaps", summary="per ball: last contest drawn, current absence, longest absence")
def gaps(
    game: Game = Depends(get_game),
    conn: Connection = Depends(get_conn),
    wp: WindowParams = Depends(window_params),
) -> JSONResponse:
    w = _window(conn, game, wp)
    return ok(
        {
            "window": window_json(w),
            "expected_gap": round(stats.expected_gap(game), 2),
            "items": [
                {
                    "ball": g.ball,
                    "last_seen": g.last_seen,
                    "current_gap": g.current_gap,
                    "longest_gap": g.longest_gap,
                }
                for g in stats.gaps(conn, game, w)
            ],
        }
    )
