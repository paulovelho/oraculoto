"""Statistics over a window: last=N contests or from/to, default the whole history (docs/api.md §4, Stats).

Every response carries the window it covered and what a fair draw would give, so a number
never shows up without its baseline.
"""

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import Connection

from oraculoto.api.deps import Paging, WindowParams, get_conn, get_game, paging, window_params
from oraculoto.api.envelope import ApiError, day, ok, page_of
from oraculoto.db import stats
from oraculoto.db.draws import Game
from oraculoto.guess.heat import HEAT_VERSION, HEAT_WINDOW, heat, ranked

router = APIRouter(prefix="/games/{game}/stats", tags=["stats"])

# /heat only changes when a contest arrives, so browsers may keep it for an hour without asking,
# then revalidate with the ETag. A 304 still starts Python (CGI); only max-age saves that.
HEAT_MAX_AGE = 3600


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


@router.get(
    "/heat", summary=f"per ball: times in the last {HEAT_WINDOW} contests minus what its own rate predicts"
)
def heat_scores(
    request: Request, game: Game = Depends(get_game), conn: Connection = Depends(get_conn)
) -> Response:
    """Fixed window, no window parameters: one answer per latest contest, which is what lets it be cached."""
    overall = stats.resolve_window(conn, game)
    etag = f'W/"heat@{HEAT_VERSION}-{game.slug}-{overall.last_contest or 0}"'
    headers = {"ETag": etag, "Cache-Control": f"private, max-age={HEAT_MAX_AGE}"}
    if etag in request.headers.get("if-none-match", ""):
        return Response(status_code=304, headers=headers)
    recent = stats.resolve_window(conn, game, last=HEAT_WINDOW)
    recent_counts = dict(stats.frequency(conn, game, recent))
    overall_counts = dict(stats.frequency(conn, game, overall))
    scores = heat(game, recent_counts, overall_counts, overall.draws, recent.draws)
    response = ok(
        {
            "window": window_json(recent),
            "history": window_json(overall),
            "version": HEAT_VERSION,
            "items": [
                {
                    "ball": b,
                    "heat": round(scores[b], 2),
                    "recent": recent_counts[b],
                    "overall": overall_counts[b],
                }
                for b in ranked(scores)
            ],
        }
    )
    response.headers.update(headers)
    return response
