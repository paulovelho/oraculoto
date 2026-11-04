# `guess_oraculoto`: how oraculoto picks its own bet

Oraculoto bets on every contest, before the draw, and never changes the bet afterwards (`docs/api.md` §11). This document explains the function that picks those numbers: what each step does, why it's built the way it is, and what it did with the real history.

- **Code:** `src/oraculoto/guess/oraculoto.py` (the steps), `src/oraculoto/guess/heat.py` (heat, shared with the stats panel)
- **Tests:** `tests/test_guess_oraculoto.py` (each step on its own, plus the whole bet on the real file), `tests/test_bets.py`
- **Current version:** `guess_oraculoto@2`, still being designed. `@1` was a seeded random placeholder, and bets placed with it keep that `source`.

## The contract

It follows the guess-function contract (`docs/api.md` §5):

```
guess_oraculoto(game, history, k, params) -> k distinct numbers in the game's range
```

- `history` holds only the contests **before** the target, so the function can't see the draw it's betting on.
- **Same input, same answer.** The only randomness is a tie-break in step 3, and its generator is seeded with `"{game}:{target contest}"`.
- `k` defaults to the game's minimum bet (6 for Mega-Sena) and can go up to 20 with `oraculoto bet --k N`.
- It's not in the registry: it isn't in `/functions`, it can't be backtested through the API, and it isn't a ticket `source`.

## The steps

The bet is filled in this order. A ball already in the bet is never added twice, and every step stops once the bet holds k balls.

| # | Looks at | Adds |
|---|---|---|
| 0 | last 52 contests | every ball that didn't come out in any of them |
| 1–3 | whole history | the runner-up triple of the most absent ball |
| 4 | whole history | if step 3 found no triple: every absent ball |
| 5 | last 52 contests | the ball with the second-largest count |
| 6 | last 52 contests | the ball absent the longest |
| 7 | last 100 contests vs whole history | the hottest balls, until the bet is full |

### Step 0: missing from the last 52

Every ball that didn't come out in any of the last 52 contests (`RECENT`) goes in automatically, most absent first. A Mega-Sena ball misses 52 contests in a row with a probability of about 0.4%, so this rarely happens. When it does, the ball comes first.

### Steps 1–3: the absent ball's triple

1. **Absent balls:** the balls whose "Ausente há" is above 30 (`ABSENT_OVER`), most absent first, ties by the lower ball. "Ausente há" is the stats panel's current absence: contests since the ball last came out, counted over the whole history.
2. **Runner-up triples:** count how often every triple came out across the whole history. MAX is the largest count. Keep the triples that came out **exactly MAX − 1** times. The MAX triples themselves are left out on purpose.
3. **Search:** go through the absent balls, most absent first. The first one that belongs to any runner-up triple brings **that triple** into the bet, and the search stops there.
   - When the ball belongs to several triples, the one with the **largest summed absence** of its three balls wins. The absent ball is in all of them, so in practice this compares the other two balls.
   - If the sums tie too, one of the tied triples is drawn with the seeded generator.

### Step 4: the absent balls themselves

If no absent ball belongs to a runner-up triple, every absent ball goes in, most absent first. If there are no absent balls, nothing is added.

### Step 5: second most frequent in the last 52

Count how often each ball came out in the last 52 contests. **Positions go by count value:** every ball tied on the largest count is 1st, the next count down is 2nd, and so on.

- The ball **alone** at the 2nd position goes in.
- If several balls share the 2nd position, try the 3rd, then the 4th, until a position holds exactly one ball.
- If no position does, the step is skipped.
- If the ball is already in the bet, the step is skipped. The search doesn't continue to the next position.

### Step 6: longest absent in the last 52

Same rule as step 5, from position 1 down, but by absence counted inside the 52-contest window instead of by count. It's skipped in the same cases.

### Step 7: heat, the last resort

Whatever is still missing up to k is filled with the hottest balls not yet in the bet:

```
heat(ball) = times in the last 100 contests − times overall × (100 / contests overall)
```

That's how much more a ball came out lately than its own long-run rate predicts. Positive is hot, negative is cold. Ties go to the lower ball, which makes the ranking a strict order of all 60 balls. Because of that, the bet can always be completed, even for k = 20 or an empty history.

The stats panel ("Quentes e frias", `GET /games/{game}/stats/heat`) uses the same function, so the panel and the bet always agree. `HEAT_VERSION` must be bumped whenever the formula or the window changes, because it's part of the panel's HTTP cache key.

## Example: the bet on #3073

History up to #3072:

| Step | What happened | Bet so far |
|---|---|---|
| 0 | No ball missed the last 52 (the longest absence is 45) | — |
| 1 | Absent above 30: 34 (45), 32 (41), 59 (37), 46 (34), 03 (32) | — |
| 2 | MAX = 8 (14 triples); 80 triples came out 7 times | — |
| 3 | 34 is in 4 of them: (8, 23, 34) sums 64, beating (31, 34, 37) 56, (2, 34, 50) 52 and (6, 34, 53) 52 | 08 23 34 |
| 5 | Last 52: 16 and 43 share the 1st count (11); 11 is alone at the 2nd (10) | 08 11 23 34 |
| 6 | 34 is alone at the top of the absences, but it's already in: skipped | 08 11 23 34 |
| 7 | Hottest: 58 (+8.23), then 27 | **08 11 23 27 34 58** |

## How the steps behaved in the real history

These are simulations over `files/Mega-Sena.xlsx`, run while the rules were being decided.

- **Step 0** (2,973 contests, from #100 on): no ball in 75% of them, one ball in 21%, two in 3%, three in 13 contests. Steps 0–4 together never brought more than 6 balls, so the k limit has never been needed there.
- **Steps 1–4** (last 500 contests): a triple came in 411 times. In 355 of those the absent ball had more than one candidate triple, and the random draw was needed only 24 times. The absent balls came in alone (step 4) 26 times. 63 times there was no ball absent above 30.
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
| `placed: megasena #3073: 08 11 23 27 34 58 (guess_oraculoto@2); bets close 2026-10-22 19:00 Brasília` | 0 | bet stored |
| `already_placed: megasena #3073: 08 11 23 27 34 58 (guess_oraculoto@2)` | 0 | that contest already had a bet; nothing written |
| `bet failed, nothing written: too late for #3073 …` | 1 | bets closed for the target; fetch first, or that contest is missed |
| `bet failed, nothing written: can't tell when #N is drawn …` | 1 | the latest contest came from the xlsx and has no announced next date; run the fetch |
| `bet failed, nothing written: … never change …` | 1 | a different `--k` on a contest that already has a bet |

**Running it again is safe.** A contest that already has a bet keeps it: the run only reports it, even after bets close. A new version of the code doesn't recompute it either, and the bet keeps its `source`. Two runs at the same time are settled by the unique key (game, contest): the second one gets `already_placed`. A new bet happens only when a newer contest has been fetched in the meantime.

**Before the first real bet**, deploy the current code to the server (`git pull`, `uv sync --compile-bytecode`). Whatever version is there when a contest is bet on is the one that stays on record.

## Changing it

- **Any change in behavior bumps the version** (`ORACULOTO = GuessFunction("guess_oraculoto", N, …)`). Stored bets keep the `source` they were placed with, which is what makes the record trustworthy.
- New steps go **before step 7**. Heat is the last resort.
- Update this document, `docs/api.md` §11, and the #3073 example in `tests/test_guess_oraculoto.py`.
