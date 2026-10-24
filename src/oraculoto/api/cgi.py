"""CGI entry point: public/index.cgi runs `python -I -m oraculoto.api.cgi` once per request.

FastAPI (ASGI) is wrapped by a2wsgi and run by wsgiref's CGIHandler. Tracebacks go to
logs/cgi-error.log (or ORACULOTO_CGI_LOG), never to the client: they can hold paths or settings.
"""

import os
import sys
import time
import traceback
from pathlib import Path
from urllib.parse import unquote
from wsgiref.handlers import CGIHandler

from oraculoto.config import PROJECT_ROOT, load_env

CRASH_RESPONSE = (
    "Status: 500 Internal Server Error\r\nContent-Type: application/json\r\n\r\n"
    '{"success": false, "error": {"code": "internal", "message": "internal server error"}}'
)


def log_path() -> Path:
    return Path(os.environ.get("ORACULOTO_CGI_LOG") or PROJECT_ROOT / "logs" / "cgi-error.log")


def log_crash(text: str) -> None:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text.rstrip() + "\n\n")


def fix_environ(environ: dict | os._Environ) -> None:
    """Undo what the .htaccess rewrite does to the CGI variables.

    Apache reports the path of index.cgi, not the one requested: rebuild PATH_INFO and
    QUERY_STRING from REQUEST_URI and clear SCRIPT_NAME, so FastAPI routes on the real path.
    The Authorization header comes through the rewrite as HTTP_AUTHORIZATION, or prefixed with
    REDIRECT_ after the internal redirect, or empty when the client sent none.
    """
    path, _, query = environ.get("REQUEST_URI", "/").partition("?")
    environ["PATH_INFO"] = unquote(path or "/", encoding="latin-1")  # WSGI wants it decoded, as latin-1
    environ["QUERY_STRING"] = query
    environ["SCRIPT_NAME"] = ""
    auth = environ.get("HTTP_AUTHORIZATION") or environ.get("REDIRECT_HTTP_AUTHORIZATION")
    if auth:
        environ["HTTP_AUTHORIZATION"] = auth
    else:
        environ.pop("HTTP_AUTHORIZATION", None)


class Handler(CGIHandler):
    def log_exception(self, exc_info) -> None:
        # Errors inside the app (after FastAPI answered 500) land here; wsgiref would print to stderr.
        log_crash("".join(traceback.format_exception(*exc_info)))


def main() -> None:
    try:
        load_env()
        fix_environ(os.environ)

        from a2wsgi import ASGIMiddleware

        from oraculoto.api.app import create_app
        from oraculoto.api.deps import dispose_engine

        app = create_app()
        try:
            Handler().run(ASGIMiddleware(app))
        finally:
            dispose_engine()
    except Exception:
        log_crash(traceback.format_exc())
        sys.stdout.write(CRASH_RESPONSE)
        sys.stdout.flush()


if __name__ == "__main__":
    main()
