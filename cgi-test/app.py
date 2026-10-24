"""Throwaway CGI test: is FastAPI + MySQL through plain CGI fast enough on DreamHost?

Apache starts this script once per request (public/index.cgi -> here), so every
request pays for the Python startup and the imports. The responses report how
long the imports and the database took; curl's time_total gives the full cost.
"""

import time

T0 = time.perf_counter()

import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ERROR_LOG = HERE / "cgi-error.log"


def load_env(path: Path) -> None:
    """Minimal .env reader: KEY=VALUE lines, # comments. CGI gets no shell environment."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def fix_cgi_environ() -> None:
    """After the .htaccess rewrite, Apache reports the path of index.cgi, not the one requested.

    Rebuild PATH_INFO from REQUEST_URI and clear SCRIPT_NAME, so FastAPI routes on the real path.
    """
    uri = os.environ.get("REQUEST_URI", "/")
    os.environ["PATH_INFO"] = uri.split("?", 1)[0] or "/"
    os.environ["SCRIPT_NAME"] = ""


def main() -> None:
    load_env(HERE / ".env")
    fix_cgi_environ()

    from wsgiref.handlers import CGIHandler

    from a2wsgi import ASGIMiddleware
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from sqlalchemy import URL, create_engine, text

    imports_ms = round((time.perf_counter() - T0) * 1000, 1)

    app = FastAPI(title="oraculoto cgi test", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/")
    def root():
        return {
            "success": True,
            "data": {
                "message": "FastAPI is answering through CGI",
                "python": sys.version.split()[0],
                "imports_ms": imports_ms,
                "path": os.environ["PATH_INFO"],
            },
        }

    @app.get("/db")
    def db():
        missing = [k for k in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD") if not os.environ.get(k)]
        if missing:
            error = {"code": "config", "message": f"missing in cgi-test/.env: {', '.join(missing)}"}
            return JSONResponse({"success": False, "error": error}, status_code=500)

        t = time.perf_counter()
        # URL.create escapes the password, so special characters in it are fine.
        url = URL.create(
            "mysql+pymysql",
            username=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            host=os.environ["DB_HOST"],
            port=int(os.environ.get("DB_PORT") or 3306),
            database=os.environ["DB_NAME"],
        )
        engine = create_engine(url)
        try:
            with engine.connect() as conn:
                connect_ms = round((time.perf_counter() - t) * 1000, 1)
                t = time.perf_counter()
                version = conn.execute(text("SELECT VERSION()")).scalar_one()
                query_ms = round((time.perf_counter() - t) * 1000, 1)
        except Exception as e:
            # PyMySQL's messages name the user and host, never the password.
            error = {"code": "db_error", "message": f"{type(e).__name__}: {e.__cause__ or e}"}
            return JSONResponse({"success": False, "error": error}, status_code=500)
        finally:
            engine.dispose()
        return {
            "success": True,
            "data": {
                "mysql": version,
                "imports_ms": imports_ms,
                "connect_ms": connect_ms,
                "query_ms": query_ms,
            },
        }

    CGIHandler().run(ASGIMiddleware(app))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Don't print the traceback to the browser (it can hold paths or credentials); log it next to app.py.
        with ERROR_LOG.open("a") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + traceback.format_exc() + "\n")
        sys.stdout.write("Status: 500 Internal Server Error\r\nContent-Type: text/plain\r\n\r\n")
        sys.stdout.write("error: see cgi-test/cgi-error.log on the server\n")
