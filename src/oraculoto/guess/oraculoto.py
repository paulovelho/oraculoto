"""`guess_oraculoto`: the function behind oraculoto's own bet (docs/api.md §11). Work in progress.

The bet is a pipeline of steps read from `oraculoto.toml`, next to this file: which steps, in
which order, with which options, and the version they make up. Every step stops once the bet
holds k balls, and a ball already in it is never added twice. After the configured steps, the
bet is always topped up to k with the hottest balls (oraculoto.guess.heat).

The step types (STEP_TYPES; the config can use each one any number of times):

- `missing`: every ball that didn't come out in any of the last `window` contests, most absent
  first.
- `absent_triple`: the absent balls ("Ausente há" over the whole history, as in the stats panel,
  above `absent_over`), most absent first, and the triples that came out exactly MAX - `offset`
  times over the whole history, MAX being the most frequent triple's count. The first absent ball
  that's in any of those triples brings its triple, and the search stops; when it's in several,
  the largest summed absence wins, and a tie there goes to the lowest triple. If none is in one
  and `fallback` is set, every absent ball goes in instead (most absent first, up to k).
- `lone_position`: over the last `window` contests, the ball alone at position `start` by
  `measure` (`count`: times it came out; `absence`: contests since it last came out, within the
  window). Positions go by value: balls tied on the largest value are all 1st, the next value
  is 2nd. If several balls hold `start`, the next position is tried, until one holds a ball
  alone; if none does, skipped. Also skipped when that ball is already in the bet.

A new step type is a function here plus an entry in STEP_TYPES; then the config can place it.

No randomness anywhere: same input and config, same answer (§5). `explain_oraculoto` runs the
steps and also says what each one saw and added (`oraculoto audit`); `guess_oraculoto` is it
without the explanation, so the two can't disagree. It's not in REGISTRY: it's oraculoto's, not
one users pick or backtest.
"""

import tomllib
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any

from oraculoto.db.draws import Game
from oraculoto.guess.base import GuessFunction, PastDraw
from oraculoto.guess.heat import heat_from_history, ranked

CONFIG_PATH = Path(__file__).with_name("oraculoto.toml")


def target_contest(history: Sequence[PastDraw]) -> int:
    return history[-1].contest + 1 if history else 1


def current_gaps(game: Game, history: Sequence[PastDraw]) -> dict[int, int]:
    """The stats panel's "Ausente há" over the whole history: contests since the ball last came out,
    0 if it came out in the latest one, the whole history's span if it never did."""
    if not history:
        return {b: 0 for b in range(game.ball_min, game.ball_max + 1)}
    last_seen = {b: d.contest for d in history for b in d.balls}  # later contests overwrite earlier
    latest, span = history[-1].contest, history[-1].contest - history[0].contest + 1
    return {
        b: latest - last_seen[b] if b in last_seen else span for b in range(game.ball_min, game.ball_max + 1)
    }


def absent_balls(gaps: Mapping[int, int], over: int) -> list[int]:
    """Absence above `over`, most absent first, ties by the lower ball."""
    return sorted((b for b, g in gaps.items() if g > over), key=lambda b: (-gaps[b], b))


def triple_counts(history: Sequence[PastDraw]) -> Counter:
    return Counter(t for d in history for t in combinations(d.balls, 3))


def runner_up_triples(history: Sequence[PastDraw], offset: int = 1, counts: Counter | None = None):
    """The triples that came out exactly MAX - `offset` times, ascending. None if that's 0 or less."""
    counts = triple_counts(history) if counts is None else counts
    if not counts:
        return []
    wanted = max(counts.values()) - offset
    return sorted(t for t, n in counts.items() if n == wanted) if wanted > 0 else []


def absent_triple(
    absent: Sequence[int], triples: Sequence[tuple[int, ...]], gaps: Mapping[int, int]
) -> tuple[int, ...] | None:
    """The triple of the most absent ball that has one, or None. Ties on the summed absence go to
    the lowest triple."""
    for ball in absent:
        candidates = _by_summed_absence([t for t in triples if ball in t], gaps)
        if candidates:
            return candidates[0]
    return None


