#!/bin/sh
# CGI entry point. A shell wrapper, so the shebang doesn't need an absolute path to the venv.
# -I: ignore PYTHON* variables and don't put this folder on sys.path.
here="$(cd "$(dirname "$0")" && pwd)"
exec "$here/../.venv/bin/python" -I -m oraculoto.api.cgi
