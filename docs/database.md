# Database — plan

Status (2026-10-24): **built.** Schema: Alembic migrations 0001–0003 in `src/oraculoto/db/migrations/` (tables, the `draw_balls_flat` view, the Mega-Sena seed), mirrored in `src/oraculoto/db/schema.py`. `save_draw()`: `src/oraculoto/db/draws.py`. Importer: `oraculoto import-xlsx` (`src/oraculoto/importer/`). The real file imports with exactly the counts in §7, and the §6 queries return the values shown (`tests/test_import.py`). Stack decided: **MySQL 8** on DreamHost shared hosting, SQLAlchemy Core + PyMySQL, Alembic, Python importer on stdlib zipfile + xml.etree (see `blueprint.md`). Types below are generic; §9 maps them to MySQL.

## 1. Scope

For each lottery game (Mega-Sena now; Quina and Lotofácil later) the database stores:
- every contest's result: balls, prize tiers, money figures, winner locations, notes
- the invite list of users (Google login through Firebase) and each user's tickets
- a log of imports and crawler runs

Not stored:
- **Guesses from the prediction functions.** They're computed on demand and judged by backtests; see `docs/api.md`.
- **Precomputed statistics.** At ~18k ball rows every stats query takes milliseconds.

## 2. What the source data looks like (verified 2026-10-23)

`files/Mega-Sena.xlsx` is Caixa's results download.

