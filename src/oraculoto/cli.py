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
