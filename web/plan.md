# Web — plan (placeholder)

Status (2026-10-23): **on hold until the API is settled**, as `blueprint.md` says. This page only records what's already known, so nothing gets lost in the meantime.

## Known requirements

- **Login:** Google sign-in through Firebase. The web app sends the Firebase ID token on every API call (`api/plan.md` §2).
- **Invite-only:**
  - A 403 `not_invited` shows a "you're not on the list" screen.
  - A 403 `blocked` shows a blocked screen.
  - There's no sign-up page; the admin invites people from the command line.
- **Pages (draft):**
  - **Latest result:** balls (and the order they were drawn, when known), prize tiers, rollover, the next estimated prize, and how fresh the data is (from `/health`).
  - **Contest lookup:** find a contest by number.
  - **Stats:** how often each ball is drawn (chart), "when were these balls last drawn together" (optionally only jackpot contests), top pairs and triples, and current and longest absences.
  - **My tickets:** pick 6–20 numbers and a contest range; see the list; see results per contest with winning combinations and estimated prize, plus pending contests.
  - **Guesses and backtests:** pick a function and its parameters, get numbers, and optionally save them as a ticket (with `source` set to the function).
- **Honesty rule:**
  - Every guess is shown with its real odds (1 in 50,063,860 for 6 numbers).
  - Every backtest is shown next to the random baseline from the API.
  - Nothing is ever labelled a "prediction" without that baseline next to it.
- **Formatting:** pt-BR. Money as R$ 1.234,56 (the API sends strings; never parse them into floats). Dates as dd/mm/yyyy.

## Open (decide when this module starts)

- **Stack:** Vue 3 + Vite + TypeScript (decided 2026-10-23, same as Dunedin).
- **Hosting:** serving the web app from the same domain as the API means no CORS at all (`api/plan.md` §2).
