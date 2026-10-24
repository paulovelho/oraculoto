"""Command line: `oraculoto <command>`. Run `oraculoto --help` for the list."""

import argparse
import sys

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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
