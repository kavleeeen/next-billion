"""Command line entry. Holds no logic — every command calls a plain function."""
from __future__ import annotations

import argparse
import logging
import sys

from .search import DEFAULT_LIMIT, search
from .sync import sync


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)-7s %(name)s: %(message)s",
    )


def cmd_sync(args: argparse.Namespace) -> int:
    report = sync(
        batches=tuple(args.batch) if args.batch else None,
        limit=args.limit,
    )
    print(report.render())
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    report = search(args.term, limit=args.limit or DEFAULT_LIMIT)
    print(report.render())
    return 0 if report.found else 1


def build_parser() -> argparse.ArgumentParser:
    # Shared flags, accepted either before or after the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-v", "--verbose", action="store_true", help="show progress logs")

    parser = argparse.ArgumentParser(
        prog="pipeline", description="Investment pipeline", parents=[common]
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", parents=[common], help="pull sources into the database")
    p_sync.add_argument("--batch", action="append", help="YC batch, repeatable (e.g. W25)")
    p_sync.add_argument("--limit", type=int, help="cap companies per source (for testing)")
    p_sync.set_defaults(func=cmd_sync)

    p_search = sub.add_parser("search", parents=[common], help="keyword search the database")
    p_search.add_argument("term", help='e.g. "SMB founders"')
    p_search.add_argument("--limit", type=int)
    p_search.set_defaults(func=cmd_search)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
