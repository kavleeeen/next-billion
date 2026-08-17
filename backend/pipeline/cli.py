"""Command line entry. Holds no logic — every command calls a plain function."""
from __future__ import annotations

import argparse
import logging
import sys

from .comments import fetch_comments
from .enrich import enrich
from .enrich.pdl import MissingToken
from .prepare import MAX_SELECTION, TooManySelected, prepare
from .score import score
from .scoring.gemini import MissingToken as GeminiMissingToken
from .search import DEFAULT_LIMIT, search
from .sync import sync


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)-7s %(name)s: %(message)s",
    )


def cmd_sync(args: argparse.Namespace) -> int:
    try:
        report = sync(
            args.topic,
            batches=tuple(args.batch) if args.batch else None,
            limit=args.limit,
        )
    except ValueError as exc:
        print(exc)
        return 1
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


def cmd_prepare(args: argparse.Namespace) -> int:
    ids = [int(x) for x in args.ids.split(",") if x.strip()]
    try:
        report = prepare(ids, use_pdl=not args.no_pdl)
    except (TooManySelected, MissingToken, ValueError) as exc:
        print(exc)
        return 1
    print(report.render())
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    ids = [int(x) for x in args.ids.split(",") if x.strip()]
    try:
        report = score(ids, force=args.force)
    except (TooManySelected, GeminiMissingToken, ValueError) as exc:
        print(exc)
        return 1
    print(report.render())
    return 0



def build_parser() -> argparse.ArgumentParser:
    # Shared flags, accepted either before or after the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-v", "--verbose", action="store_true", help="show progress logs")

    parser = argparse.ArgumentParser(
        prog="pipeline", description="Investment pipeline", parents=[common]
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", parents=[common],
                            help="collect companies for a topic")
    p_sync.add_argument("topic", help='what to look for, e.g. "AI agents for SMBs"')
    p_sync.add_argument("--batch", action="append", help="YC batch, repeatable (e.g. W25)")
    p_sync.add_argument("--limit", type=int, help="cap companies per source (for testing)")
    p_sync.set_defaults(func=cmd_sync)

    p_search = sub.add_parser("search", parents=[common], help="keyword search the database")
    p_search.add_argument("term", help='e.g. "SMB founders"')
    p_search.add_argument("--limit", type=int)
    p_search.add_argument("--source", choices=("yc", "hn"),
                          help="only this connector")
    p_search.add_argument("--sort",
                          choices=("default", "points", "recent", "score", "score_asc"),
                          default="default",
                          help="default: batch; points: most HN traction; "
                               "recent: latest launch; score: highest total; "
                               "score_asc: lowest total")
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

    p_prepare = sub.add_parser("prepare", parents=[common],
                               help="get selected companies ready to score")
    p_prepare.add_argument("ids", help=f"company ids, comma separated (max {MAX_SELECTION})")
    p_prepare.add_argument("--no-pdl", action="store_true",
                           help="threads only, spend no credits")
    p_prepare.set_defaults(func=cmd_prepare)

    p_score = sub.add_parser("score", parents=[common],
                             help="score prepared companies against the thesis")
    p_score.add_argument("ids", help=f"company ids, comma separated (max {MAX_SELECTION})")
    p_score.add_argument("--force", action="store_true",
                         help="score again even if a fresh score exists")
    p_score.set_defaults(func=cmd_score)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _configure_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
