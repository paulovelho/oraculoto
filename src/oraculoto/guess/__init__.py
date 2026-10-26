"""Guess functions: the contract (base), the registry below, and backtests (backtest)."""

from oraculoto.guess import reference
from oraculoto.guess.base import GuessContractError, GuessFunction, Param, PastDraw

# key -> function. New functions get a module of their own and are added here.
REGISTRY: dict[str, GuessFunction] = {f.key: f for f in reference.FUNCTIONS}

__all__ = ["REGISTRY", "GuessContractError", "GuessFunction", "Param", "PastDraw"]
