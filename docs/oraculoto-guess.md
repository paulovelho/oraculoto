# `guess_oraculoto`: how oraculoto picks its own bet

Oraculoto bets on every contest, before the draw, and never changes the bet afterwards (`docs/api.md` §11). This document explains the function that picks those numbers: what each step does, why it's built the way it is, and what it did with the real history.

- **Config:** `src/oraculoto/guess/oraculoto.toml` (which steps, their order and options, the version)
- **Code:** `src/oraculoto/guess/oraculoto.py` (the step types), `src/oraculoto/guess/heat.py` (heat, shared with the stats panel)
- **Tests:** `tests/test_guess_oraculoto.py` (each step on its own, the config, plus the whole bet on the real file), `tests/test_bets.py`
- **Current version:** `guess_oraculoto@3`, still being designed. `@1` was a seeded random placeholder; `@2` broke the triple search's ties with a seeded random draw; `@3` sends them to the lowest triple. Bets placed with older versions keep their `source`.

## The contract

It follows the guess-function contract (`docs/api.md` §5):

```
guess_oraculoto(game, history, k, params) -> k distinct numbers in the game's range
```

- `history` holds only the contests **before** the target, so the function can't see the draw it's betting on.
- **Same input, same answer.** No randomness anywhere: every tie has a fixed rule.
- `k` defaults to the game's minimum bet (6 for Mega-Sena) and can go up to 20 with `oraculoto bet --k N`.
- It's not in the registry: it isn't in `/functions`, it can't be backtested through the API, and it isn't a ticket `source`.

## The steps

The steps live in **`src/oraculoto/guess/oraculoto.toml`**, not in the code. That file says which steps run, in which order, with which options, and which version they make up. The bet is filled in the file's order. A ball already in the bet is never added twice, and every step stops once the bet holds k balls. After the last configured step, **heat always tops the bet up to k**, so it isn't listed in the file.

The shipped config (`version = 3`):

| # | Type | Options | Adds |
|---|---|---|---|
| 0 | `missing` | `window = 52` | every ball that didn't come out in the last 52 contests |
| 1 | `absent_triple` | `absent_over = 30`, `offset = 1`, `fallback = true` | the most absent ball's MAX − 1 triple, else every absent ball |
| 2 | `lone_position` | `measure = "count"`, `window = 52`, `start = 2` | the ball with the second-largest count in the last 52 |
| 3 | `lone_position` | `measure = "absence"`, `window = 52`, `start = 1` | the ball absent the longest within the last 52 |
| 4 | heat (implicit) | — | the hottest balls, until the bet is full |

The numbers are positions in the pipeline, so they change whenever the file is reordered. `oraculoto audit` prints them in the same way.

### Editing the config

- **Order:** move the `[[step]]` blocks.
- **Options:** change the values. Every option is required, and the file is checked when it loads: an unknown key, an unknown type, a missing option, a wrong type (`window = true`) or a value out of range (`window = 0`) stops the code with a `ConfigError`, so `oraculoto bet` refuses to bet instead of guessing what the file meant.
- **More steps:** a type can be used any number of times, with different options. For example, a second `lone_position` with `measure = "count"` and `start = 3`.
- **A new kind of step** needs code: a `step_<name>(run, step, **options)` function in `oraculoto.py` and an entry in `STEP_TYPES` that declares its options. After that, the config can place it anywhere.
- **Any change in the file changes the bets: bump `version`.** It becomes the `source` of every bet placed from then on (`guess_oraculoto@N`). There is one file and no history of past setups, so `oraculoto audit --contest N` always replays with the **current** config. For a bet from an older version, "differs" is expected. Git has the old file if you need it.

### `missing`: missing from the window

Every ball that didn't come out in any of the last `window` contests goes in, most absent first (absence over the whole history), ties by the lower ball. A Mega-Sena ball misses 52 contests in a row with a probability of about 0.4%, so with `window = 52` this rarely happens. When it does, the ball comes first.

### `absent_triple`: the absent ball's triple

1. **Absent balls:** the balls whose "Ausente há" is above `absent_over`, most absent first, ties by the lower ball. "Ausente há" is the stats panel's current absence: contests since the ball last came out, counted over the whole history.
2. **Triples:** count how often every triple came out across the whole history. MAX is the largest count. Keep the triples that came out **exactly MAX − `offset`** times. With `offset = 1`, the MAX triples themselves are left out on purpose; `offset = 0` takes them instead. If MAX − `offset` is 0 or less, there are no triples.
3. **Search:** go through the absent balls, most absent first. The first one that belongs to any of those triples brings **that triple** into the bet, and the search stops there.
   - When the ball belongs to several triples, the one with the **largest summed absence** of its three balls wins. The absent ball is in all of them, so in practice this compares the other two balls.
   - If the sums tie too, the lowest triple (ascending order) wins, like every other tie here going to the lower ball.