def _by_summed_absence(triples: Sequence[tuple[int, ...]], gaps: Mapping[int, int]) -> list[tuple[int, ...]]:
    return sorted(triples, key=lambda t: (-sum(gaps[b] for b in t), t))


def positions(scores: Mapping[int, int]) -> list[tuple[int, int, list[int]]]:
    """(position, value, balls holding it), highest value first; tied balls share one position."""
    return [
        (pos, value, sorted(b for b, v in scores.items() if v == value))
        for pos, value in enumerate(sorted(set(scores.values()), reverse=True), 1)
    ]


def lone_at_or_after(scores: Mapping[int, int], position: int) -> int | None:
    """The ball alone at `position`, or at the first position after it held by one ball; None if
    none is."""
    for pos, _, holders in positions(scores):
        if pos >= position and len(holders) == 1:
            return holders[0]
    return None


def recent_counts(game: Game, recent: Sequence[PastDraw]) -> dict[int, int]:
    counts = Counter(b for d in recent for b in d.balls)
    return {b: counts[b] for b in range(game.ball_min, game.ball_max + 1)}


# ---------------------------------------------------------------- the explanation


@dataclass
class Step:
    """What one step saw (`notes`, plain sentences) and which balls it put in the bet."""

    number: str  # its place in the pipeline, "0", "1", ...
    title: str
    notes: list[str] = field(default_factory=list)
    added: list[int] = field(default_factory=list)


@dataclass
class Explanation:
    game: Game
    target: int
    k: int
    history: int  # contests in it
    steps: list[Step]
    numbers: list[int]  # in the order the steps picked them


def _balls(balls, gaps: Mapping[int, int] | None = None) -> str:
    if not balls:
        return "none"
    return ", ".join(f"{b:02d}" + (f" ({gaps[b]})" if gaps is not None else "") for b in balls)


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _positions_note(scores: Mapping[int, int], start: int, unit: str) -> list[str]:
    """The positions a lone-ball search walked through, up to the one it settled on."""
    lines = []
    for pos, value, holders in positions(scores):
        line = f"position {pos} ({value} {unit}): {_balls(holders)}"
        if pos < start:
            lines.append(line)
            continue
        alone = len(holders) == 1
        lines.append(line + (" <- alone" if alone else ", shared"))
        if alone:
            break
    return lines


@dataclass
class _Run:
    """One bet being filled: the input, the balls picked so far and the whole-history absences."""

    game: Game
    history: Sequence[PastDraw]
    k: int
    gaps: dict[int, int]
    picked: dict[int, None] = field(default_factory=dict)  # insertion-ordered set

    def add(self, step: Step, *balls: int) -> None:
        for b in balls:
            if b in self.picked:
                continue
            if len(self.picked) >= self.k:
                step.notes.append(
                    f"bet already full ({self.k}): {_balls([b])} and anything after it left out"
                )
                return
            self.picked.setdefault(b)
            step.added.append(b)


# ---------------------------------------------------------------- the step types


def step_missing(run: _Run, s: Step, window: int) -> None:
    recent = run.history[-window:]
    s.title = f"balls missing from the last {len(recent)} contests"
    counts = recent_counts(run.game, recent)
    gaps = run.gaps
    missing = sorted((b for b, n in counts.items() if n == 0), key=lambda b: (-gaps[b], b))
    if missing:
        s.notes.append(f"missing (absence over the whole history): {_balls(missing, gaps)}")
    else:
        s.notes.append(
            f"none: every ball came out at least once (the longest absence is {max(gaps.values())})"
        )
    run.add(s, *missing)


