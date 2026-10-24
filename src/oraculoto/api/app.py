"""The FastAPI app. Built per process: per request under CGI, once under uvicorn."""

from fastapi import FastAPI

from oraculoto.config import load_env

PREFIX = "/api/v1"


def create_app() -> FastAPI:
    load_env()
    from oraculoto.api.auth import check_auth_config

    check_auth_config()

    from oraculoto.api.envelope import install_handlers
    from oraculoto.api.routes import results, service, stats

    app = FastAPI(
        title="Oraculoto",
        version="1",
        openapi_url=f"{PREFIX}/openapi.json",
        docs_url=f"{PREFIX}/docs",
        redoc_url=None,
    )
    install_handlers(app)
    for module in (service, results, stats):
        app.include_router(module.router, prefix=PREFIX)
    return app
