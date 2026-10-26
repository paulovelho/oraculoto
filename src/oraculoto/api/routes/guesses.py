"""Guess functions and backtests (docs/api.md §4, Guesses, and §5).

GET /games/{game}/guess is not built yet: its rules are still to be defined.
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Connection

from oraculoto.api.auth import require_user
from oraculoto.api.deps import get_conn, get_game
from oraculoto.api.envelope import ApiError, ok
from oraculoto.api.routes.stats import window_json
from oraculoto.config import backtest_max_contests
from oraculoto.db import stats
from oraculoto.db.draws import Game
from oraculoto.db.results import load_history
from oraculoto.guess import REGISTRY, GuessFunction
from oraculoto.guess.backtest import BacktestResult, backtest, expected_hits

router = APIRouter(tags=["guesses"], dependencies=[Depends(require_user)])

# Query parameters of /backtest itself; anything else is a parameter of the function.
BACKTEST_QUERY = {"function", "k", "from", "to"}
DEFAULT_TARGETS = 100


def function_json(f: GuessFunction) -> dict:
    return {
        "key": f.key,
        "version": f.version,
        "ref": f.ref,
        "description": f.description,
        "params": [
            {
                "name": p.name,
                "type": p.type.__name__,
                "default": p.default,
                "min": p.min,
                "max": p.max,
                "description": p.description,
            }
            for p in f.params
        ],
    }


def sig(x: float | None) -> float | None:
    """4 significant digits: keeps tiny expectations (a jackpot is ~2e-8 per draw) readable."""
    return None if x is None else float(f"{x:.4g}")


def backtest_json(game: Game, r: BacktestResult) -> dict:
    return {
        "function": {"key": r.function.key, "version": r.function.version, "ref": r.function.ref},
        "params": r.params,
        "k": r.k,
        "window": window_json(stats.Window(r.first_contest, r.last_contest, r.draws)),
        "average_hits": sig(r.average_hits),
        "hits": [{"hits": h, "draws": n} for h, n in r.hits.items()],
        "tiers": [
            {"hits": t, "draws": n, "expected": sig(r.expected_tier(game, t))} for t, n in r.tiers.items()
        ],
        "baseline": {
            "average_hits": sig(expected_hits(game, r.k)),
            "standard_error": sig(r.standard_error(game)),
            "z_score": None if r.draws == 0 else round(r.z_score(game), 2),
        },
    }


@router.get("/functions", summary="available guess functions: key, version, description, parameters")
def list_functions() -> JSONResponse:
    return ok([function_json(f) for f in REGISTRY.values()])


@router.get(
    "/games/{game}/backtest",
    summary="how a guess function would have scored, next to chance",
    description="Any query parameter besides function, k, from and to goes to the function "
    "(see GET /functions for what each one accepts).",
)
def run_backtest(
    request: Request,
    function: str = Query(description="a key from GET /functions"),
    k: int | None = Query(None, description="numbers per guess; default: the game's minimum bet"),
    from_: int | None = Query(None, alias="from", ge=1, description="first target contest"),
    to: int | None = Query(None, ge=1, description="last target contest; default: the latest"),
    game: Game = Depends(get_game),
    conn: Connection = Depends(get_conn),
) -> JSONResponse:
    fn = REGISTRY.get(function)
    if fn is None:
        raise ApiError(400, "invalid_input", f"function: unknown {function!r} (see GET /functions)")
    k = game.bet_min_numbers if k is None else k
    if not game.bet_min_numbers <= k <= game.bet_max_numbers:
        raise ApiError(400, "invalid_input", f"k: must be {game.bet_min_numbers}-{game.bet_max_numbers}")
    if from_ is not None and to is not None and from_ > to:
        raise ApiError(400, "invalid_input", f"from ({from_}) is after to ({to})")

    extra = [
        (name, value) for name, value in request.query_params.multi_items() if name not in BACKTEST_QUERY
    ]
    names = [name for name, _ in extra]
    if len(set(names)) != len(names):
        raise ApiError(400, "invalid_input", "a function parameter was given more than once")
    try:
        params = fn.resolve_params(dict(extra))
    except ValueError as e:
        raise ApiError(400, "invalid_input", str(e)) from None

    if from_ is None:
        # The last DEFAULT_TARGETS contests that exist up to `to`.
        end = stats.resolve_window(conn, game, to=to).last_contest or 1
        from_ = max(1, end - DEFAULT_TARGETS + 1)
    w = stats.resolve_window(conn, game, first=from_, to=to)
    cap = backtest_max_contests()
    if w.draws > cap:
        raise ApiError(400, "invalid_input", f"from/to: {w.draws} target contests, at most {cap} per request")

    history = load_history(conn, game, w.last_contest) if w.draws else []
    result = backtest(game, history, fn, k, params, w.first_contest or 0, w.last_contest or 0)
    return ok(backtest_json(game, result))
