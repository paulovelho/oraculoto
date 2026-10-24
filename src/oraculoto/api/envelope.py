"""The response conventions of docs/api.md §3: the envelope, error codes, money and dates.

Routes return `ok(data)` with data already JSON-native (money as strings, dates as
YYYY-MM-DD), which skips FastAPI's generic encoder on every response.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# Error codes for plain HTTP errors (unknown path, wrong method) that don't come with their own.
HTTP_CODES = {
    400: "invalid_input",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def ok(data: Any) -> JSONResponse:
    return JSONResponse({"success": True, "data": data})


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        {"success": False, "error": {"code": code, "message": message}}, status_code=status, headers=headers
    )


def money(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


def day(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def utc_timestamp(value: datetime | None) -> str | None:
    """Naive UTC datetimes from the database, as ISO 8601 with a Z."""
    return None if value is None else value.isoformat(timespec="seconds") + "Z"


def page_of(items: list, page: int, limit: int, total: int) -> dict[str, Any]:
    return {"items": items, "page": page, "limit": limit, "total": total}


def _validation_message(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors()[:3]:
        where = ".".join(str(p) for p in err.get("loc", ())[1:]) or "request"
        parts.append(f"{where}: {err.get('msg', 'invalid')}")
    return "; ".join(parts) or "invalid input"


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return error(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _invalid(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return error(400, "invalid_input", _validation_message(exc))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = HTTP_CODES.get(exc.status_code, "error")
        return error(exc.status_code, code, str(exc.detail), getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _crash(_request: Request, _exc: Exception) -> JSONResponse:
        # The traceback is logged by whoever runs the app (uvicorn's console, the CGI error log);
        # the client only learns that something broke.
        return error(500, "internal", "internal server error")
