# Web — plan

Status (2026-11-03): **in progress** (roadmap step 7). Code in `web/` for §6 steps 1–3 (step 1 without login, see §0); step 3 built and checked by hand against production through the dev proxy, **not deployed yet**. Previous status (2026-11-02): planned, not started. It's built against the production API, which is being deployed at the same time (roadmap step 6). Earlier notes from 2026-10-23 are folded in below.

## 0. Scope change (2026-11-03)

- **v1 is public and read-only.** Login, session states and tickets (§3, §6 steps 1's login part and 4) are **postponed**, not dropped. The API client is built so auth can be added later without a rewrite.
- v1 pages: shell + `/health` badge, latest result + contest lookup, stats, backtests. Guesses stay blocked (§6.6).
- Accepted: the API, the expensive backtest included, is open to anyone while `ORACULOTO_AUTH=none`.

## 1. Decisions (2026-11-02)

- **Stack:** Vue 3 + Vite + TypeScript (decided 2026-10-23, same as Dunedin), `vue-router` in history mode, the modular Firebase JS SDK (`firebase/app` + `firebase/auth` only).
- **Same domain as the API:** the app is served from `oraculoto.platypusweb.com.br` at `/`, the API stays at `/api/v1`. The browser sees one origin, so **no CORS**, now or later (closes the open point in `docs/api.md` §10).
- **Local development runs against production only.** No local API, no dev key in the browser. Consequences, accepted:
  - Every ticket created while testing is a real row in the production `tickets` table, under a real account. Clean up with `DELETE /me/tickets/{id}` (or by hand).
  - Every call costs ~1.3 s (CGI), in development too.
  - The Firebase project must exist before the first line of frontend code (§3).
- **Code lives in this repo,** in `web/`, next to `src/`. One repo, one `git pull`.

## 2. Hosting

`public/` is the domain's web root. Today everything that isn't a real file goes to `index.cgi`. It changes to:

- `/api/*` → `index.cgi` (as now; `oraculoto.api.cgi` rebuilds `PATH_INFO` from `REQUEST_URI`, so nothing changes in Python)
- a real file (`index.html`, `assets/…`, favicon) → served by Apache
- anything else → `index.html` (history-mode routes like `/tickets/12`)

Draft of the new `public/.htaccess`:

```apache
Options +ExecCGI -Indexes
AddHandler cgi-script .cgi
DirectoryIndex index.html

RewriteEngine On
RewriteRule .* - [E=HTTP_AUTHORIZATION:%{HTTP:Authorization}]

# Real files as they are (this also stops the second pass after the rewrites below).
RewriteCond %{REQUEST_FILENAME} -f
RewriteRule ^ - [L]

RewriteRule ^api/ index.cgi [L]
RewriteRule ^ index.html [L]

# Hashed assets never change; index.html must always be revalidated.
<IfModule mod_headers.c>
  <FilesMatch "^index\.html$">
    Header set Cache-Control "no-cache"
  </FilesMatch>
  <If "%{REQUEST_URI} =~ m#^/assets/#">
    Header set Cache-Control "public, max-age=31536000, immutable"
  </If>
</IfModule>
```

- An unknown path outside `/api` now gets the app (which shows its own 404), not the JSON `not_found` envelope. Unknown paths under `/api` still reach FastAPI.
- **Build output:** `vite build` writes to `web/dist/` (never straight into `public/`: `emptyOutDir` would delete `index.cgi` and `.htaccess`). Build at home, not on DreamHost (no Node there). `web/dist/` is not committed.
- **Deploy:** `scripts/deploy-web.sh` (`--dry-run` to preview). It runs the tests and the build (type check included) under Node 22, then rsyncs `web/dist/` into the server's `public/` with `--delete`, excluding `.htaccess` and `index.cgi`. `--delete` only removes old hashed assets; the two excludes keep the API's entry points. Target (`DEPLOY_HOST`, `DEPLOY_PATH`) in `scripts/deploy.conf`: `platypusweb@paulovelho.com`, `~/oraculoto`. Both can be overridden from the environment.
- Permissions: suEXEC doesn't care about static files; the deploy sets them `644` and folders `755` (`--chmod`).

## 3. Login

- **Before coding:** create the Firebase project, enable only the Google provider, add `oraculoto.platypusweb.com.br` to the authorized domains (`localhost` is there by default), and set `FIREBASE_PROJECT_ID` in the server's `.env`.
- The Firebase web config (`apiKey`, `authDomain`, `projectId`, `appId`) is public by design. It goes in `web/.env` as `VITE_FIREBASE_*`, with a `web/.env.example` committed.
- `signInWithPopup` with `GoogleAuthProvider`. Not the redirect flow: it relies on third-party storage that browsers now partition, unless `authDomain` is our own domain, which is setup we don't need.
- **Session states**, driven by `onAuthStateChanged` + one `GET /me`:
  - `loading` → spinner
  - `signed-out` → login screen
  - `not-invited` (403 `not_invited`) → "you're not on the list", with a sign-out button. There's no sign-up page; the admin invites from the command line.
  - `blocked` (403 `blocked`) → blocked screen
  - `ready` → the app
- **API client** (one small module, no axios):
  - Adds `Authorization: Bearer ${await user.getIdToken()}` to every call (the SDK caches it and refreshes it before the 1-hour expiry).
  - Unwraps the envelope: returns `data`, or throws an `ApiError { status, code, message }`.
  - On 401: `getIdToken(true)` and retry once; a second 401 signs out.
  - On 403 `not_invited` / `blocked`: switch the session state, whatever page is open.
  - Relative URLs (`/api/v1/...`) only, so the same build works behind the dev proxy and in production.
- **Dev proxy** (`vite.config.ts`): `server.proxy['/api'] = { target: 'https://oraculoto.platypusweb.com.br', changeOrigin: true }`. The `Authorization` header passes through unchanged.

## 4. Slow API, honest UI

Each call is ~1.3 s and nothing is cached server-side, so:
- Skeletons on every data block; never a blank page.
- Fire a page's calls in parallel, never one after another.
- An in-memory cache for the session, keyed by the latest contest from `/health`: `/games`, `/functions`, any `draws/{contest}`, and the stats responses. They only change when a new contest arrives. Tickets are never cached.
- No `localStorage` cache in v1. Add it only if it turns out to be painful.

## 5. Formatting and honesty

- **pt-BR only**, no i18n library.
- **Money** arrives as a string (`"38295.72"`). Format it by splitting the string (`R$ 38.295,72`), never through `parseFloat`. Totals that need adding up come from the API.
- **Dates** arrive as `YYYY-MM-DD`. Show them as `dd/mm/yyyy` by splitting the string, never through `new Date()` (UTC midnight is the previous day in Brasília).
- **Honesty rule:**
  - Every guess is shown with its real odds (1 in 50,063,860 for 6 numbers).
  - Every backtest is shown next to the random baseline from the API, including the `z_score`.
  - Nothing is ever labelled a "prediction" without that baseline next to it.
- **Charts:** the frequency chart is 60 bars. Hand-written SVG, no chart library.
- No UI kit. Plain CSS with a few variables; the app has five pages.

## 6. Pages, in build order

Each step ships to production before the next one starts.

1. **Skeleton:** layout, router, login, the session states (§3), the API client, the `/health` freshness badge (latest contest, stale flag). This step proves the parts that have never run together on DreamHost: the new `.htaccess`, the `Authorization` header through Apache, and real Firebase tokens.
2. **Latest result + contest lookup:** balls (in drawn order when `draw_order` isn't `null`), prize tiers, winner locations, rollover, next estimated prize. Lookup by number at `/contest/:n`; previous/next links.
3. **Stats:** frequency (chart + `expected` line), gaps (table, current absence first), pairs/triples (top N + expected), "together" (pick 1–6 balls, `jackpot` toggle, paginated list). One window selector for all of them: whole history / last N / from–to.
   - **Built (2026-11-03), not deployed.** `/stats` (`views/StatsView.vue`), with a header nav (Resultados / Estatísticas). Checked by hand at phone width with `?last=100&balls=10,53`: every block matches the API, no console errors. `vue-tsc`, `vite build` and `vitest` (82 tests) pass.
   - **State in the URL:** `last` or `from`/`to` (the API's own window keys) plus `balls`, `jackpot=1`, `page`. Malformed values are dropped, never sent (`lib/statsQuery.ts`). A new window resets `page` to 1. A query-only change keeps the scroll position (`router.ts`).
   - **Drafts, not live inputs:** the window form and the ball picker fetch only on "Aplicar" / "Consultar", since every change costs ~1.3 s per block.
   - **Frequency band:** the exact binomial central range (n = window draws, p = balls_drawn / pool, 2.5% per tail), **not** expected ± 2σ: the normal approximation is wrong on short windows (expected ≈ 1 with `last=10`). The page also states how many balls fall outside and how many chance alone would leave outside (`lib/stats.ts`, `fairBand`). The SVG measures its container (ResizeObserver) so labels stay readable on phones.
   - **Selection effect:** the pairs/triples block says that the top 20 of C(60,2) = 1,770 pairs (34,220 triples) always beats `expected` by chance alone. The gaps block says a "late" ball is not more likely.
   - Gaps show 10 rows until asked. "Together" pages 20 contests at a time.
   - `components/BallPicker.vue` is generic (`min`, `max`, `limit`) for step 4's ticket form.
   - Stats responses go in the session cache keyed by their full URL (§4).
   - Shared styles (`.block`, `.data-table`, `.btn`, `.input`, skeleton sizes) moved from `DrawDetails.vue` to `style.css`.
   - Needs Node 22 (`web/.nvmrc`; run `nvm use`). Under Node 18, Vite 8 fails with a `styleText` import error.
4. **My tickets:** list (paginated, newest first); create (a 1–60 ball picker with 6–20 numbers, contest range defaulting to the next contest, span capped by the API); results per contest (`drawn` / `pending` / `missing`, matched numbers, winning combinations, amounts, the `registered_after_draw` flag); rename; delete.
5. **Backtests:** the form is built from `GET /functions` (each `params` entry gives type, default, min and max), plus `k` and the contest range. Results: hits histogram, tiers vs expected, baseline next to it (§5).
6. **Guesses:** **blocked** until the `GET /games/{game}/guess` rules are defined (`docs/api.md` §4). "Save as ticket" (with `source` = the function's `ref`) comes with it.

## 7. Tests

- `vue-tsc --noEmit` and `vitest`, no end-to-end suite in v1.
- Unit tests where bugs would be silent: the money and date formatters, the API client (envelope, 401 retry, 403 switch), the ticket form's validation.
- Pages are checked by hand against production. No tests hit the real API.

## 8. Not in v1

- A local-API mode (decided 2026-11-02: production only).
- Offline support, `localStorage` cache, PWA.
- Admin screens (the API has no admin endpoints; §7 of `docs/api.md`).
- Notifications.