def step_absent_triple(run: _Run, s: Step, absent_over: int, offset: int, fallback: bool) -> None:
    gaps = run.gaps
    s.title = f"the most absent ball's MAX - {offset} triple (whole history)"
    absent = absent_balls(gaps, absent_over)
    s.notes.append(f'absent ("Ausente há" above {absent_over}), most absent first: {_balls(absent, gaps)}')

    tcounts = triple_counts(run.history)
    triples = runner_up_triples(run.history, offset, tcounts)
    if tcounts:
        top = max(tcounts.values())
        at_top = sum(1 for n in tcounts.values() if n == top)
        s.notes.append(f"MAX = {top} ({at_top} triple{'s' if at_top != 1 else ''} at it)")
        wanted = top - offset
        s.notes.append(
            f"{len(triples)} triples came out {wanted} times"
            if wanted > 0
            else f"MAX - {offset} is 0: no triples"
        )
    else:
        s.notes.append("no history: no triples")

    triple = absent_triple(absent, triples, gaps)
    for ball in absent:
        candidates = _by_summed_absence([t for t in triples if ball in t], gaps)
        if not candidates:
            s.notes.append(f"{ball:02d}: in no such triple, next")
            continue
        best = sum(gaps[b] for b in candidates[0])
        plural = "s" if len(candidates) != 1 else ""
        s.notes.append(f"{ball:02d}: in {len(candidates)} such triple{plural}, by summed absence:")
        for t in candidates:
            parts = " + ".join(str(gaps[b]) for b in t)
            s.notes.append(
                f"  ({_balls(t)}) = {parts} = {sum(gaps[b] for b in t)}" + (" <- wins" if t == triple else "")
            )
        tied = [t for t in candidates if sum(gaps[b] for b in t) == best]
        if len(tied) > 1:
            s.notes.append(f"  {len(tied)} triples tie at {best}: the lowest one wins")
        break

    if triple:
        run.add(s, *triple)
    elif not absent:
        s.notes.append("no absent balls: nothing to search")
    elif fallback:
        s.notes.append("no absent ball is in such a triple: the absent balls themselves go in")
        run.add(s, *absent)
    else:
        s.notes.append("no absent ball is in such a triple (no fallback)")


def step_lone_position(run: _Run, s: Step, measure: str, window: int, start: int) -> None:
    recent = run.history[-window:]
    if measure == "count":
        scores, unit = recent_counts(run.game, recent), "times"
        s.title = f"the {_ordinal(start)} most frequent of the last {len(recent)}"
    else:
        scores, unit = current_gaps(run.game, recent), "contests absent"
        rank = "" if start == 1 else f"{_ordinal(start)} "
        s.title = f"the {rank}longest absent within the last {len(recent)}"
    ball = lone_at_or_after(scores, start)
    s.notes.extend(_positions_note(scores, start, unit))
    if ball is None:
        s.notes.append(f"skipped: no position from {start} on holds a single ball")
    elif ball in run.picked:
        s.notes.append(f"skipped: {ball:02d} is already in the bet")
    else:
        run.add(s, ball)


def _heat(run: _Run, s: Step) -> None:
    s.title = "hottest balls not yet in, until the bet is full"
    if len(run.picked) >= run.k:
        s.notes.append("not needed: the bet is already full")
        return
    heat = heat_from_history(run.game, run.history)
    hot = [b for b in ranked(heat) if b not in run.picked][: run.k - len(run.picked)]
    run.add(s, *hot)
    s.notes.append("heat = times in the last 100 - times overall x (100 / contests overall)")
    s.notes.extend(f"{b:02d}: {heat[b]:+.2f}" for b in hot)


# ---------------------------------------------------------------- the config


@dataclass(frozen=True)
class Option:
    kind: type | tuple[str, ...]  # int, bool, or the allowed strings
    min: int | None = None


@dataclass(frozen=True)
class StepType:
    run: Callable[..., None]  # (run, step, **options)
    options: Mapping[str, Option]


STEP_TYPES: dict[str, StepType] = {
    "missing": StepType(step_missing, {"window": Option(int, 1)}),
    "absent_triple": StepType(
        step_absent_triple,
        {"absent_over": Option(int, 0), "offset": Option(int, 0), "fallback": Option(bool)},
    ),
    "lone_position": StepType(
        step_lone_position,
        {"measure": Option(("count", "absence")), "window": Option(int, 1), "start": Option(int, 1)},
    ),
}


