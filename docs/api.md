# API — plan

Status (2026-10-24): **read endpoints built** (roadmap step 2, local only; not yet deployed): `/health`, `/games`, draws and the four stats endpoints, with the §3 conventions. Code: `src/oraculoto/api/` (app, envelope, auth stub, routes), queries in `src/oraculoto/db/results.py` and `src/oraculoto/db/stats.py`, CGI entry `src/oraculoto/api/cgi.py` behind `public/`. Tests: `tests/test_api.py` (sample data), `tests/test_api_stats.py` (the §6 values of `docs/database.md` on the real file), `tests/test_cgi.py` (through `public/index.cgi`). Auth is still the dev stub (§10); `/me` and tickets are not built.

Status (2026-10-26): **guess functions and backtests built** (roadmap step 3, local only): `GET /functions` and `GET /games/{game}/backtest`, the registry with the four deterministic reference strategies, the exact random baseline. Code: `src/oraculoto/guess/` (contract in `base.py`, strategies in `reference.py`, scoring in `backtest.py`), history loader `load_history()` in `src/oraculoto/db/results.py`, routes in `src/oraculoto/api/routes/guesses.py`. Tests: `tests/test_guess.py` (no database), `tests/test_backtest_reference.py` (the §5 table on the real file), plus validation in `tests/test_api.py`. **`GET /games/{game}/guess` is not built**: its rules are still to be defined (decided 2026-10-26). Stack decided: Python + FastAPI, PyJWT for Firebase tokens, MySQL 8, served as plain CGI on DreamHost shared hosting (see `blueprint.md` and §10).

Local development: `uv run uvicorn oraculoto.api.app:create_app --factory --reload`, then `http://127.0.0.1:8000/api/v1/docs`.

## 1. Scope

The API:
- reads results and statistics, and runs guess functions and backtests
- manages each user's tickets

It never writes results. Only `save_draw()` does that, through the importer and the crawler.

Decisions so far (2026-10-23):
- a Firebase token is required on every endpoint except `/health`
- access is invite-only
- no rate limits
- function guesses are not stored

## 2. Who gets in

Firebase only says *who* someone is, and anyone with a Google account can sign in. Limiting *who may use* the app is the API's job, through the invite list (`users`, see `docs/database.md`).

1. The web app signs in with Google through Firebase and sends the ID token as `Authorization: Bearer <token>`. Tokens expire after 1 hour, and the Firebase SDK refreshes them.
2. The API verifies the token:
   - its signature against Google's public keys, cached on disk for as long as their `Cache-Control: max-age` says (CGI keeps nothing in memory between requests)
   - `aud` = the Firebase project ID, and `iss` = `https://securetoken.google.com/<project ID>`
   - not expired (60 s leeway), and `sub` present
   - `email_verified = true`, and `firebase.sign_in_provider = "google.com"`, so turning on another provider later doesn't open a back door

   Missing, invalid or expired token → **401**.
3. The API looks up the user:
   - First by `firebase_uid = sub`.
   - If there's no match: by `email = lower(token email)` among invited users who haven't logged in yet (`firebase_uid IS NULL`). On a match, save the uid, name and photo on that row.
4. Refusals:
   - No row → **403 `not_invited`**.
   - A `blocked` row → **403 `blocked`**.
   - The email is already linked to a *different* uid → 403 `not_invited`, and log it.
   - Logging in never creates a user.
5. `GET /me` updates `last_login_at`. The web app calls it once when a session starts.

No rate limits. Expensive endpoints still validate their input (backtest range, list sizes); that's input checking, not rate limiting.

**CORS:**
- If the web app is served from the same domain as the API, no CORS is needed.
- Otherwise allow exactly the web app's domain, the `Authorization` and `Content-Type` headers, and the methods in use. No cookies, so no credentials mode.
- CORS is a browser courtesy (curl ignores it). The token check above is the real lock.

## 3. Conventions

- **Prefix:** `/api/v1`. **Format:** JSON.
- **Response shape** (same as Dunedin):
  - success: `{ "success": true, "data": … }`
  - error: `{ "success": false, "error": { "code": "not_invited", "message": "…" } }`
- **Values:**
  - Money: strings with 2 decimals (`"38295.72"`), never floats.
  - Dates: `YYYY-MM-DD`.
  - Balls: integers.
