#!/usr/bin/env bash
# Build the web app at home and copy it into the server's public/ (docs/web.md §2). DreamHost has no Node.
#   scripts/deploy-web.sh            build, type-check, then rsync
#   scripts/deploy-web.sh --dry-run  build, then show what rsync would change, without changing it
# Target in scripts/deploy.conf. Keeps the API's entry points (.htaccess, index.cgi) and deletes old hashed assets.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=deploy.conf
. "$root/scripts/deploy.conf"

dry_run=()
if [ "${1:-}" = "--dry-run" ]; then
    dry_run=(--dry-run)
elif [ $# -gt 0 ]; then
    echo "usage: $0 [--dry-run]" >&2
    exit 2
fi

cd "$root/web"

# Vite 8 needs Node 22 (web/.nvmrc). nvm is a shell function, so load it here.
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [ -s "$NVM_DIR/nvm.sh" ]; then
    . "$NVM_DIR/nvm.sh"
    nvm use >/dev/null
fi
node_major="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$node_major" -lt 22 ]; then
    echo "Node 22+ needed, found $(node --version)" >&2
    exit 1
fi

npm test
npm run build   # vue-tsc first: a type error stops the deploy

target="$DEPLOY_HOST:$DEPLOY_PATH/public/"
echo "-> $target"
rsync -av --delete --chmod=D755,F644 \
    --exclude .htaccess --exclude index.cgi \
    "${dry_run[@]}" \
    dist/ "$target"
