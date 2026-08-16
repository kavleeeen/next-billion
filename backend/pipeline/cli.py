"""Command line entry. Holds no logic — every command calls a plain function."""
from __future__ import annotations

import argparse
import logging
import sys

from .comments import fetch_comments
from .enrich import enrich
from .enrich.pdl import MissingToken
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
        comments=args.comments,
    )
    print(report.render())
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    report = search(
        args.term, limit=args.limit or DEFAULT_LIMIT,
        source=args.source, sort=args.sort,
    )
    print(report.render())
    return 0 if report.found else 1


def cmd_enrich(args: argparse.Namespace) -> int:
    try:
        report = enrich(
            limit=args.limit, use_pdl=not args.no_pdl,
            source=args.source, force=args.force,
        )
    except MissingToken as exc:
        print(exc)
        return 1
    print(report.render())
    return 0


def cmd_comments(args: argparse.Namespace) -> int:
    print(fetch_comments(limit=args.limit).render())
    return 0



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
    p_sync.add_argument("--comments", type=int,
                        help="HN threads to pull at the end; 0 to skip")
    p_sync.set_defaults(func=cmd_sync)

    p_search = sub.add_parser("search", parents=[common], help="keyword search the database")
    p_search.add_argument("term", help='e.g. "SMB founders"')
    p_search.add_argument("--limit", type=int)
    p_search.add_argument("--source", choices=("yc", "hn"),
                          help="only this connector")
    p_search.add_argument("--sort", choices=("default", "points", "recent"),
                          default="default",
                          help="default: batch; points: most HN traction; "
                               "recent: latest launch")
    p_search.set_defaults(func=cmd_search)

    p_enrich = sub.add_parser("enrich", parents=[common],
                              help="attach founders to companies (uses PDL credits)")
    p_enrich.add_argument("--limit", type=int, default=5,
                          help="companies to process; ~2 credits each (default 5)")
    p_enrich.add_argument("--source", choices=("yc", "hn"),
                          help="only enrich companies from this connector")
    p_enrich.add_argument("--force", action="store_true",
                          help="re-buy founders for companies that already have them")
    p_enrich.add_argument("--no-pdl", action="store_true",
                          help="scrape founder slugs only, spend no credits")
    p_enrich.set_defaults(func=cmd_enrich)

    p_comments = sub.add_parser("comments", parents=[common],
                                help="pull Hacker News launch threads (free)")
    p_comments.add_argument("--limit", type=int, default=20, help="threads to pull")
    p_comments.set_defaults(func=cmd_comments)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