4. **Fallback:** if no absent ball belongs to one of the triples and `fallback = true`, every absent ball goes in, most absent first. If there are no absent balls, nothing is added.

### `lone_position`: one ball alone at a position

Over the last `window` contests, score every ball by `measure`:

- `count`: how many times it came out.
- `absence`: contests since it last came out, counted inside the window (the window's span if it never did).

**Positions go by value:** every ball tied on the largest value is 1st, the next value down is 2nd, and so on.

- The ball **alone** at position `start` goes in.
- If several balls share it, try the next position, then the one after, until a position holds exactly one ball.
- If no position does, the step is skipped.
- If the ball is already in the bet, the step is skipped. The search doesn't continue to the next position.

### Heat, the last resort

Whatever is still missing up to k is filled with the hottest balls not yet in the bet:

```
heat(ball) = times in the last 100 contests − times overall × (100 / contests overall)
```

That's how much more a ball came out lately than its own long-run rate predicts. Positive is hot, negative is cold. Ties go to the lower ball, which makes the ranking a strict order of all 60 balls. Because of that, the bet can always be completed, even for k = 20, an empty history or a config with no steps.

It isn't configurable on purpose. The stats panel ("Quentes e frias", `GET /games/{game}/stats/heat`) uses the same function and window (`HEAT_WINDOW`), so the panel and the bet always agree. `HEAT_VERSION` must be bumped whenever the formula or the window changes, because it's part of the panel's HTTP cache key.

## Example: the bet on #3073

History up to #3072, with the shipped config:

| Step | What happened | Bet so far |
|---|---|---|
| 0 `missing` | No ball missed the last 52 (the longest absence is 45) | — |
| 1 `absent_triple` | Absent above 30: 34 (45), 32 (41), 59 (37), 46 (34), 03 (32). MAX = 8 (14 triples); 80 triples came out 7 times. 34 is in 4 of them: (8, 23, 34) sums 64, beating (31, 34, 37) 56, (2, 34, 50) 52 and (6, 34, 53) 52 | 08 23 34 |
| 2 `lone_position` count | Last 52: 16 and 43 share the 1st count (11); 11 is alone at the 2nd (10) | 08 11 23 34 |
| 3 `lone_position` absence | 34 is alone at the top of the absences, but it's already in: skipped | 08 11 23 34 |
| 4 heat | Hottest: 58 (+8.23), then 27 | **08 11 23 27 34 58** |

## How the steps behaved in the real history

These are simulations over `files/Mega-Sena.xlsx`, run while the rules were being decided.

These use the shipped config's step numbers as `@3` had them before the steps moved to the config (0 = `missing`, 1–4 = `absent_triple`, 5 and 6 = the two `lone_position`s).

- **Step 0** (2,973 contests, from #100 on): no ball in 75% of them, one ball in 21%, two in 3%, three in 13 contests. Steps 0–4 together never brought more than 6 balls, so the k limit has never been needed there.
- **Steps 1–4** (last 500 contests): a triple came in 411 times. In 355 of those the absent ball had more than one candidate triple, and the sums tied only 24 times (`@2` drew among them at random; `@3` takes the lowest). The absent balls came in alone (step 4) 26 times. 63 times there was no ball absent above 30.
- **Step 5** (last 500): skipped about 23% of the time because no position held a single ball. The pick came from the 3rd position or lower 170 times.
- **Step 6** (last 500): never skipped for lack of a lone position. In 416 of 500 its ball is also absent above 30, so it's usually a ball steps 1–4 already looked at, and it's often skipped because that ball is already in.

## Ideas tried and dropped

- **"The ball that climbed the most positions" in a frequency ranking, contest to contest:** with all-time counts, only the balls of the last draw can climb, and by one or two positions. In practice the rule meant "repeat a ball from the last draw, picked by where the ties fell". There was a tie at the top in 35–39% of contests.
- **The same idea over an absence ranking**, either "most absent climbs" or "least absent falls": every ball that wasn't drawn gains +1 absence, so their relative order never changes. The only movement comes from the drawn balls dropping back to zero. The rule ended up drawing among about 10–12 tied balls, all among the least absent.
- **Heat measured as momentum** (counts in the last 150 now vs 10 contests ago): small integers, with a tie at the top in more than half the contests. The heat formula above never tied and changes slowly.

## Placing the bet

The bet always runs **on the server**, because that's where the database is. It's triggered from the home machine over SSH, in the same way as the crawler. There are two separate commands, run at home, and neither one starts the other:

```sh
scripts/fetch.sh     # fetch the latest results from Caixa and save them on the server
scripts/bet.sh       # oraculoto bets on the next contest (runs `oraculoto bet` on the server over SSH)
```

- **`scripts/bet.sh`** runs `~/oraculoto/.venv/bin/oraculoto bet --game <game>` on the server for every game in `FETCH_GAMES`. The host, path and games come from `scripts/deploy.conf`. Any argument goes to `oraculoto bet`, e.g. `scripts/bet.sh --k 8`. It only needs SSH, not the local `.venv`. Exit status 0 if every game has its bet, 1 if any failed (the other games still run).
- **On the server itself**, the same thing is `~/oraculoto/.venv/bin/oraculoto bet [--game megasena] [--k N]`.
- **Order:** run `scripts/fetch.sh` first. The bet targets the contest after the latest one **stored**. If the latest result hasn't been fetched yet, the target is a contest that was already drawn: its bets are closed, so the bet is refused and nothing is written. If that contest already has a bet, it answers `already_placed`.
- **Deadline:** bets are taken until 19:00 Brasília on the target's draw date (the latest contest's `dataProximoConcurso`). A contest the crawler fell behind on is **missed**: there is never a late bet.

What the output means:

| Output | Exit | Meaning |
|---|---|---|
| `placed: megasena #3073: 08 11 23 27 34 58 (guess_oraculoto@3); bets close 2026-10-22 19:00 Brasília` | 0 | bet stored |
| `already_placed: megasena #3073: 08 11 23 27 34 58 (guess_oraculoto@3)` | 0 | that contest already had a bet; nothing written |
| `bet failed, nothing written: too late for #3073 …` | 1 | bets closed for the target; fetch first, or that contest is missed |
| `bet failed, nothing written: can't tell when #N is drawn …` | 1 | the latest contest came from the xlsx and has no announced next date; run the fetch |
| `bet failed, nothing written: … never change …` | 1 | a different `--k` on a contest that already has a bet |

**Running it again is safe.** A contest that already has a bet keeps it: the run only reports it, even after bets close. A new version of the code doesn't recompute it either, and the bet keeps its `source`. Two runs at the same time are settled by the unique key (game, contest): the second one gets `already_placed`. A new bet happens only when a newer contest has been fetched in the meantime.

**Before the first real bet**, deploy the current code to the server (`git pull`, `uv sync --compile-bytecode`). Whatever version is there when a contest is bet on is the one that stays on record.

## Previewing and auditing a bet

`scripts/bet-preview.sh` shows the bet `scripts/bet.sh` would place, without placing it, and explains, step by step, where each number comes from: what every step saw (absences, triple counts, positions, heat) and which balls it added or why it was skipped. It runs `oraculoto audit` on the server over SSH, like `bet.sh`, and writes nothing. It uses the code and `oraculoto.toml` **deployed on the server**: a local edit of the config doesn't show up there.

```sh
scripts/bet-preview.sh                   # the bet on the next contest, from the history stored now
scripts/bet-preview.sh --contest 3073    # replay a past contest: the history before it
scripts/bet-preview.sh --k 8             # any argument goes to `oraculoto audit`
scripts/bet-preview.sh --config my.toml  # the same, with a local config instead of the deployed one
```

- `--config FILE` tries a config without deploying it. The script sends the file's text over SSH's stdin to `oraculoto audit --config -`, so nothing is written on the server, and `oraculoto bet` has no such option: **a config is only ever bet with once it's the deployed `oraculoto.toml`**. It combines with the other options (`--config my.toml --contest 3073` replays a past contest with it). The output starts with the config's own version and says it isn't the deployed one; against a stored bet, it says "same" or "differs with this config".
- A broken config is refused before the database is touched, with the same `ConfigError` messages as the deployed file.

- `k` defaults to the stored bet's size for that contest, else the minimum bet.
- With a stored bet, it says whether the replay gives the same numbers. A bet placed by an older version can legitimately differ; one placed by the current version should never differ.
- For a contest already drawn, it also shows the draw and the hits.
- The explanation and the bet are the same code (`explain_oraculoto`; `guess_oraculoto` just drops the explanation), so the audit can't drift from what was bet.

## Changing it

- **Any change in behavior bumps the version**: `version` in `oraculoto.toml`, whether the change is in the file or in a step type's code. Stored bets keep the `source` they were placed with, which is what makes the record trustworthy.
- Heat always runs last, after the configured steps. It's the last resort.
- New step types go in `STEP_TYPES` (see [Editing the config](#editing-the-config)).
- Update this document, `docs/api.md` §11, and the #3073 example in `tests/test_guess_oraculoto.py`.
