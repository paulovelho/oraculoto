#!/usr/bin/env bash
# Fetch new results from Caixa at home and save them in the prod database (docs/crawler.md §7).
# The server plans and ingests over SSH; this machine only talks to Caixa. MySQL is never reached from here.
#   deploy/fetch.sh                        normal run for every game in FETCH_GAMES
#   deploy/fetch.sh --contest 3080         refetch one contest
#   deploy/fetch.sh --backfill [--from N] [--to M]
# Any argument is passed to `oraculoto fetch`. Target and games in deploy/deploy.conf.
# Exit status: 0 if every game ran clean, 1 if any failed (the others still run).
set -uo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=deploy.conf
. "$root/deploy/deploy.conf"

oraculoto="$root/.venv/bin/oraculoto"
if [ ! -x "$oraculoto" ]; then
    echo "no $oraculoto: run 'uv sync --extra fetch' in $root first" >&2
    exit 1
fi

# `~` stays unexpanded here, for the remote shell. DEPLOY_PATH is relative to the SSH user's home.
remote_cmd="~/$DEPLOY_PATH/.venv/bin/oraculoto"

failed=()
for game in $FETCH_GAMES; do
    echo "== $game -> $DEPLOY_HOST ($(date '+%Y-%m-%d %H:%M'))"
    if ! "$oraculoto" fetch --remote "$DEPLOY_HOST" --remote-cmd "$remote_cmd" --game "$game" "$@"; then
        failed+=("$game")
    fi
done

if [ ${#failed[@]} -gt 0 ]; then
    echo "== FAILED: ${failed[*]}" >&2
    exit 1
fi
echo "== done: $FETCH_GAMES"
