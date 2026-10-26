"""The guess-function contract (docs/api.md §5): what a function receives, declares and must return.

    guess(game, history, k, params) -> k distinct numbers in the game's range

Functions are pure: no database, no network, no clock, no randomness, no global state. The
history holds only the contests strictly before the target, so a function can't peek at
the draw it's guessing, and the same input always gives the same answer.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from oraculoto.db.draws import Game


@dataclass(frozen=True)
class PastDraw:
    contest: int
    date: date
    balls: tuple[int, ...]  # ascending
    draw_order: tuple[int, ...] | None  # as drawn; None unless every position is known


class GuessContractError(RuntimeError):
    """A function returned something other than k distinct numbers in range: a bug in the function."""


@dataclass(frozen=True)
class Param:
    """One option a function declares; values arrive as query-string text and are checked here."""

    name: str
    type: type  # int, float or bool
    default: int | float | bool
    description: str
    min: int | float | None = None
    max: int | float | None = None

    def parse(self, raw: str) -> int | float | bool:
        if self.type is bool:
            if raw.lower() in ("true", "1"):
                return True
            if raw.lower() in ("false", "0"):
                return False
            raise ValueError(f"{self.name}: expected true or false, got {raw!r}")
        try:
            value = self.type(raw)
        except ValueError:
            raise ValueError(f"{self.name}: expected {self.type.__name__}, got {raw!r}") from None
        if self.min is not None and value < self.min:
            raise ValueError(f"{self.name}: must be >= {self.min}")
        if self.max is not None and value > self.max:
            raise ValueError(f"{self.name}: must be <= {self.max}")
        return value


GuessFn = Callable[[Game, Sequence[PastDraw], int, Mapping], Sequence[int]]


@dataclass(frozen=True)
class GuessFunction:
    """A registered function. Bump `version` whenever its behavior changes, so `key@version`
    (e.g. a ticket's `source`) keeps meaning the same numbers."""

    key: str
    version: int
    description: str
    fn: GuessFn
    params: tuple[Param, ...] = ()

    @property
    def ref(self) -> str:
        return f"{self.key}@{self.version}"

    def resolve_params(self, raw: Mapping[str, str]) -> dict:
        """Declared params from raw text, defaults filled in. Unknown names are a ValueError."""
        declared = {p.name: p for p in self.params}
        unknown = sorted(set(raw) - set(declared))
        if unknown:
            accepted = ", ".join(declared) or "none"
            raise ValueError(f"{self.key} has no parameter {unknown[0]!r} (accepted: {accepted})")
        return {name: p.parse(raw[name]) if name in raw else p.default for name, p in declared.items()}

    def guess(self, game: Game, history: Sequence[PastDraw], k: int, params: Mapping) -> tuple[int, ...]:
        """Run the function and hold it to the contract; the numbers come back ascending."""
        numbers = tuple(self.fn(game, history, k, params))
        if (
            len(numbers) != k
            or len(set(numbers)) != k
            or any(type(n) is not int or not game.ball_min <= n <= game.ball_max for n in numbers)
        ):
            target = history[-1].contest + 1 if history else 1
            raise GuessContractError(
                f"{self.ref} broke the contract for contest {target}: wanted {k} distinct numbers "
                f"in {game.ball_min}-{game.ball_max}, got {list(numbers)!r}"
            )
        return tuple(sorted(numbers))