- **Rows:** one sheet (`MEGA SENA`), a header row plus 3,072 contests, from #1 (11/03/1996) to #3072 (20/10/2026). No gaps, no duplicates, dates in order. It's already out of date: #3073 (22/10/2026) has been drawn.
- **Columns (20):** `Concurso`, `Data do Sorteio`, `Bola1`–`Bola6`, `Ganhadores 6 acertos`, `Cidade / UF`, `Rateio 6 acertos`, `Ganhadores 5 acertos`, `Rateio 5 acertos`, `Ganhadores 4 acertos`, `Rateio 4 acertos`, `Acumulado 6 acertos`, `Arrecadação Total`, `Estimativa prêmio`, `Acumulado Sorteio Especial Mega da Virada`, `Observação`.
- **Balls:** always 6 distinct values in 1–60, **stored in ascending order**. The order they were drawn in isn't in the file; the API has it.
- **Everything is text:** balls `"04"`, dates `"11/03/1996"`, money `"R$1.714.650,23"`. All 7 money columns match `R$d.ddd,dd` in every row.
- **`R$0,00` doesn't always mean zero:**
  - `Arrecadação Total` is 0 in 1,069 contests (essentially #1–#1076): the value is unknown.
  - `Estimativa prêmio` is 0 in 860 contests (up to #867): unknown.
  - `Rateio N acertos` is 0 exactly when that tier had no winners (true for every row and tier): a real zero.
  - `Acumulado 6 acertos` is 0 only when the jackpot was won: a real zero. The reverse isn't true. 25 contests had a jackpot winner *and* a non-zero rollover (money reserved for contests ending in 0 or 5), so "rollover > 0" does **not** mean "nobody won".
  - `Acumulado Sorteio Especial…` is 0 before the special reserve existed (#1–#992) and right after each special contest pays it out: a real zero.
- **Winners:** the 5-hit and 4-hit tiers had winners in all 3,072 contests, so "the last time someone won with ball X" only makes sense for the jackpot (6 hits). 661 contests had jackpot winners.
- **`Cidade / UF`** is free text separated by `;`:
  - It mixes bare states (`SP`), `CITY/UF` with inconsistent spelling (`SÃO PAULO/SP`, `SAO PAULO/SP`, `São Paulo/SP`), and online sales (`CANAL ELETRONICO`, `Canal Eletrônico`).
  - It has data errors (`Cerquilho/ES`: Cerquilho is in SP).
  - In 52 contests it doesn't match the number of winners (#233: 5 winners, `DF; SP`), so it can't be used to count winners.
- **`Observação`** is free text (896 rows), mostly "estimated prize for the next contest" notes.
- **Special contests can't be found by date.** Mega da Virada 2025 was drawn on 01/01/2026 (#2955), and #3010 (24/05/2026) is special too. Only the API says which contests are special.
- **The file is malformed in ways that break generic xlsx readers:**
  - Data rows and cells have no position (`r`) attributes.
  - `<dimension ref="A1:T1"/>` claims the sheet is one row long.
  - Data cells are `t="str"` or `t="n"` holding text.
  - Only the header uses the shared-strings table.

## 3. Glossary

| Caixa (pt-BR) | Schema |
|---|---|
| modalidade / jogo (Mega-Sena, Quina…) | `games` |
| concurso | one row in `draws`; `contest_number` |
| dezena | ball |
| acertos | hits |
| faixa | prize tier, identified by `hits` |
| ganhadores | winners |
| rateio | `prize_per_winner` |
| arrecadação | `total_collected` |
| acumulado | rollover |
| estimativa de prêmio | `next_estimated_prize` |
| aposta | ticket |
| teimosinha | one ticket played over consecutive contests (`first_contest` … `last_contest`) |
| bolão | pool (not modeled) |

`blueprint.md` uses "game" for two things: the lottery ("other games, such as Quina") and a single contest ("result of a specific game"). In the schema, `games` is the lottery and `draws` is one contest.

## 4. Design rules

1. **Normalized and multi-game.** The xlsx is wide and specific to Mega-Sena (`Bola1`…`Bola6`, `6 acertos`). Balls and prize tiers live in child tables, so Quina (5 of 80) and Lotofácil (15 of 25) fit without schema changes.
2. **One write path.** One function, `save_draw()`, writes draws. In one transaction it:
   1. checks the draw against the game's rules
   2. inserts or updates the `draws` row by (`game_id`, `contest_number`)
   3. replaces the draw's balls, prizes and locations

   The importer, the crawler and the backfill all use it, and nothing else writes those tables. Without this, the blueprint's "skip if it's already in the database" leaves a half-written draw (a row with no balls) in place forever.
3. **The API beats the xlsx.** The API has everything the xlsx has, plus draw order, the special flag and winner counts per city. The importer skips contests already saved from the API (unless `--force`). The crawler always overwrites.
4. **NULL means unknown, 0 means zero.** The conversions are listed in §2 and in the column notes below.
5. **Money is exact.**
   - Database: `decimal(15,2)`. The largest value so far is R$3,052,431,720.00, the total collected for Mega da Virada 2025.
   - Code: exact decimals. JSON: strings. Never floats.
   - The API sends floats, so round to 2 decimal places when parsing.
6. **The database checks structure; the code checks game rules.** Foreign keys, unique keys and simple CHECKs live in SQL. Ball count and range per game are checked by `save_draw()` and by the ticket API, because a CHECK can't read the `games` table.
7. **No precomputed stats.** Every query in §6 runs over ~18k rows. If something gets slow later (e.g. Lotofácil triples), cache the API response, keyed by the latest contest number.

## 5. Tables

Types are generic. The mapping to MySQL 8 is in §9.

### `games`

| column | type | null | notes |
|---|---|---|---|
| `id` | int, PK | no | |
| `slug` | varchar(32) | no | unique. `megasena`, the same as the Caixa API path |
| `name` | varchar(64) | no | `Mega-Sena` |
| `balls_drawn` | smallint | no | 6 |
| `ball_min`, `ball_max` | smallint | no | 1, 60 |
| `min_winning_hits` | smallint | no | 4, so the prize tiers are 6, 5 and 4 hits |
| `bet_min_numbers`, `bet_max_numbers` | smallint | no | 6, 20: how many numbers one ticket may have (check Caixa's current rules before seeding) |
| `created_at` | timestamp | no | |

Checks: `ball_min <= ball_max`; `1 <= min_winning_hits <= balls_drawn`; `balls_drawn <= bet_min_numbers <= bet_max_numbers`.

Seed: Mega-Sena only. For reference when expanding (verify the rules then):
- Quina: 5 of 1–80, tiers 5–2, tickets of 5–15 numbers
- Lotofácil: 15 of 1–25, tiers 15–11, tickets of 15–20 numbers

### `draws`: one row per contest

| column | type | null | from xlsx | from API | notes |
|---|---|---|---|---|---|
| `id` | bigint, PK | no | | | |
| `game_id` | FK → `games` | no | | | |
| `contest_number` | int | no | `Concurso` | `numero` | unique together with `game_id` |
| `draw_date` | date | no | `Data do Sorteio` | `dataApuracao` | both `dd/mm/yyyy` |
| `is_special` | boolean | **yes** | — | `indicadorConcursoEspecial` = 2 | NULL = unknown (xlsx rows, until backfilled) |
| `total_collected` | decimal(15,2) | **yes** | `Arrecadação Total` | `valorArrecadado` | 0 → NULL |
| `rollover_amount` | decimal(15,2) | no | `Acumulado 6 acertos` | `valorAcumuladoProximoConcurso` | amount carried into the next contest's jackpot |
| `next_estimated_prize` | decimal(15,2) | **yes** | `Estimativa prêmio` | `valorEstimadoProximoConcurso` | estimate for the *next* contest; 0 → NULL |
| `special_accumulated` | decimal(15,2) | no | `Acumulado Sorteio Especial Mega da Virada` | `valorAcumuladoConcursoEspecial` | reserve for the next special contest |
| `notes` | text | yes | `Observação` | `observacao` | kept as written; empty → NULL |
| `source` | varchar(8) | no | `xlsx` | `api` | which source wrote the row last |
| `source_payload` | json | yes | — | the whole response | so unmapped fields (where it was drawn, the 0/5 reserve, the next draw date…) never need a re-crawl |
| `created_at`, `updated_at` | timestamp | no | | | |

Keys and checks: unique (`game_id`, `contest_number`); index (`game_id`, `draw_date`); `contest_number >= 1`; money columns `>= 0`; `source IN ('xlsx', 'api')`.

Don't work out "nobody won" from `rollover_amount` (see §2). Use `draw_prizes`.

### `draw_balls`

| column | type | null | notes |
|---|---|---|---|
| `draw_id` | FK → `draws`, delete cascades | no | |
| `ball` | smallint | no | check 0–99 (Lotomania uses 00) |
| `draw_position` | smallint | yes | 1 = first ball drawn; NULL when unknown (xlsx) |

Primary key (`draw_id`, `ball`). Unique (`draw_id`, `draw_position`), which allows NULLs. Index (`ball`, `draw_id`). Check `draw_position >= 1`.

### `draw_prizes`

| column | type | null | notes |
|---|---|---|---|
| `draw_id` | FK → `draws`, delete cascades | no | |
| `hits` | smallint | no | 6, 5 and 4 for Mega-Sena |
| `winners` | int | no | check `>= 0` |
| `prize_per_winner` | decimal(15,2) | no | check `>= 0`; 0 when `winners = 0` |

Primary key (`draw_id`, `hits`). Sources:
- **xlsx:** `Ganhadores N acertos` and `Rateio N acertos`.
- **API:** `listaRateioPremio[]`. `faixa` 1 is the top tier, so `hits = balls_drawn − faixa + 1`. Cross-check against `descricaoFaixa` ("6 acertos").

Mega da Virada never rolls over: if nobody hits 6, the jackpot goes to the 5-hit winners. The tier rows just record what was paid, so no special case is needed.

### `draw_winner_locations`: where jackpot winners bought their tickets

| column | type | null | notes |
|---|---|---|---|
| `id` | bigint, PK | no | |
| `draw_id` | FK → `draws`, delete cascades | no | indexed |
| `city` | varchar(128) | yes | spelled as the source spells it; no normalization |
| `uf` | char(2) | yes | NULL for online sales or when unknown |
| `is_online` | boolean | no | `CANAL ELETRONICO` (xlsx), `uf = "--"` (API) |
| `winners` | int | yes | API `ganhadores`; NULL for xlsx rows (the xlsx doesn't say) |
| `raw` | varchar(255) | no | the original text, untouched |

On the current file the importer produces 903 rows: 597 with city and state, 263 with state only, 43 online, 0 it can't parse. For draws imported from the xlsx, don't use this table to count winners (see §2).

### `users`: the invite list

| column | type | null | notes |
|---|---|---|---|
| `id` | bigint, PK | no | |
| `email` | varchar(255) | no | unique, stored lowercase. The admin adds it before the person can log in |
| `firebase_uid` | varchar(128) | yes | unique. Set on the first successful login; NULL = invited but never logged in |
| `display_name` | varchar(255) | yes | from the login token |
| `photo_url` | text | yes | from the login token |
| `role` | varchar(16) | no | `admin` or `member`; default `member` |
| `status` | varchar(16) | no | `active` or `blocked`; default `active` |
| `last_login_at` | timestamp | yes | |
| `created_at`, `updated_at` | timestamp | no | |

Logging in never creates a row; only the admin command line does. The login flow is in `docs/api.md`.

### `tickets`: a user's bet

| column | type | null | notes |
|---|---|---|---|
| `id` | bigint, PK | no | |
| `user_id` | FK → `users`, delete cascades | no | indexed |
| `game_id` | FK → `games` | no | |
| `first_contest`, `last_contest` | int | no | check `last_contest >= first_contest`. Equal for a single bet; a range for a teimosinha |
| `label` | varchar(120) | yes | e.g. "bolão do escritório" |
| `source` | varchar(64) | yes | the guess function the user says produced the numbers (e.g. `hot_recent@1`), checked against the registry; NULL when not stated. Nullable with no default since migration 0004 (decided 2026-10-28; it was `manual`, not null) |
| `created_at`, `updated_at` | timestamp | no | |

Index (`game_id`, `first_contest`, `last_contest`). Numbers and contests can't change after saving; only `label` can. Otherwise a ticket's results could be rewritten after the draw.

### `ticket_numbers`

| column | type | null | notes |
|---|---|---|---|
| `ticket_id` | FK → `tickets`, delete cascades | no | |
| `ball` | smallint | no | check 0–99 |

Primary key (`ticket_id`, `ball`). The API checks the count (6–20 for Mega-Sena) and the range against `games`.

### `sync_runs`: log of imports and crawls

| column | type | null | notes |
|---|---|---|---|
| `id` | bigint, PK | no | |
| `game_id` | FK → `games` | yes | |
| `kind` | varchar(16) | no | `xlsx_import`, `crawl` or `backfill` |
| `status` | varchar(16) | no | `running`, `ok`, `nothing_new` or `error` |
| `started_at` | timestamp | no | |
| `finished_at` | timestamp | yes | |
| `draws_written` | int | no | default 0 |
| `message` | text | yes | file name, contest range, error details |

Index (`game_id`, `kind`, `started_at`). The API's `/health` reads the latest successful run from here.

### View `draw_balls_flat`

One row per ball together with its contest. It's the shape that guess functions and ad-hoc analysis want.

```sql
CREATE VIEW draw_balls_flat AS
SELECT g.slug AS game, d.contest_number, d.draw_date, b.ball, b.draw_position
FROM draw_balls b
JOIN draws d ON d.id = b.draw_id
JOIN games g ON g.id = d.game_id;
```

## 6. Example queries

Tested on 2026-10-23: the full xlsx was loaded into this schema (SQLite as a stand-in) and every query below was run against it. The results shown cover contests #1–#3072. `game_id = 1` is Mega-Sena.

**Result of a contest**

```sql
SELECT d.contest_number, d.draw_date, b.ball, b.draw_position
FROM draws d
JOIN games g ON g.id = d.game_id
JOIN draw_balls b ON b.draw_id = d.id
WHERE g.slug = 'megasena' AND d.contest_number = 3072
ORDER BY b.ball;
-- 02 06 09 16 31 40

SELECT p.hits, p.winners, p.prize_per_winner
FROM draw_prizes p
JOIN draws d ON d.id = p.draw_id
WHERE d.game_id = 1 AND d.contest_number = 3072
ORDER BY p.hits DESC;
-- (6, 0, 0.00), (5, 140, 38295.72), (4, 9261, 954.26)
```

**Last time a set of balls was drawn together.** Works for one ball or several; the number in `HAVING` is how many balls are in the list.

```sql
SELECT d.contest_number, d.draw_date
FROM draws d
JOIN draw_balls b ON b.draw_id = d.id
WHERE d.game_id = 1
  AND b.ball IN (10, 53)
GROUP BY d.id, d.contest_number, d.draw_date
HAVING COUNT(*) = 2
ORDER BY d.contest_number DESC
LIMIT 1;
-- #3065 (2026-10-01). Without LIMIT: all 38 contests where both were drawn (about 26 expected by chance).
```

**Last time someone won the jackpot in a contest that drew those balls**

```sql
SELECT d.contest_number, d.draw_date
FROM draws d
JOIN games g ON g.id = d.game_id
JOIN draw_balls b ON b.draw_id = d.id
WHERE d.game_id = 1
  AND b.ball IN (10, 53)
  AND EXISTS (SELECT 1 FROM draw_prizes p
              WHERE p.draw_id = d.id AND p.hits = g.balls_drawn AND p.winners > 0)
GROUP BY d.id, d.contest_number, d.draw_date
HAVING COUNT(*) = 2
ORDER BY d.contest_number DESC
LIMIT 1;
-- #3043 (2026-08-11). For ball 26 alone (IN (26) ... HAVING COUNT(*) = 1): #3015 (2026-06-06).
```

**Which balls show up most**

```sql
SELECT b.ball, COUNT(*) AS times
FROM draw_balls b
JOIN draws d ON d.id = b.draw_id
WHERE d.game_id = 1
  -- optional window, e.g. the last 100 contests: AND d.contest_number > 3072 - 100
GROUP BY b.ball
ORDER BY times DESC, b.ball;
-- 10 (359), 53 (350), 5 (335) ... 55 (264), 21 (261), 26 (250). A fair draw expects 307.2 each.
```

A ball that never appears inside the chosen window is missing from the result. Fill in the zeros in code, or join against a series of 1–60.

**Balls that show up together** (pairs; for triples, add a third self-join with `c.ball > b.ball`)

```sql
SELECT a.ball AS ball_a, b.ball AS ball_b, COUNT(*) AS times
FROM draw_balls a
JOIN draw_balls b ON b.draw_id = a.draw_id AND b.ball > a.ball
JOIN draws d ON d.id = a.draw_id
WHERE d.game_id = 1
GROUP BY a.ball, b.ball
ORDER BY times DESC, ball_a, ball_b
LIMIT 20;
-- (5, 27) 43, (4, 52) 42, (23, 53) 42 ...   about 26 expected per pair.
-- Triples top out at 8: (4, 17, 52), (4, 27, 52), (4, 28, 30); about 1.8 expected per triple.
```

**How long since each ball last appeared, and its longest absence.** Both count contests in a row without the ball.

```sql
-- current absence ("atraso"); 0 = drawn in the latest contest
SELECT b.ball,
       MAX(d.contest_number) AS last_seen,
       (SELECT MAX(contest_number) FROM draws WHERE game_id = 1) - MAX(d.contest_number) AS current_gap
FROM draw_balls b
JOIN draws d ON d.id = b.draw_id
WHERE d.game_id = 1
GROUP BY b.ball
ORDER BY current_gap DESC;
-- 34 (last seen #3027, 45 contests ago), 32 (41), 59 (37) ...

-- longest absence between two appearances. Needs window functions (PostgreSQL, MariaDB >= 10.2, MySQL >= 8)
SELECT ball, MAX(gap) AS longest_gap
FROM (
  SELECT b.ball,
         d.contest_number - LAG(d.contest_number)
           OVER (PARTITION BY b.ball ORDER BY d.contest_number) - 1 AS gap
  FROM draw_balls b
  JOIN draws d ON d.id = b.draw_id
  WHERE d.game_id = 1
) t
GROUP BY ball
ORDER BY longest_gap DESC;
-- 42 (108), 26 (88), 19 (82) ...  This excludes the current absence; compare with the query above.
```

## 7. xlsx importer

Command (the exact name depends on the stack):
`import-xlsx --game megasena files/Mega-Sena.xlsx [--dry-run] [--force]`

**Reading the file**
- Open the xlsx as a zip. Read `xl/sharedStrings.xml` (the header names) and the worksheet XML.
- Read rows and cells **in document order**, because they carry no position attributes. If a cell does have one (e.g. the file was re-saved in Excel or LibreOffice), use it.
- Every data row in the current file has exactly 20 cells. Any other count is an error.
- Ignore `<dimension>` (it says `A1:T1`). Generic readers trust it: openpyxl in read-only mode stops after the header unless `ws.reset_dimensions()` is called.
- Map columns **by header name**, never by position. A missing header stops the import; an unknown extra header is a warning.
- Prefer Caixa's original download. Re-saving the file can turn text into real numbers and dates; the parser should accept either.

**Column map**

| header | goes to | rule |
|---|---|---|
| `Concurso` | `draws.contest_number` | integer |
| `Data do Sorteio` | `draws.draw_date` | `dd/mm/yyyy` |
| `Bola1` … `Bola6` | `draw_balls.ball` | integer; `draw_position` stays NULL |
| `Ganhadores 6 acertos`, `Rateio 6 acertos` | `draw_prizes` (hits 6) | integer, money |
| `Ganhadores 5 acertos`, `Rateio 5 acertos` | `draw_prizes` (hits 5) | integer, money |
| `Ganhadores 4 acertos`, `Rateio 4 acertos` | `draw_prizes` (hits 4) | integer, money |
| `Cidade / UF` | `draw_winner_locations` | location rule below |
| `Acumulado 6 acertos` | `draws.rollover_amount` | money |
| `Arrecadação Total` | `draws.total_collected` | money; 0 → NULL |
| `Estimativa prêmio` | `draws.next_estimated_prize` | money; 0 → NULL |
| `Acumulado Sorteio Especial Mega da Virada` | `draws.special_accumulated` | money |
| `Observação` | `draws.notes` | empty → NULL |

**Parsing rules**
- **Integer:** trim, base 10 (`"04"` → 4).
- **Date:** `dd/mm/yyyy`.
- **Money:** must match `^R\$\d{1,3}(\.\d{3})*,\d{2}$`. Drop `R$` and the `.` separators, turn `,` into `.`, and keep it as an exact decimal.
- **Location:** split on `;`, trim each piece, then apply the first rule that matches:
  1. `canal eletrônico` or `canal eletronico`, any case → `is_online = true`
  2. `<city>/<UF>`, where UF is 2 capital letters → `city`, `uf`
  3. a bare `<UF>` → `uf`
  4. anything else → `raw` only, with a warning

  `winners` stays NULL. Known data errors are kept as they are; no corrections.

**Checks.** Any failure stops the import and reports the row and the reason. Nothing is written.
- 6 distinct balls, all within the game's range
- contest numbers unique and increasing; a missing contest is only a warning (a partial file is allowed)
- draw dates never go backwards
- for each tier: `winners >= 0`, and `prize_per_winner > 0` exactly when `winners > 0`
- money `>= 0`

**Writing**
- Every row goes through `save_draw()`, all inside one transaction: the file is imported completely or not at all.
- Contests already saved with `source = 'api'` are skipped and counted as "skipped", unless `--force`.
- Importing the same file again changes nothing.
- Each run writes one `sync_runs` row: file name, contest range, and counts of rows inserted, updated and skipped.
- `--dry-run` parses and checks, and writes nothing.

**Expected result on `files/Mega-Sena.xlsx` (2026-10-23)**
- **Row counts:** 3,072 draws (#1–#3072), 18,432 draw_balls, 9,216 draw_prizes, 903 draw_winner_locations.
- **NULLs:** `total_collected` in 1,069 rows, `next_estimated_prize` in 860 rows, `is_special` in every row.
- **#1:** 04 05 30 33 41 52.
  - 6 hits: no winners. 5 hits: 17 × R$39,158.92. 4 hits: 2,016 × R$330.21.
  - Rollover R$1,714,650.23. Total collected NULL.
- **#3072:** 02 06 09 16 31 40. These values are identical to the API's response for #3072.
  - 5 hits: 140 × R$38,295.72. 4 hits: 9,261 × R$954.26.
  - Rollover R$187,648,868.43. Total collected R$134,543,238.00.
  - Next estimate R$200,000,000.00. Special reserve R$106,119,095.67.

**Tests**
- A tiny 3-row sample xlsx with the same defects (no position attributes, wrong dimension, text values). The test code builds it; don't save it from Excel.
- Unit tests for the money, date and location parsers, covering every kind of location text listed above and malformed money.
- Header mapping: a missing header stops the import; columns in a different order still import.
- The expected values for #1 and #3072 above.

## 8. Verification (once `schema.sql` and the importer exist)

1. Run the migrations on an empty database (`alembic upgrade head`), then import the xlsx. Expect exactly the row counts and NULL counts above.
2. Spot-check #1 and #3072 against the expected values above (and against the API).
3. Run the import again: nothing changes (0 inserted, 0 updated).
4. Run every query in §6. The results must match the comments.
5. After the first crawler run, #3073 = 04 13 23 28 41 58 with `source = 'api'` and `draw_position` filled in.

## 9. Depends on the stack

- **Engine: MySQL 8** (decided 2026-10-23), because DreamHost shared hosting offers nothing else. PostgreSQL was the first pick.
  - **Version:** CHECK constraints are enforced only from 8.0.16, and the gaps query needs window functions (8.0). DreamHost runs **8.0.41** (checked 2026-10-23), so both work. Local development uses the `mysql:8.0` image to match.
  - **Engine and charset:** InnoDB, `utf8mb4` (city names have accents), timestamps stored in UTC.
  - **Driver:** PyMySQL, which is pure Python, so nothing has to compile on the shared host.

  | generic | MySQL 8 |
  |---|---|
  | id PK | `BIGINT UNSIGNED AUTO_INCREMENT` |
  | boolean | `TINYINT(1)` (`BOOLEAN`) |
  | decimal(15,2) | `DECIMAL(15,2)` |
  | json | `JSON` (binary storage, validated on insert) |
  | timestamp | `DATETIME`, stored in UTC |
  | upsert | `INSERT … ON DUPLICATE KEY UPDATE`. It fires on *any* unique key; it's safe on `draws` because (`game_id`, `contest_number`) is the only one besides the PK |
  | unique with NULLs | multiple NULLs are allowed, so unique (`draw_id`, `draw_position`) works as intended |

- **Migrations from the first deploy, with Alembic.** In Dunedin the dev database is disposable and `schema.sql` is edited directly. Here, `users` and `tickets` can't be rebuilt from the xlsx or the API, so production needs real migrations from day one. **MySQL DDL isn't transactional:** a migration that fails halfway leaves the schema half-changed. Rules: one schema change per migration, and a `mysqldump` before every deploy that migrates.
- **Data writes are still transactional** (InnoDB): `save_draw()` and the all-or-nothing importer work as described.
- **Importer language and xlsx reader:** Python, with a small stdlib `zipfile` + `xml.etree` reader (see §7). The file breaks openpyxl.

## 10. Not modeled yet (other games)

These need schema changes when they arrive. Documented, not built:
- **Dupla Sena:** two draws per contest, so `draw_balls` needs a `round` column and prizes per round. The API sends `listaDezenasSegundoSorteio`.
- **+Milionária:** 6 of 1–50 plus 2 "trevos" of 1–6, with tiers that combine both. It needs a ball-set column and tier keys beyond `hits`.
- **Super Sete:** 7 columns with one digit 0–9 each, and repeats are allowed. It's positional, not a set of balls.
- **Timemania, Dia de Sorte:** an extra non-numeric result (a team, a month), which needs a column on `draws`. The API sends it in `nomeTimeCoracaoMesSorte`.
- **Lotomania:** also pays for 0 hits, so `min_winning_hits` would become a list of tiers.
- **Federal, Loteca:** different kinds of game altogether.
