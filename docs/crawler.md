# Crawler — plan

Status (2026-10-23): design ready, no code yet. Stack decided: Python + httpx. Caixa blocks data-center IPs, so the run is split: a **fetcher on the home machine** talks to Caixa, and the **server** (DreamHost) decides what to fetch and saves it (§7).

## 1. Goal

Keep `draws` complete and current for each game:
- fetch every contest that's missing
- refresh recent contests whose data may have changed
- write everything through `save_draw()` (see `docs/database.md` §4)

It runs on a schedule. It replaces the blueprint's "run in a cron and skip if the result is already in the database".

## 2. Source: Caixa's JSON endpoint

```
https://servicebus2.caixa.gov.br/portaldeloterias/api/megasena/{contest}
```

This is the undocumented backend of Caixa's own results site. It's **open but fragile**.

Checked from the dev machine on 2026-10-23:
- **Open:** no login or key. Any User-Agent works, including curl's default and the snippet's `Foo Spider`. It sends `access-control-allow-origin: *` and `cache-control: no-cache`, and answers in about 0.3 s. Neither host has a robots.txt.
- **Matches the xlsx:** contest #3072 matches the xlsx field for field.
- **Has more than the xlsx:** the order the balls were drawn, a "special contest" flag and winner counts per city. Draw order and the special flag are there for every contest back to #1.
- **Fragile:**
  - There are no docs, no guarantees and no versioning.
  - It sits behind Azion's edge network with Radware bot-detection cookies (`__uzma`, `__uzmb`, …), so bot challenges can be switched on at any time.
  - **It blocks data-center IPs.** Verified on 2026-10-23: every request (latest, #3072, #9999) got **403** with Azion's "Forbidden" HTML page, both from DreamHost shared hosting (US, edge `IAD`) and from a Hostinger VPS in Brazil. From the home connection the same requests work. So it isn't a geo-block; residential IPs pass and data-center IPs don't.
- **Odd behavior:**
  - The "latest" endpoint (`/api/megasena`) still returned #3072 while `/api/megasena/3073` already existed.
  - `ultimoConcurso` is `true` for every contest, #1 included.
  - A contest that hasn't been drawn yet returns **HTTP 500** with a JSON-wrapped .NET exception. The real 404 is buried inside it (`"StatusCode":404`).

**Don't work around the block:** no browser User-Agent, no proxies, no "residential IP" services. That's evading their access control, and the likely result is the endpoint closing for everyone. The home fetcher is a normal client on a normal connection, at about 5 requests per run.

**Fallback if it gets blocked:** download the xlsx by hand from Caixa's site and run the importer (`docs/database.md` §7).

**Why not the blueprint's snippet:** its URL now redirects 4 times, and the snippet allows only 1 (`CURLOPT_MAXREDIRS => 1`). It ends on an `.aspx` page (`loterias.caixa.gov.br/Paginas/Mega-Sena.aspx`) that loads the results with JavaScript, and there's no `ul.numbers.mega-sena` in its HTML.

## 3. One run, per game

The logic below is one run. §7 says which machine does which part: the home fetcher only does the HTTP requests; everything that reads or writes the database runs on the server.

```
max = highest contest_number stored for the game (0 if none)

# 1. refresh: catches prize data that arrived late, and corrections
for n in max-2 .. max (only those >= 1):
    fetch n -> save_draw (source = 'api')

# 2. fill the gap, one contest at a time
n = max + 1
repeat (at most 50 times per run):
    fetch n
    found      -> save_draw; n = n + 1
    not found  -> stop (normal: not drawn yet)
    error      -> stop, status = error

write one sync_runs row: kind = 'crawl', status, draws_written, message
```

- Never trust `/api/megasena` (latest) or `ultimoConcurso`. Asking for each contest by number is the source of truth.
- The cap of 50 stops a runaway loop if the API starts returning garbage. Normally a run writes 0–2 new contests; the backfill (§6) handles history.
- Refreshing the last 3 contests turns xlsx rows into API rows (with draw order filled in), which is an upgrade.

**Reading the response**

| response | meaning | action |
|---|---|---|
| 200, JSON, `numero` = requested | found | validate, save |
| 500 or 404 with an inner `"StatusCode":404` in the body | not drawn yet | stop; status `nothing_new` if nothing was written |
| 403, an HTML page, a captcha | blocked by bot detection | stop, status `error`; fall back to the xlsx |
| timeout, other 5xx | Caixa is down | retry (§5), then `error` |
| 200 but `numero` ≠ requested, invalid balls, or missing fields | the API changed or has a bug | write nothing, status `error` |

## 4. Field map (API → schema)

| API field | goes to | rule |
|---|---|---|
| `numero` | `draws.contest_number` | must equal the requested number |
| `dataApuracao` | `draws.draw_date` | `dd/mm/yyyy` |
| `listaDezenas` | `draw_balls.ball` | strings like `"02"` → integers |
| `dezenasSorteadasOrdemSorteio` | `draw_balls.draw_position` | list index + 1; must hold the same set as `listaDezenas` |
| `indicadorConcursoEspecial` | `draws.is_special` | `2` → true, `1` → false |
| `listaRateioPremio[]` | `draw_prizes` | `hits = balls_drawn − faixa + 1`; check against `descricaoFaixa` ("6 acertos"); `numeroDeGanhadores` → `winners`; `valorPremio` → `prize_per_winner` |
| `listaMunicipioUFGanhadores[]` | `draw_winner_locations` | `ganhadores` → `winners`; `uf = "--"` or `municipio = "CANAL ELETRONICO"` → `is_online`; `raw` = `municipio/uf` |
| `valorArrecadado` | `draws.total_collected` | 0 → NULL |
| `valorAcumuladoProximoConcurso` | `draws.rollover_amount` | |
| `valorEstimadoProximoConcurso` | `draws.next_estimated_prize` | 0 → NULL |
| `valorAcumuladoConcursoEspecial` | `draws.special_accumulated` | |
| `observacao` | `draws.notes` | `""` → NULL |
| the whole response | `draws.source_payload` | after removing NUL characters |

- **Money:** the API sends JSON floats (e.g. `38295.72`). Convert each one to a decimal rounded to 2 places at parse time, and never store a float.
- **Fields left out of the mapping** (kept in `source_payload`):
  - `dataProximoConcurso`, used for the staleness alarm in §5
  - `localSorteio`, `nomeMunicipioUFSorteio`
  - `valorAcumuladoConcurso_0_5`, `numeroConcursoFinal_0_5`
  - `acumulado`: derive it from `draw_prizes` instead
  - `tipoPublicacao`: 3 on every contest sampled; meaning unknown, so keep an eye on it
- **Junk:** `nomeTimeCoracaoMesSorte` is a string of NUL characters (`\u0000`) for Mega-Sena. Strip NULs everywhere. `id` is `null`. `ultimoConcurso` is useless (see §2).

**Validation** is the same as the importer's, run by `save_draw()`. On top of that:
- `numero` must equal the requested contest number.
- The sorted ball list and the draw-order list must hold the same 6 balls.

## 5. Schedule, politeness, alarms

- **When:** daily at about 23:00 and 09:00, Brasília time, on the home machine. Use a systemd timer with `Persistent=true`, so a run missed while the PC was off happens at the next boot. Draws happen in the evening. Draw days vary: in 2026, Tuesday, Thursday and Saturday plus some Sundays and a Wednesday. So never schedule by weekday. The morning run also refreshes prize data that arrives late.
- **Cost:** about 4–5 requests per run.
- **HTTP client:**
  - User-Agent `loterias-crawler/<version> (+<project URL or contact>)`. Identify yourself; don't fake a browser.
  - HTTPS only, with certificate checks **on**. Old tutorials turn them off; if Caixa's certificate chain breaks, fix the CA bundle instead.
  - 10 s timeout. 3 attempts with 2 s / 4 s / 8 s backoff on timeouts, connection errors and server errors that aren't the "not drawn yet" kind.
  - At most 1 request per second. Keep a cookie jar for the run, like a normal client.
- **Staleness alarm:** if today is more than 2 days past the latest saved draw's `dataProximoConcurso` and the run found nothing new, record status `error` with the message `stale`. Draws imported from the xlsx have no API response stored, so the check starts after the first API write.
- **The home machine can be off,** and then nothing runs and nothing gets logged. So `/health` also reports **how long since the last successful crawl** (from `sync_runs`) and flags it when it's more than 2 days. For now that's where you look; email or a messaging app can come later.

## 6. Backfill (opt-in, one time)

`crawl --backfill [--from N] [--to M]`
- Re-fetches every contest that's missing or still has `source = 'xlsx'`, oldest first, at 1 request per second at most. 3,073 contests take about an hour.
- Fills in draw order, the special flag, winner counts per city and the raw API response for the whole history. Without it, draw order and `is_special` exist only from today onwards.
- Can resume: contests already saved from the API are skipped, so it's safe to stop and restart.
- Runs from the home machine like any crawl (§7). The server's `crawl-plan --backfill` lists the contests to fetch.
- It sends about 3k requests to an unofficial API, so run it only once you decide to.

## 7. Where it runs (decided 2026-10-23)

Caixa refuses the server (§2), so a run is split across two machines. They talk over **SSH only**: MySQL is never opened to the internet, and a changing home IP doesn't matter.

| part | runs on | does |
|---|---|---|
| `crawl-plan --game G [--backfill …]` | server (DreamHost) | reads the database; prints the contests to refresh (max−2…max), the first contest to try (max+1) and the cap, as JSON |
| `fetch` | **home machine** | calls `crawl-plan` over SSH, requests those contests from Caixa (§3 order, §5 politeness), and stops the gap fill at "not drawn yet". It writes one JSON line per request: contest, HTTP status, classification (found / not drawn / blocked / error) and the body |
| `ingest --game G` | server | reads those lines on stdin; validates, maps (§4) and calls `save_draw()` for each found contest; writes the `sync_runs` row. A "blocked" line becomes status `error` |

One run from the home machine:

```
oraculoto fetch --remote dh --game megasena
  = ssh dh 'oraculoto crawl-plan --game megasena'
    → requests to Caixa from home
    → ssh dh 'oraculoto ingest --game megasena' < results
```

- **One codebase.** The home machine needs only the `fetch` part and httpx, with no database settings at all. The parsing and validation live in one place, on the server.
- **Never inside an API request.** The API process never talks to Caixa.
- **Manual commands:** `fetch`, `fetch --backfill [--from N] [--to M]`, `fetch --contest N` (refetch one contest).
- **Fallback:** if Caixa blocks the home connection too, use the xlsx by hand (§2).

## 8. Tests

- **Recorded responses**, saved once when implementing: #3072 (normal, no jackpot winner), #2955 (special, winners including online sales), #1 (oldest, empty `dataProximoConcurso`), and a "not drawn yet" 500 body. The tests never hit the network.
- **Parser:** every row of the field map, money rounding, and NUL stripping.
- **Same data from both sources:** #3072 parsed from the API equals #3072 parsed from the xlsx, except for the API-only fields.
- **Run logic, with a fake HTTP client:**
  - the gap fill: with max = 3071 it fetches 3072 and 3073 and stops at 3074
  - stopping cleanly on "not drawn yet"
  - stopping with `error` when blocked
  - the 50-contest cap
  - the refresh of the last 3 contests
- **Split run:** `crawl-plan` output for an empty database, for max = 3071, and for `--backfill`. `ingest` with recorded lines: found → saved; not drawn → `nothing_new`; blocked → `error` and nothing written; malformed line → `error` and nothing written.

## 9. Decided (2026-10-23)

- **Language and HTTP client:** Python + httpx.
- **Scheduler:** a systemd timer on the home machine (§5).
- **Where it runs:** split between the home machine and the server, over SSH (§7). Caixa blocks data-center IPs, wherever the host is (§2).
- **Staleness alarm:** `sync_runs` + `/health` for now. Email or a messaging app later.