- **Lists:** `page` (starts at 1) and `limit` (default 20, max 100). The response is `{ items, page, limit, total }`.
- **Errors:** 400 invalid input, 401 bad token, 403 not invited or blocked, 404 not found. Another user's ticket is a 404, never a 403 (same as Dunedin), so the API doesn't confirm that it exists.
  - Codes in use: `invalid_input` (400, including every query-parameter check; FastAPI's 422 is never sent), `unauthorized` (401), `not_found` (404: unknown path, game or contest), `method_not_allowed` (405), `db_unavailable` (503, `/health` only), `internal` (500; the traceback goes to the log, never to the client). Step 5 adds `not_invited` and `blocked` (403).
- **Timestamps** (e.g. the last sync): ISO 8601 in UTC, `2026-10-24T14:11:16Z`.

## 4. Endpoints

`{game}` is a slug such as `megasena`. All endpoints need a valid token from an invited user, except `/health`.

**Service**

| method + path | returns |
|---|---|
| `GET /health` (no token) | database status; latest contest and date per game; last successful crawl (`sync_runs`) and whether it's stale |
| `GET /me` | the current user; updates `last_login_at` |

**Results**

| method + path | returns |
|---|---|
| `GET /games` | games and their rules (balls drawn, range, ticket sizes) |
| `GET /games/{game}/draws?from=&to=&page=&limit=` | contests, newest first. `from`/`to` are contest numbers (as on the stats endpoints), both optional |
| `GET /games/{game}/draws/by-date?from=&to=&page=&limit=` | the same list, filtered by draw date: `from`/`to` are `YYYY-MM-DD`, both optional. A dedicated route per filter type (decided 2026-10-24), so contest and date filters can't be mixed |
| `GET /games/{game}/draws/latest` | the latest contest |
| `GET /games/{game}/draws/{contest}` | one contest; 404 if it doesn't exist |

A contest response includes:
- balls in ascending order, plus the draw order when known
- the prize tiers
- winner locations
- `total_collected`, `rollover_amount`, `next_estimated_prize`, `special_accumulated`
- `notes`, `is_special`

As built, one contest is:
`{ contest, date, balls, draw_order, prizes: [{ hits, winners, prize_per_winner }], winner_locations: [{ city, uf, is_online, winners, raw }], total_collected, rollover_amount, next_estimated_prize, special_accumulated, notes, is_special, source }`.
`draw_order` is `null` unless every position is known (xlsx rows never have it). Unknown values are `null`, never `0` (`docs/database.md` §4, rule 4). The list endpoint returns the same objects. `/games` returns a plain array (a fixed catalog, not paginated).

**Stats.** Every stats endpoint accepts a window: `last=N` contests, or `from`/`to` contest numbers. Default: the whole history.

| method + path | returns |
|---|---|
| `GET /games/{game}/stats/frequency` | every ball (including zero counts) with how often it was drawn, plus the expected count for a fair draw |
| `GET /games/{game}/stats/together?balls=10,53&jackpot=false` | how many contests drew all the given balls, the last one, and optionally the list. With `jackpot=true`, only contests where the jackpot was won. `balls`: 1 up to `balls_drawn` distinct balls within range |
| `GET /games/{game}/stats/pairs?size=2&top=20` | most frequent pairs (`size=3` for triples), plus the count expected by chance |
| `GET /games/{game}/stats/gaps` | per ball: last contest drawn, current absence, longest absence |

The SQL behind each one, tested on the real data with the expected results, is in `docs/database.md` §6.

As built:
- **Window:** `last` and `from`/`to` together → 400; `from` > `to` → 400. `last=N` takes the N latest contests that exist. Every response has `window: { from, to, draws }` with the contests actually covered (`null`s and 0 draws when the window is empty, which is not an error).
- **frequency:** `{ window, expected, items: [{ ball, times }] }`, every ball in range, most frequent first (ties: lower ball). `expected` = draws × balls_drawn / pool (307.2 over #1–#3072).
- **together:** `{ window, balls, jackpot, expected, last: { contest, date } | null, items: [{ contest, date }], page, limit, total }`. The list is always there, paginated with the §3 convention, newest first; `total` is the count. `expected` = contests considered × P(one draw holds all the balls), where "considered" is the whole window, or only the jackpot contests with `jackpot=true` (a baseline that assumes the balls don't affect whether somebody wins).
- **pairs:** `size` 2 or 3, `top` 1–100 (default 20). `{ window, size, expected, items: [{ balls, times }] }`, ties by lower balls.
- **gaps:** `{ window, expected_gap, items: [{ ball, last_seen, current_gap, longest_gap }] }`, longest current absence first. Within the window: `current_gap` counts up to the window's last contest; `longest_gap` counts runs between two appearances only, as in `docs/database.md` §6 (`null` with fewer than two). `expected_gap` = (1 − p) / p with p = balls_drawn / pool (9 for Mega-Sena).
- **health:** `{ database: "ok", games: [{ game, latest_contest, latest_date, last_crawl, stale }] }`, `last_crawl` being the latest `ok` or `nothing_new` run of kind `crawl` in `sync_runs` (xlsx imports don't count), and `stale` true when there is none or it's more than 2 days old (`docs/crawler.md` §5). Renamed from `last_sync` on 2026-10-28. If the database is unreachable: 503 `db_unavailable`, details only in the log.

**Guesses**

| method + path | returns |
|---|---|
| `GET /functions` | available guess functions: key, version, description, parameters |
| `GET /games/{game}/guess?function=&k=6&…params` | **not built; rules to be defined.** `k` numbers from the function over the full history, plus the honest odds (k = 6: 1 in 50,063,860). Not stored |
| `GET /games/{game}/backtest?function=&k=6&from=&to=&…params` | how the function would have scored (§5) |

As built:
- **functions:** a plain array of `{ key, version, ref, description, params: [{ name, type, default, min, max, description }] }`, `ref` being `key@version`.
- **backtest:** `function` is required (unknown → 400). `k` defaults to `bet_min_numbers` and must be within the game's bet sizes. `from`/`to` are target contests; `to` defaults to the latest, `from` to the last 100 contests up to `to`. Every other query parameter goes to the function: undeclared, invalid or repeated → 400.
- Response: `{ function: { key, version, ref }, params, k, window: { from, to, draws }, average_hits, hits: [{ hits, draws }], tiers: [{ hits, draws, expected }], baseline: { average_hits, standard_error, z_score } }`. `hits` runs from 0 to min(k, balls_drawn). A tier counts the draws where the guess held at least one winning combination of it (§6), so with k = 6 a 5-hit draw counts for tier 5 only. Floats have 4 significant digits; `z_score` = (average − baseline) / standard error. An empty window gives 0 draws and `null`s, not an error.

**Tickets** (only the caller's own)

| method + path | returns |
|---|---|
| `GET /me/tickets?game=&page=&limit=` | the user's tickets, newest first |
| `POST /me/tickets` | create one: `{ game, numbers[], first_contest, last_contest?, label?, source? }` |
| `GET /me/tickets/{id}` | one ticket |
| `PATCH /me/tickets/{id}` | change `label` only |
| `DELETE /me/tickets/{id}` | delete |
| `GET /me/tickets/{id}/results` | results per contest (§6) |

Rules for creating a ticket:
- The number of numbers must be between the game's `bet_min_numbers` and `bet_max_numbers` (6–20 for Mega-Sena), all distinct and within range.
- `first_contest >= 1`, and `last_contest` defaults to `first_contest`.
- The span is capped (configurable), so a typo can't create a 10,000-contest ticket.
- Tickets for contests already drawn are allowed: users can register old bets.

## 5. Guess functions and backtests

**Contract for the functions you'll send:**

```
guess(game, history, k, params) -> k distinct numbers in the game's range

game:    the game's rules (balls drawn, range, bet sizes)
history: the contests strictly before the target, oldest first;
         each one = contest number, date, balls (sorted), draw order or nothing
k:       how many numbers to return (6–20 for Mega-Sena)
params:  the function's own options, validated against its declared parameters
```

(Changed 2026-10-26: `game` added, since the function otherwise can't know the range; `rng` dropped, along with the `random` strategy. Guesses are deterministic. A function that ever wants randomness brings its own, seeded from its params.)

- **Pure:** no database, no network, no clock, no randomness, no global state. That's what makes a backtest honest: a function can't peek at the draw it's guessing, and the same input gives the same answer. As built, `GuessFunction.guess()` enforces the output (k distinct ints in range; anything else is a `GuessContractError`, a 500).
- **Registered:** each function has a key, a version, a description and its parameters. If its behavior changes, bump the version, so a ticket's `source` (e.g. `hot_recent@1`) keeps meaning the same thing.

**Backtest:**
- **How it runs:** for each target contest N in `from`…`to`, call `guess(game, history before N, k, params)` and count the hits against draw N.
- **What it returns:**
  - average hits per draw, the hit distribution, and how many draws reached each prize tier
  - next to that, always the **random baseline**: expected average `k × balls_drawn / pool size` (0.6 for k = 6 on Mega-Sena), its standard error, and the expected number of prize-tier hits
- **Cache:** none for now (decided 2026-10-26: measure first). Measured locally: loading the whole history takes ~0.12 s, and `hot`, the slowest reference strategy, scores 2,072 targets in ~1.6 s, so a 500-target request costs well under a second on top of CGI. If it's ever needed: on disk, keyed by (function@version, params, k, from, to, latest contest). Nothing is stored in the database.
- **Range cap:** at most 500 target contests per request (`ORACULOTO_BACKTEST_MAX_CONTESTS`); longer ranges get 400. Shared hosting kills long-running requests, so this is a hosting limit, not a rate limit.

**Reference strategies.** Built in (`src/oraculoto/guess/reference.py`), except `random`, which was dropped with `rng` (the baseline is exact math, not a function); they double as regression tests for the backtest. Measured on 2026-10-23 over target contests #1001–#3072 (2,072 draws):

| key | rule | average hits | draws with ≥ 4 hits |
|---|---|---|---|
| `random` | uniform | 0.600 expected | ~0.9 expected |
| `hot` | 6 most frequent balls in all earlier draws; ties go to the lower ball | 0.612 | 0 |
| `hot_recent` | the same, over the last 200 draws (param `last`) | 0.629 | 0 |
| `overdue` | 6 balls whose last appearance is oldest; ties go to the lower ball | 0.572 | 1 |
| `repeat_last` | the previous draw's balls (for k > 6, filled from earlier draws, newest first) | 0.589 | 1 |

The standard error over 2,072 draws is about 0.015, so all of them are within about 2 standard errors of random.

The one idea the data supports is avoiding **popular** combinations. It doesn't raise the chance of winning; it raises the share of the prize if you do win. In contests since #1100 (leaving out the year-end specials), the 4-hit tier had about 91–96 winners per R$1M bet when at most one drawn ball was ≤ 31, and about 218 when all six were (people play birthdays). An `unpopular` function can prefer numbers above 31 and avoid sequences and repeats of recent draws.

## 6. Ticket results

For each contest from `first_contest` to `last_contest`:
- **Not drawn yet:** `pending`.
- **Drawn:** `h` = how many of the ticket's `k` numbers were drawn, plus the matched numbers.
  - For each tier `j` (from `balls_drawn` down to `min_winning_hits`), the ticket holds `C(h, j) × C(k − h, balls_drawn − j)` winning 6-number combinations.
  - Each combination is worth that contest's `prize_per_winner` for tier `j`; the total is the sum.
  - Examples:

    | ticket size k | hits h | winning combinations |
    |---|---|---|
    | 6 | 4 | 1 four-hit |
    | 7 | 6 | 1 jackpot + 6 five-hit |
    | 8 | 4 | 6 four-hit |

  - Amounts are gross (before income tax), as Caixa published them.
  - Mega da Virada's no-rollover rule is already reflected in the published prizes, so it needs no special case.
- **Flag:** `registered_after_draw` when the ticket was created on or after that contest's draw date. It keeps records honest, e.g. for tickets whose `source` is a guess function.

## 7. Admin (command line only in v1)

- `users invite <email> [--admin]`, `users block <email>`, `users unblock <email>`, `users list`
- The importer and crawler commands are described in their own plans.

There are no admin HTTP endpoints in v1, which means less to attack.

## 8. Tests

- **Login cases:**
  - valid token + invited user → 200
  - valid token, not invited → 403 `not_invited`
  - unverified email → 403
  - blocked user → 403 `blocked`
  - the email is linked to another uid → 403
  - an expired or garbage token, or a missing header → 401

  Token checks are tested with fake signing keys, never real Firebase.
- **Stats:** endpoints return the known values from `docs/database.md` §6 (e.g. most frequent ball 10, drawn 359 times; least frequent 26, 250 times, over #1–#3072).
- **Tickets:** the combinations table for k = 6…20; contest ranges; `pending`; another user's ticket → 404; only `label` can be changed.
- **Backtest:** the reference strategies reproduce the numbers in §5 on the same data, and no function can see the target draw. Both done (`tests/test_backtest_reference.py`, `tests/test_guess.py`).

## 9. Not in v1

- Rate limits (decided).
- Signing up yourself (never: invite only).
- Storing function guesses (decided; backtests replace them).
- Notifications ("your ticket won"). Later, the crawler could send them after each draw.

## 10. Stack and deployment (decided 2026-10-23)

- **Framework:** FastAPI. Its automatic OpenAPI docs replace Dunedin's hand-written `openapi.yaml`.
- **Auth:** PyJWT (+ `cryptography` for RS256) does the token checks in §2, behind a FastAPI dependency. Not `firebase-admin`: its import alone would add a big slice to every CGI request. Until step 5 that dependency is a dev stub that refuses to start outside dev.
  - As built (`src/oraculoto/api/auth.py`): `require_user` sits on every router except the one with `/health`. The stub wants `Authorization: Bearer <anything>` (else 401) and returns a fake admin. `create_app()` raises unless `ORACULOTO_ENV=dev`, so **the API can't be deployed until step 5**. `tests/test_api.py` checks that every route in the OpenAPI schema except `/health` answers 401 without a token.
  - The OpenAPI docs (`/api/v1/docs`, `/api/v1/openapi.json`) are public by decision (2026-10-24): the project will be open source, so the routes are public anyway. They list the routes, not data.
- **Guess functions:** Python, one module per function, plus a registry (key, version, description, parameters): `REGISTRY` in `src/oraculoto/guess/__init__.py`. The four reference strategies share one module, being a few lines each.
- **Hosting: DreamHost shared hosting.**
  - **Plain CGI.** DreamHost removed Passenger from shared hosting, so Apache starts Python once per request. Proven by `cgi-test/` (since deleted) on 2026-10-24 (numbers in `blueprint.md`): about 1.3 s per request from Brazil, of which ~0.6 s is network.
  - The domain's web directory points to a `public/` folder holding only `.htaccess` (CGI on; everything that isn't a real file goes to `index.cgi`; the `Authorization` header passed through) and `index.cgi` (a shell wrapper that runs the app with the project's `.venv` Python). The code, `.env` and the docs stay outside the web root.
  - The app is FastAPI wrapped with `a2wsgi` and run by `wsgiref`'s CGIHandler. `PATH_INFO` is rebuilt from `REQUEST_URI`, because of the rewrite. The code doesn't need async.
  - As built: `public/index.cgi` runs `.venv/bin/python -I -m oraculoto.api.cgi`. `oraculoto.api.cgi` rebuilds `PATH_INFO` and `QUERY_STRING` from `REQUEST_URI`, clears `SCRIPT_NAME`, and takes the token from `HTTP_AUTHORIZATION` or `REDIRECT_HTTP_AUTHORIZATION` (Apache may prefix it after the internal redirect; **not yet verified on DreamHost**). Crashes are appended to `logs/cgi-error.log` (or `ORACULOTO_CGI_LOG`), and the client gets a 500 `internal` envelope.
  - Permissions (from the CGI test's setup script): suEXEC refuses scripts or folders writable by group or others, so `chmod 755` the project folder, `public` and `public/index.cgi`, `chmod 644 public/.htaccess`, `chmod 600 .env`.
  - Measured locally (2026-10-24): imports + building the app ≈ 0.5 s, of which ~60 ms is this project's code (SQLAlchemy table definitions, FastAPI analysing the routes); the rest is FastAPI, pydantic and SQLAlchemy themselves. The CGI test measured 463 ms of imports on DreamHost for a two-route app, so expect a bit more there.
  - **Every request pays for the imports**, so keep them lean: import heavy modules only in the routes that need them, no `firebase-admin`, and precompiled bytecode.
  - **Nothing survives between requests**: caches (backtests, Google's keys) live on disk; database connections are opened per request (~36 ms).
  - Python 3.13 is installed in the home directory with `uv`, because the system Python is old.
  - CPU limits: hence the backtest range cap (§5) and the cache.
  - **Deploy:** `mysqldump` (if migrating), `git pull`, `uv sync --compile-bytecode`, `alembic upgrade head`. No restart needed: every request starts fresh.
- **Still open:** whether the web app is served from the same domain as the API, which decides whether CORS is needed.
