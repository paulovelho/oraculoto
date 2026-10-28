#!/bin/sh
# Server: put an email on the invite list as admin, so it can log in.
#   deploy/create-admin.sh someone@example.com
# Uses the project's .venv and .env (the database settings), wherever the project lives.
# An email that is already invited is refused: nothing is changed.
set -eu

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
    echo "usage: $0 <email>" >&2
    exit 2
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
oraculoto="$root/.venv/bin/oraculoto"
if [ ! -x "$oraculoto" ]; then
    echo "$oraculoto not found: run 'uv sync' in $root first" >&2
    exit 1
fi

cd "$root"
exec "$oraculoto" users invite "$1" --admin
