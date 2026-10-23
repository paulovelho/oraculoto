# API — plan

Status (2026-10-23): design ready, no code yet. The framework and language depend on the stack decision.

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

Firebase only says *who* someone is, and anyone with a Google account can sign in. Limiting *who may use* the app is the API's job, through the invite list (`users`, see `database/plan.md`).

1. The web app signs in with Google through Firebase and sends the ID token as `Authorization: Bearer <token>`. Tokens expire after 1 hour, and the Firebase SDK refreshes them.
2. The API verifies the token:
   - its signature against Google's public keys (cached)
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

## 4. Endpoints

`{game}` is a slug such as `megasena`. All endpoints need a valid token from an invited user, except `/health`.

**Service**

| method + path | returns |
|---|---|
| `GET /health` (no token) | database status; latest contest and date per game; last successful sync (`sync_runs`) |
| `GET /me` | the current user; updates `last_login_at` |

**Results**

| method + path | returns |
|---|---|
| `GET /games` | games and their rules (balls drawn, range, ticket sizes) |
| `GET /games/{game}/draws?from=&to=&page=&limit=` | contests, newest first |
| `GET /games/{game}/draws/latest` | the latest contest |
| `GET /games/{game}/draws/{contest}` | one contest; 404 if it doesn't exist |

A contest response includes:
- balls in ascending order, plus the draw order when known
- the prize tiers
- winner locations
- `total_collected`, `rollover_amount`, `next_estimated_prize`, `special_accumulated`
- `notes`, `is_special`

**Stats.** Every stats endpoint accepts a window: `last=N` contests, or `from`/`to` contest numbers. Default: the whole history.

| method + path | returns |
|---|---|
| `GET /games/{game}/stats/frequency` | every ball (including zero counts) with how often it was drawn, plus the expected count for a fair draw |
| `GET /games/{game}/stats/together?balls=10,53&jackpot=false` | how many contests drew all the given balls, the last one, and optionally the list. With `jackpot=true`, only contests where the jackpot was won. `balls`: 1 up to `balls_drawn` distinct balls within range |
| `GET /games/{game}/stats/pairs?size=2&top=20` | most frequent pairs (`size=3` for triples), plus the count expected by chance |
| `GET /games/{game}/stats/gaps` | per ball: last contest drawn, current absence, longest absence |

The SQL behind each one, tested on the real data with the expected results, is in `database/plan.md` §6.

**Guesses**

| method + path | returns |
|---|---|
| `GET /functions` | available guess functions: key, version, description, parameters |
| `GET /games/{game}/guess?function=&k=6&seed=&…params` | `k` numbers from the function over the full history, plus the honest odds (k = 6: 1 in 50,063,860). Not stored |
| `GET /games/{game}/backtest?function=&k=6&from=&to=&seed=&…params` | how the function would have scored (§5) |

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
guess(history, k, params, rng) -> k distinct numbers in the game's range

history: the contests strictly before the target, oldest first;
         each one = contest number, date, balls (sorted), draw positions or nothing
k:       how many numbers to return (6–20 for Mega-Sena)
params:  the function's own options, validated against its declared parameters
rng:     a seeded random generator, the only randomness allowed
```

- **Pure:** no database, no network, no clock, no global state. That's what makes a backtest honest: a function can't peek at the draw it's guessing, and the same seed gives the same answer.
- **Registered:** each function has a key, a version, a description and its parameters. If its behavior changes, bump the version, so a ticket's `source` (e.g. `hot_recent@1`) keeps meaning the same thing.

**Backtest:**
- **How it runs:** for each target contest N in `from`…`to`, call `guess(history before N, k, params, rng seeded by (seed, N))` and count the hits against draw N.
- **What it returns:**
  - average hits per draw, the hit distribution, and how many draws reached each prize tier
  - next to that, always the **random baseline**: expected average `k × balls_drawn / pool size` (0.6 for k = 6 on Mega-Sena), its standard error, and the expected number of prize-tier hits
- **Cache:** results are cached by (function and version, params, k, seed, from, to, latest contest). Nothing is stored in the database.

**Reference strategies.** Ship these as built-in functions; they double as regression tests for the backtest. Measured on 2026-10-23 over target contests #1001–#3072 (2,072 draws):

| key | rule | average hits | draws with ≥ 4 hits |
|---|---|---|---|
| `random` | uniform | 0.600 expected | ~0.9 expected |
| `hot` | 6 most frequent balls in all earlier draws; ties go to the lower ball | 0.612 | 0 |
| `hot_recent` | the same, over the last 200 draws | 0.629 | 0 |
| `overdue` | 6 balls whose last appearance is oldest; ties go to the lower ball | 0.572 | 1 |
| `repeat_last` | the previous draw's balls | 0.589 | 1 |

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
- **Stats:** endpoints return the known values from `database/plan.md` §6 (e.g. most frequent ball 10, drawn 359 times; least frequent 26, 250 times, over #1–#3072).
- **Tickets:** the combinations table for k = 6…20; contest ranges; `pending`; another user's ticket → 404; only `label` can be changed.
- **Backtest:** the reference strategies reproduce the numbers in §5 on the same data, and no function can see the target draw.

## 9. Not in v1

- Rate limits (decided).
- Signing up yourself (never: invite only).
- Storing function guesses (decided; backtests replace them).
- Notifications ("your ticket won"). Later, the crawler could send them after each draw.

## 10. Depends on the stack

- The framework. If it's Python, FastAPI's automatic OpenAPI docs replace Dunedin's hand-written `openapi.yaml`.
- The Firebase token library (`firebase-admin` in Python; `kreait/firebase-php` was used in Dunedin).
- How guess functions are packaged, e.g. one module per function plus a registry.
- Whether the web app is served from the same domain as the API, which decides whether CORS is needed.
