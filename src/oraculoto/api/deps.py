"""Shared dependencies: the database connection, the game in the path, paging and stats windows."""

from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache

from fastapi import Depends, Path, Query
from sqlalchemy import Connection, Engine

from oraculoto.api.envelope import ApiError
from oraculoto.db.draws import Game
from oraculoto.db.draws import get_game as load_game


@cache
def get_engine() -> Engine:
    """One engine per process: per request under CGI, shared under uvicorn. Tests override it."""
    from oraculoto.db import make_engine

    return make_engine()


def dispose_engine() -> None:
    if get_engine.cache_info().currsize:
        get_engine().dispose()


def get_conn(engine: Engine = Depends(get_engine)) -> Iterator[Connection]:
    # One connection per request, shared by the auth check and the route (FastAPI caches it).
    # Code that writes commits; anything left uncommitted is rolled back when it closes.
    with engine.connect() as conn:
        yield conn


def get_game(game: str = Path(max_length=32), conn: Connection = Depends(get_conn)) -> Game:
    try:
        return load_game(conn, game)
    except LookupError:
        raise ApiError(404, "not_found", f"unknown game {game!r}") from None


@dataclass(frozen=True)
class Paging:
    page: int
    limit: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


def paging(
    page: int = Query(1, ge=1, description="starts at 1"),
    limit: int = Query(20, ge=1, le=100),
) -> Paging:
    return Paging(page, limit)


@dataclass(frozen=True)
class WindowParams:
    last: int | None
    first_contest: int | None
    last_contest: int | None


def window_params(
    last: int | None = Query(None, ge=1, description="the last N contests"),
    from_: int | None = Query(None, alias="from", ge=1, description="first contest number"),
    to: int | None = Query(None, ge=1, description="last contest number"),
) -> WindowParams:
    if last is not None and (from_ is not None or to is not None):
        raise ApiError(400, "invalid_input", "use either last=N or from/to, not both")
    if from_ is not None and to is not None and from_ > to:
        raise ApiError(400, "invalid_input", f"from ({from_}) is after to ({to})")
    return WindowParams(last, from_, to)
