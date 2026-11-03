"""The FastAPI app. Built per process: per request under CGI, once under uvicorn."""

from fastapi import Depends, FastAPI

from oraculoto.config import auth_mode, load_env

PREFIX = "/api/v1"


def create_app() -> FastAPI:
    load_env()
    mode = auth_mode()

    from oraculoto.api.envelope import install_handlers
    from oraculoto.api.routes import bets, guesses, results, service, stats

    app = FastAPI(
        title="Oraculoto",
        version="1",
        openapi_url=f"{PREFIX}/openapi.json",
        docs_url=f"{PREFIX}/docs",
        redoc_url=None,
    )
    install_handlers(app)
    app.include_router(service.router, prefix=PREFIX)

    if mode == "none":
        # Login off: the public routes for anyone, and nothing that belongs to a user. Not even
        # PyJWT gets imported, which CGI pays for on every request.
        for module in (results, stats, guesses, bets):
            app.include_router(module.router, prefix=PREFIX)
        return app

    from oraculoto.api.auth import auth_config, require_user
    from oraculoto.api.routes import me

    auth_config()  # a bad setup fails here, at startup, not on the first request
    app.include_router(me.router, prefix=PREFIX)
    for module in (results, stats, guesses, bets):
        app.include_router(module.router, prefix=PREFIX, dependencies=[Depends(require_user)])
    return app
