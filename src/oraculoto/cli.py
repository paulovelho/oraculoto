"""Command line: `oraculoto <command>`. Run `oraculoto --help` for the list."""

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

from oraculoto.db.draws import DrawValidationError
from oraculoto.importer.caixa_xlsx import ImportFileError
from oraculoto.importer.xlsx import XlsxError


def cmd_import_xlsx(args: argparse.Namespace) -> int:
    from oraculoto.db import make_engine
    from oraculoto.importer.caixa_xlsx import import_xlsx

    engine = make_engine()
    try:
        report = import_xlsx(engine, args.game, args.file, dry_run=args.dry_run, force=args.force)
    except (ImportFileError, XlsxError, DrawValidationError, LookupError) as e:
        print(f"import failed, nothing written: {e}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    for w in report.warnings[: args.max_warnings]:
        print(f"warning: {w}", file=sys.stderr)
    if len(report.warnings) > args.max_warnings:
        print(f"... and {len(report.warnings) - args.max_warnings} more warnings", file=sys.stderr)
    print(("dry run, nothing written: " if args.dry_run else "") + report.summary())
    return 0


def cmd_crawl_plan(args: argparse.Namespace) -> int:
    from oraculoto.crawler.plan import crawl_plan
    from oraculoto.db import make_engine
    from oraculoto.db.draws import get_game

    if (args.first or args.last) and not args.backfill:
        print("--from and --to need --backfill", file=sys.stderr)
        return 2
    engine = make_engine()
    try:
        with engine.connect() as conn:
            plan = crawl_plan(
                conn, get_game(conn, args.game), backfill=args.backfill, first=args.first, last=args.last
            )
    except LookupError as e:
        print(f"crawl-plan failed: {e}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    print(plan.to_json())
    return 0


def _ssh(host: str, remote_cmd: str, *args: str) -> list[str]:
    # remote_cmd is left unquoted so it can hold a path like ~/oraculoto/.venv/bin/oraculoto
    return ["ssh", host, " ".join([remote_cmd, *(shlex.quote(a) for a in args)])]


def _fetch_plan(args: argparse.Namespace):
    """The plan to follow: --plan, --contest, or the server's crawl-plan over SSH."""
    from oraculoto.crawler.protocol import Plan

    if args.plan:
        return Plan.from_json(sys.stdin.read() if args.plan == "-" else Path(args.plan).read_text())
    if args.contest:
        return Plan(game=args.game, kind="crawl", contests=[args.contest])
    extra = ["--backfill"] if args.backfill else []
    extra += ["--from", str(args.first)] if args.first else []
    extra += ["--to", str(args.last)] if args.last else []
    done = subprocess.run(
        _ssh(args.remote, args.remote_cmd, "crawl-plan", "--game", args.game, *extra),
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        raise RuntimeError(f"remote crawl-plan failed: {done.stderr.strip()}")
    return Plan.from_json(done.stdout)


def cmd_fetch(args: argparse.Namespace) -> int:
    try:
        from oraculoto.crawler.fetch import Fetcher, make_client
    except ImportError as e:
        print(f"fetch needs the 'fetch' extra (uv sync --extra fetch): {e}", file=sys.stderr)
        return 1
    from oraculoto.crawler.protocol import ProtocolError

    if args.plan and args.contest:
        print("--plan and --contest can't be used together", file=sys.stderr)
        return 2
    if not args.remote and not (args.plan or args.contest):
        print("give --plan FILE (or - for stdin), --contest N, or --remote HOST", file=sys.stderr)
        return 2
    if (args.backfill or args.first or args.last) and (args.plan or args.contest or not args.remote):
        print(
            "--backfill, --from and --to go with --remote only (else pass them to crawl-plan)",
            file=sys.stderr,
        )
        return 2
    if (args.first or args.last) and not args.backfill:
        print("--from and --to need --backfill", file=sys.stderr)
        return 2

    try:
        plan = _fetch_plan(args)
    except (ProtocolError, RuntimeError, OSError) as e:
        print(f"fetch failed, nothing requested: {e}", file=sys.stderr)
        return 1

    with make_client() as client:
        lines = Fetcher(client).run(plan)
        if not args.remote:
            for line in lines:
                print(json.dumps(line), flush=True)
            return 0
        # Stream into the server's ingest, so a long backfill is saved as it goes.
        ingest = subprocess.Popen(
            _ssh(args.remote, args.remote_cmd, "ingest", "--game", plan.game),
            stdin=subprocess.PIPE,
            text=True,
        )
        try:
            for line in lines:
                ingest.stdin.write(json.dumps(line) + "\n")
                ingest.stdin.flush()
        except BrokenPipeError:
            print("the remote ingest stopped reading; see its message above", file=sys.stderr)
        finally:
            try:
                ingest.stdin.close()
            except BrokenPipeError:
                pass
        return ingest.wait()


def cmd_ingest(args: argparse.Namespace) -> int:
    from oraculoto.crawler.ingest import ingest
    from oraculoto.db import make_engine

    engine = make_engine()
    try:
        report = ingest(engine, args.game, sys.stdin)
    except LookupError as e:
        print(f"ingest failed, nothing written: {e}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    print(f"{report.status}: {report.summary()}", file=sys.stderr if report.problem else sys.stdout)
    return 1 if report.problem else 0


def cmd_bet(args: argparse.Namespace) -> int:
    from oraculoto.bets import BetError, place_bet
    from oraculoto.db import make_engine
    from oraculoto.db.draws import get_game

    engine = make_engine()
    try:
        with engine.connect() as conn:
            outcome = place_bet(conn, get_game(conn, args.game), args.k)
    except (BetError, LookupError) as e:
        print(f"bet failed, nothing written: {e}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    bet = outcome.bet
    numbers = " ".join(f"{n:02d}" for n in bet.numbers)
    line = f"{outcome.result}: {args.game} #{bet.contest}: {numbers} ({bet.source})"
    if outcome.closes_at:
        line += f"; bets close {outcome.closes_at:%Y-%m-%d %H:%M} Brasília"
    print(line)
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    from sqlalchemy import func, select

    from oraculoto.db import bets as bets_db
    from oraculoto.db import make_engine
    from oraculoto.db.draws import get_game
    from oraculoto.db.results import load_history
    from oraculoto.db.schema import draws
    from oraculoto.guess.oraculoto import CONFIG, ORACULOTO, ConfigError, explain_oraculoto, parse_config_text

    # before the database, so a broken config fails fast. Not the deployed one: a what-if, never bet
    config, config_name = CONFIG, None
    if args.config:
        config_name = "stdin" if args.config == "-" else Path(args.config).name
        try:
            text = sys.stdin.read() if args.config == "-" else Path(args.config).read_text(encoding="utf-8")
            config = parse_config_text(text, config_name)
        except (OSError, ConfigError) as e:
            print(f"audit failed: {e}", file=sys.stderr)
            return 1
    ref = f"{ORACULOTO.key}@{config.version}"

    engine = make_engine()
    try:
        with engine.connect() as conn:
            game = get_game(conn, args.game)
            latest = conn.execute(
                select(func.max(draws.c.contest_number)).where(draws.c.game_id == game.id)
            ).scalar_one()
            if latest is None:
                print(f"audit failed: no {game.name} contests stored", file=sys.stderr)
                return 1
            target = latest + 1 if args.contest is None else args.contest
            if not 1 <= target <= latest + 1:
                print(
                    f"audit failed: contest must be 1-{latest + 1} (the next one), got {target}",
                    file=sys.stderr,
                )
                return 1
            history = load_history(conn, game, target)  # includes the target itself once it was drawn
            stored = bets_db.get_bet(conn, game, target)
    except LookupError as e:
        print(f"audit failed: {e}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    drawn = history.pop() if history and history[-1].contest == target else None
    k = args.k or (len(stored.numbers) if stored else game.bet_min_numbers)
    if not game.bet_min_numbers <= k <= game.bet_max_numbers:
        print(
            f"audit failed: k must be {game.bet_min_numbers}-{game.bet_max_numbers}, got {k}", file=sys.stderr
        )
        return 1
    ex = explain_oraculoto(game, history, k, config)

    fmt = lambda balls: " ".join(f"{b:02d}" for b in balls)  # noqa: E731
    span = f"#{history[0].contest}-#{history[-1].contest}" if history else "empty"
    print(f"{ref} for {game.name} #{target}, k = {k}, history {span} ({ex.history} contests)")
    if config_name is not None:
        print(f"config: {config_name} (not the deployed one; nothing is bet with it)")
    for step in ex.steps:
        print(f"\n[{step.number}] {step.title}")
        for note in step.notes:
            print(f"    {note}")
        if step.added:
            print(f"    + {fmt(step.added)}")
    numbers = sorted(ex.numbers)
    print(f"\nbet: {fmt(numbers)}  (picked in this order: {fmt(ex.numbers)})")

    if stored is not None:
        same = tuple(numbers) == stored.numbers
        line = f"stored bet: {fmt(stored.numbers)} ({stored.source})"
        if same:
            line += ": same"
        elif config_name is not None:
            line += ": differs with this config"
        elif stored.source != ORACULOTO.ref:
            line += f": differs, it was placed by an older version than {ORACULOTO.ref}"
        else:
            line += ": DIFFERS from the same version (history changed since it was placed?)"
        print(line)
    if drawn is not None:
        hits = sorted(set(numbers) & set(drawn.balls))
        print(
            f"drawn: {fmt(drawn.balls)}: {len(hits)} hit{'s' if len(hits) != 1 else ''}"
            + (f" ({fmt(hits)})" if hits else "")
        )
    return 0


def cmd_users(args: argparse.Namespace) -> int:
    from oraculoto.db import make_engine
    from oraculoto.db import users as db

    engine = make_engine()
    try:
        with engine.begin() as conn:
            if args.action == "list":
                for u in db.list_users(conn):
                    login = u.last_login_at.isoformat(sep=" ") if u.last_login_at else "never logged in"
                    print(f"{u.email}\t{u.role}\t{u.status}\t{login}")
                return 0
            if args.action == "invite":
                user = db.invite(conn, args.email, "admin" if args.admin else "member")
            else:
                user = db.set_status(conn, args.email, "blocked" if args.action == "block" else "active")
    except (ValueError, LookupError) as e:
        print(f"users {args.action} failed: {e}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    print(f"{user.email}: {user.role}, {user.status}")
    return 0


def cmd_db_check(args: argparse.Namespace) -> int:
    from oraculoto.db.check import run

    return run()


def cmd_dev_token(args: argparse.Namespace) -> int:
    from oraculoto.auth.keys import DevKey
    from oraculoto.config import load_env, var_dir

    load_env()
    lifetime = -120 if args.expired else args.minutes * 60  # past the 60 s leeway
    print(
        DevKey(var_dir() / "dev-key.pem").sign(
            args.email.strip().lower(),
            uid=args.uid,
            name=args.name,
            verified=not args.unverified,
            provider=args.provider,
            lifetime_seconds=lifetime,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oraculoto", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("import-xlsx", help="import Caixa's results xlsx (all or nothing)")
    p.add_argument("file", help="path to the xlsx, e.g. files/Mega-Sena.xlsx")
    p.add_argument("--game", default="megasena", help="game slug (default: megasena)")
    p.add_argument("--dry-run", action="store_true", help="parse and check only; write nothing")
    p.add_argument("--force", action="store_true", help="also overwrite contests saved from Caixa's API")
    p.add_argument("--max-warnings", type=int, default=20, help="warnings to print (default: 20)")
    p.set_defaults(func=cmd_import_xlsx)

    def backfill_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--backfill", action="store_true", help="every stored contest not yet from the API")
        p.add_argument("--from", dest="first", type=int, metavar="N", help="backfill from contest N")
        p.add_argument("--to", dest="last", type=int, metavar="M", help="backfill up to contest M")

    p = sub.add_parser("crawl-plan", help="server: print what the fetcher should request, as JSON")
    p.add_argument("--game", default="megasena", help="game slug (default: megasena)")
    backfill_args(p)
    p.set_defaults(func=cmd_crawl_plan)

    p = sub.add_parser("fetch", help="home machine: request a plan's contests from Caixa")
    p.add_argument("--game", default="megasena", help="game slug (default: megasena)")
    p.add_argument("--plan", metavar="FILE", help="follow this plan (- for stdin); print the lines")
    p.add_argument("--contest", type=int, metavar="N", help="refetch one contest")
    p.add_argument("--remote", metavar="HOST", help="ssh host: get the plan from it and ingest there")
    p.add_argument("--remote-cmd", default="oraculoto", help="oraculoto's path on the remote host")
    backfill_args(p)
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("ingest", help="server: save the fetcher's lines (stdin) through save_draw()")
    p.add_argument("--game", default="megasena", help="game slug (default: megasena)")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("bet", help="server: oraculoto bets on the next contest (once; never changed)")
    p.add_argument("--game", default="megasena", help="game slug (default: megasena)")
    p.add_argument("--k", type=int, help="how many numbers (default: the minimum bet, 6 for Mega-Sena)")
    p.set_defaults(func=cmd_bet)

    p = sub.add_parser("audit", help="server: explain where each number of oraculoto's bet comes from")
    p.add_argument("--game", default="megasena", help="game slug (default: megasena)")
    p.add_argument("--contest", type=int, metavar="N", help="the contest to explain (default: the next one)")
    p.add_argument("--k", type=int, help="how many numbers (default: the stored bet's, else the minimum bet)")
    p.add_argument(
        "--config", metavar="FILE", help="explain with this oraculoto.toml instead (- for stdin); never bets"
    )
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("users", help="the invite list: invite, block, unblock, list")
    users_sub = p.add_subparsers(dest="action", required=True)
    for action, help_text in (
        ("invite", "add an email to the invite list"),
        ("block", "refuse this user's logins"),
        ("unblock", "accept this user's logins again"),
    ):
        a = users_sub.add_parser(action, help=help_text)
        a.add_argument("email")
        if action == "invite":
            a.add_argument("--admin", action="store_true", help="role admin (no extra powers in v1)")
    users_sub.add_parser("list", help="every invited user")
    p.set_defaults(func=cmd_users)

    p = sub.add_parser(
        "db-check", help="test the database settings: DNS, TCP port, login, schema (first FAIL = the cause)"
    )
    p.set_defaults(func=cmd_db_check)

    p = sub.add_parser(
        "dev-token", help="dev: print a token signed by the local dev key (API with ORACULOTO_AUTH=dev-key)"
    )
    p.add_argument("email")
    p.add_argument("--uid", help="Firebase uid (default: derived from the email)")
    p.add_argument("--name", help="display name claim")
    p.add_argument("--minutes", type=int, default=60, help="lifetime (default: 60, as Firebase)")
    p.add_argument("--expired", action="store_true", help="already expired")
    p.add_argument("--unverified", action="store_true", help="email_verified = false")
    p.add_argument("--provider", default="google.com", help="sign_in_provider (default: google.com)")
    p.set_defaults(func=cmd_dev_token)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
