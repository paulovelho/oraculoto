#!/usr/bin/env bash
# Have oraculoto place its own bet on the next contest, for every game in FETCH_GAMES (docs/api.md §11).
# Run at home, like scripts/fetch.sh, and separately from it: usually right after a fetch brought the latest
# result. The bet itself runs on the server over SSH; MySQL is never reached from here.
#   scripts/bet.sh            the minimum bet (6 numbers for Mega-Sena)
#   scripts/bet.sh --k 8      any argument is passed to `oraculoto bet`
# Safe to repeat: a contest that already has a bet is left alone (already_placed). It only bets while the
# next contest still takes bets (until 19:00 Brasília on its draw date); later, nothing is written.
# Target and games in scripts/deploy.conf.
# Exit status: 0 if every game has its bet, 1 if any failed (the others still run).
set -uo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=deploy.conf
. "$root/scripts/deploy.conf"

# `~` stays unexpanded here, for the remote shell. DEPLOY_PATH is relative to the SSH user's home.
remote_cmd="~/$DEPLOY_PATH/.venv/bin/oraculoto"

failed=()
for game in $FETCH_GAMES; do
    echo "== $game -> $DEPLOY_HOST ($(date '+%Y-%m-%d %H:%M'))"
    # shellcheck disable=SC2029  # meant to expand here; `~` is left for the remote shell
    if ! ssh "$DEPLOY_HOST" "$remote_cmd bet --game $game $*"; then
        failed+=("$game")
    fi
done

if [ ${#failed[@]} -gt 0 ]; then
    echo "== FAILED: ${failed[*]}" >&2
    exit 1
fi
echo "== done: $FETCH_GAMES"
