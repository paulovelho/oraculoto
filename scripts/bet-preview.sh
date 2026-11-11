#!/usr/bin/env bash
# Preview the bet scripts/bet.sh would place, without placing it: where each number comes from, step by
# step, for every game in FETCH_GAMES (docs/oraculoto-guess.md). Read-only: it runs `oraculoto audit` on the
# server over SSH and writes nothing. It uses the code deployed there.
#   scripts/bet-preview.sh                   the bet on the next contest, with the deployed oraculoto.toml
#   scripts/bet-preview.sh --config my.toml  the same with a local config instead: sent over SSH's stdin,
#                                            never written on the server, never bet with
#   scripts/bet-preview.sh --contest 3073    replay a past contest: the history before it, compared with the
#                                            stored bet and the draw
#   scripts/bet-preview.sh --k 8             any argument is passed to `oraculoto audit`
# Target and games in scripts/deploy.conf.
# Exit status: 0 if every game was explained, 1 if any failed (the others still run).
set -uo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=deploy.conf
. "$root/scripts/deploy.conf"

# `~` stays unexpanded here, for the remote shell. DEPLOY_PATH is relative to the SSH user's home.
remote_cmd="~/$DEPLOY_PATH/.venv/bin/oraculoto"

# --config FILE (or --config=FILE) is ours; everything else goes to `oraculoto audit`
config=""
args=()
while [ $# -gt 0 ]; do
    case "$1" in
        --config)
            [ $# -ge 2 ] || { echo "--config needs a file" >&2; exit 1; }
            config="$2"; shift 2 ;;
        --config=*) config="${1#--config=}"; shift ;;
        *) args+=("$1"); shift ;;
    esac
done
if [ -n "$config" ] && [ ! -r "$config" ]; then
    echo "can't read $config" >&2
    exit 1
fi

failed=()
for game in $FETCH_GAMES; do
    echo "== $game -> $DEPLOY_HOST${config:+ (config: $config)}"
    # shellcheck disable=SC2029  # meant to expand here; `~` is left for the remote shell
    if [ -n "$config" ]; then
        # the file's text goes through stdin; the server only sees "stdin", hence the name above
        ssh "$DEPLOY_HOST" "$remote_cmd audit --game $game --config - ${args[*]-}" < "$config"
    else
        ssh "$DEPLOY_HOST" "$remote_cmd audit --game $game ${args[*]-}" < /dev/null
    fi || failed+=("$game")
done

if [ ${#failed[@]} -gt 0 ]; then
    echo "== FAILED: ${failed[*]}" >&2
    exit 1
fi