class ConfigError(ValueError):
    """oraculoto.toml is wrong: refuse to bet rather than guess what it meant."""


@dataclass(frozen=True)
class StepConfig:
    type: str
    options: Mapping[str, Any]


@dataclass(frozen=True)
class Config:
    version: int
    steps: tuple[StepConfig, ...]


def _check_option(where: str, name: str, value: Any, opt: Option) -> None:
    if isinstance(opt.kind, tuple):
        if value not in opt.kind:
            raise ConfigError(f"{where}: {name} must be one of {', '.join(opt.kind)}, got {value!r}")
        return
    # bool is an int in Python: don't let `window = true` through, nor `fallback = 1`
    if type(value) is not opt.kind:
        raise ConfigError(f"{where}: {name} must be {opt.kind.__name__}, got {value!r}")
    if opt.min is not None and value < opt.min:
        raise ConfigError(f"{where}: {name} must be at least {opt.min}, got {value}")


def parse_config(data: Mapping[str, Any]) -> Config:
    """Checks everything: unknown keys, unknown step types, missing or wrong options."""
    extra = set(data) - {"version", "step"}
    if extra:
        raise ConfigError(f"unknown key{'s' if len(extra) > 1 else ''}: {', '.join(sorted(extra))}")
    version = data.get("version")
    if type(version) is not int or version < 1:
        raise ConfigError(f"version must be a positive integer, got {version!r}")
    steps = []
    for i, raw in enumerate(data.get("step", [])):
        raw = dict(raw)
        kind = raw.pop("type", None)
        where = f"step {i} ({kind})"
        if kind not in STEP_TYPES:
            raise ConfigError(f"step {i}: unknown type {kind!r}; known: {', '.join(STEP_TYPES)}")
        spec = STEP_TYPES[kind].options
        missing, unknown = set(spec) - set(raw), set(raw) - set(spec)
        if missing:
            raise ConfigError(f"{where}: missing {', '.join(sorted(missing))}")
        if unknown:
            raise ConfigError(
                f"{where}: unknown option{'s' if len(unknown) > 1 else ''} {', '.join(sorted(unknown))}"
            )
        for name, value in raw.items():
            _check_option(where, name, value, spec[name])
        steps.append(StepConfig(kind, raw))
    return Config(version, tuple(steps))


def parse_config_text(text: str, name: str) -> Config:
    """A config's TOML text; `name` (a file name, "stdin") goes into the errors."""
    try:
        return parse_config(tomllib.loads(text))
    except (tomllib.TOMLDecodeError, ConfigError) as e:
        raise ConfigError(f"{name}: {e}") from None


def load_config(path: Path = CONFIG_PATH) -> Config:
    return parse_config_text(path.read_text(encoding="utf-8"), path.name)


CONFIG = load_config()  # at import: a broken config stops `oraculoto bet` before it bets anything


# ---------------------------------------------------------------- the bet


def explain_oraculoto(
    game: Game, history: Sequence[PastDraw], k: int, config: Config = CONFIG
) -> Explanation:
    run = _Run(game, history, k, current_gaps(game, history))
    steps = []
    for i, sc in enumerate(config.steps):
        s = Step(str(i), sc.type)
        STEP_TYPES[sc.type].run(run, s, **sc.options)
        steps.append(s)
    s = Step(str(len(config.steps)), "heat")
    _heat(run, s)
    steps.append(s)
    return Explanation(game, target_contest(history), k, len(history), steps, list(run.picked))


def guess_oraculoto(game: Game, history: Sequence[PastDraw], k: int, params: Mapping) -> list[int]:
    return explain_oraculoto(game, history, k).numbers


ORACULOTO = GuessFunction(
    "guess_oraculoto",
    CONFIG.version,
    "oraculoto's own bet: the steps in guess/oraculoto.toml, in order, completed by heat",
    guess_oraculoto,
)
