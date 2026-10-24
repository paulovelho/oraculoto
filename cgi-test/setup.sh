#!/bin/sh
# One-time setup on the DreamHost server. Run from anywhere: sh cgi-test/setup.sh
set -eu
cd "$(dirname "$0")"

# 1. uv (single binary in ~/.local/bin, no root)
if ! command -v uv >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/uv" ]; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"

# 2. Python 3.13 + dependencies into cgi-test/.venv (uv downloads Python itself)
"$UV" sync

# 3. Permissions: suEXEC refuses scripts or folders writable by group/others
chmod 755 . public public/index.cgi
chmod 644 public/.htaccess public/test.txt app.py

# 4. Database settings
if [ ! -f .env ]; then
    cp .env.example .env
    echo ">> Created cgi-test/.env: fill in the database settings."
fi
chmod 600 .env

echo
echo "Python: $(.venv/bin/python --version)"
echo "Done. Try: https://oraculoto.platypusweb.com.br/ and /db"
