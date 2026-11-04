# oraculoto

> *"This project aims to predict the next result on Loterias Caixa. Easy."* — `blueprint.md`

Oraculoto looks at every Mega-Sena draw since 1996, counts the balls, finds which ones keep turning up together and which ones have gone quiet, and then tells you the next result. Every contest it also places its own bet, before the draw, and never changes it afterwards. It's an oracle that keeps receipts.

The setup has three parts:

- **A Python API** (FastAPI) running as plain CGI on shared hosting. Each request starts Python from scratch, so every answer takes about 1.3 seconds of drama.
- **A crawler** that runs on a home computer. Caixa blocks data-center IPs, so the home machine fetches the results and passes them to the server over SSH.
- **A Vue 3 frontend** with results, statistics and backtests. Every backtest is shown next to a random baseline, because that's how you compare things.

More detail lives in `docs/` (`database.md`, `crawler.md`, `api.md`, `web.md`) and in `blueprint.md`. How oraculoto picks its own bet, step by step, is in [`docs/oraculoto-guess.md`](docs/oraculoto-guess.md).

---

## Requirements

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- Docker (only for the local MySQL)
- Node 22+ for the frontend (`web/.nvmrc`; run `nvm use`). Vite 8 fails on Node 18.

## Backend setup (local)

```sh
cp .env.example .env          # then set DB_PORT=3307: local Docker publishes MySQL on 3307
docker compose up -d          # MySQL 8, plus the oraculoto_test database for the tests
uv sync                       # add --extra fetch on the machine that talks to Caixa
uv run alembic upgrade head   # create the schema
uv run oraculoto import-xlsx files/Mega-Sena.xlsx   # load the history
```

Run the API:

```sh
uv run uvicorn oraculoto.api.app:create_app --factory --reload
# then open http://127.0.0.1:8000/api/v1/docs
```

The `.env.example` default is `ORACULOTO_AUTH=dev-key`. To call protected routes, get a token with `uv run oraculoto dev-token you@example.com`; the email has to be invited first (see `users` below). If you set `ORACULOTO_AUTH=none`, results, stats and guesses become public, and `/me` and tickets aren't served at all.

Tests and lint:

```sh
uv run pytest        # wipes TEST_DB_NAME (oraculoto_test). Never point it at production.
uv run ruff check .
```

## The `oraculoto` command

Run `uv run oraculoto --help` to see all the commands, or `uv run oraculoto <command> --help` for one. `--game` defaults to `megasena` wherever it applies.

| Command | Where | What it does |
|---|---|---|
| `import-xlsx FILE [--dry-run] [--force]` | anywhere | Imports Caixa's results spreadsheet. All or nothing. `--force` also overwrites contests that came from Caixa's API. |
| `crawl-plan [--backfill [--from N] [--to M]]` | server | Prints, as JSON, the contests the fetcher should request. |
| `fetch --remote HOST [--remote-cmd PATH]` | home | Gets the plan from the server over SSH, asks Caixa, and streams the answers into the server's `ingest`. |
| `fetch --plan FILE\|-` / `fetch --contest N` | home | Follows a local plan, or refetches one contest, and prints the lines instead of sending them. |
| `ingest` | server | Reads the fetcher's lines on stdin and saves the draws. |
| `bet [--k N]` | server | Places oraculoto's own bet on the next contest. Only once per contest, and it's never changed. |
| `users invite EMAIL [--admin]` / `block` / `unblock` / `list` | server | Manages the invite list. Nobody can sign up; you're invited or you aren't. |
| `db-check` | anywhere | Tests the database settings one layer at a time (DNS, TCP, login, schema). The first FAIL is the cause. |
| `dev-token EMAIL [--minutes N] [--expired] [--unverified]` | dev | Prints a token signed by the local dev key, for `ORACULOTO_AUTH=dev-key`. |

## Scripts in `scripts/`

The target host, path and games are in `scripts/deploy.conf`. You can override any of them for one run, e.g. `DEPLOY_HOST=other scripts/fetch.sh`.

| Script | Where | Usage |
|---|---|---|
| `scripts/check-db.sh` | server or local | `scripts/check-db.sh`: runs `oraculoto db-check` with the project's `.venv` and `.env`. Exits 0 only if every step passes. |
| `scripts/create-admin.sh` | server | `scripts/create-admin.sh someone@example.com`: invites that email as admin. An email that's already invited is refused. |
| `scripts/bet.sh` | home | `scripts/bet.sh`: oraculoto's bet on the next contest for every game in `FETCH_GAMES`, run on the server over SSH. Separate from the fetch: run it after `scripts/fetch.sh` brought the latest result.<br>`scripts/bet.sh --k 8`: more numbers.<br>Only once per contest and only until bets close (19:00 Brasília on the draw date); repeating it changes nothing. |
| `scripts/fetch.sh` | home | `scripts/fetch.sh`: a normal crawl for every game in `FETCH_GAMES`.<br>`scripts/fetch.sh --contest 3080`: refetches one contest.<br>`scripts/fetch.sh --backfill [--from N] [--to M]`: backfill.<br>Needs `uv sync --extra fetch`. |
| `scripts/deploy-web.sh` | home | `scripts/deploy-web.sh`: runs the tests, type-checks and builds the frontend, then rsyncs `web/dist/` into the server's `public/`. It leaves `.htaccess` and `index.cgi` alone.<br>`--dry-run` shows what would change without changing it. |

### The crawler schedule (systemd, home machine)

`scripts/systemd/oraculoto-fetch.{service,timer}` runs the fetch at 09:00 and 23:00 Brasília time. Check the paths and the SSH host alias inside the unit file first, then:

```sh
cp scripts/systemd/oraculoto-fetch.* ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now oraculoto-fetch.timer
loginctl enable-linger "$USER"            # optional: run even while logged out
journalctl --user -u oraculoto-fetch      # logs
```

## Frontend (local)

```sh
cd web
nvm use              # Node 22
npm install
npm run dev          # http://localhost:5173
```

Heads up: the dev server **proxies `/api` to production** (`https://oraculoto.platypusweb.com.br`, see `web/vite.config.ts`), not to your local uvicorn. That's on purpose (`docs/web.md` §1). Every call takes the full ~1.3 s CGI trip, and anything you write goes into the production database. If you'd rather use the local API, point the proxy target at `http://127.0.0.1:8000` and don't commit the change.

Other scripts:

```sh
npm test             # vitest
npm run typecheck    # vue-tsc
npm run build        # type-check + build into web/dist/ (never into public/)
npm run preview      # serve the built dist/
```
