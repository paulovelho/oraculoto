"""Settings from the environment, plus a `.env` file at the project root.

Under CGI there is no shell environment, so `.env` is the normal source on the server.
Variables already set in the environment win over `.env`.
"""

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_env(path: Path = PROJECT_ROOT / ".env") -> None:
    """Minimal .env reader: KEY=VALUE lines, # comments, optional surrounding quotes."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


@dataclass(frozen=True)
class DbSettings:
    host: str
    port: int
    name: str
    user: str
    password: str


def db_settings(name: str | None = None) -> DbSettings:
    load_env()
    missing = [k for k in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD") if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"missing database settings: {', '.join(missing)} (see .env.example)")
    return DbSettings(
        host=os.environ["DB_HOST"],
        port=int(os.environ.get("DB_PORT") or 3306),
        name=name or os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
