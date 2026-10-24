#!/bin/sh
# CGI entry point. A shell wrapper, so the shebang doesn't need an absolute path to the venv.
here="$(cd "$(dirname "$0")" && pwd)"
exec "$here/../.venv/bin/python" "$here/../app.py"
