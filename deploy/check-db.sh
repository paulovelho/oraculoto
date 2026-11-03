#!/bin/sh
# Test the database connection from .env, one layer at a time (settings, DNS, TCP, login, schema).
#   deploy/check-db.sh
# Uses the project's .venv and .env, wherever the project lives. Exit code 0 only if every step passed.
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
oraculoto="$root/.venv/bin/oraculoto"
if [ ! -x "$oraculoto" ]; then
    echo "$oraculoto not found: run 'uv sync' in $root first" >&2
    exit 1
fi

cd "$root"
exec "$oraculoto" db-check
