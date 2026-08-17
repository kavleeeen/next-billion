"""Pull launch-thread comments for stories that have none yet.

Free and unauthenticated, one request per thread. Threads fetch in parallel and
are written on one thread, because a SQLite connection is not safe to share.

Sync does not pull threads. It could only cover 40 per run — 5% of companies —
and it chose them by points rather than by what anyone asked for. Threads are
pulled for a selection instead, where 20 companies cost about five seconds and
coverage is complete.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import Settings, settings as default_settings
from .db import connect, hours_ago
from .repository import hn_comments as comments_repo
from .sources import hn_comments as source

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommentsReport:
    threads: int
    comments: int
    from_submitter: int
    total_comments: int
    total_op: int

    def render(self) -> str:
        return "\n".join([
            f"threads pulled      : {self.threads}",
            f"comments stored     : {self.comments}",
            f"written by founders : {self.from_submitter}",
            "-" * 38,
            f"comments in database: {self.total_comments} "
            f"({self.total_op} from founders)",
        ])


def fetch_comments(
    *,
    settings: Settings = default_settings,
    limit: int = 20,
    company_ids: list[int] | None = None,
) -> CommentsReport:
    """Pull threads in parallel, then write them.

    `company_ids` takes every thread those companies have, ignoring `limit` — a
    selected company needs all of its threads, not the loudest one. A thread
    read longer ago than settings.refresh_after_hours is read again, because
    replies keep arriving after a launch.
    """
    settings.ensure_dirs()
    stored = op = 0

    with connect(settings.db_path) as conn:
        pending = (
            comments_repo.stories_for_companies(
                conn, company_ids, hours_ago(settings.refresh_after_hours)
            ) if company_ids
            else comments_repo.stories_needing_comments(conn, limit)
        )
        if not pending:
            return CommentsReport(
                0, 0, 0, comments_repo.count(conn), comments_repo.count_op(conn)
            )

        fetched = source.fetch_many(
            [(row["story_id"], row["author"]) for row in pending],
            workers=settings.hn.comment_workers,
        )

        for story in pending:
            comments = fetched.get(story["story_id"], [])
            stored += comments_repo.upsert(conn, comments)
            op += sum(c.is_op for c in comments)
            # Marked whether or not the thread had usable comments, so an empty
            # thread is not re-fetched on every run.
            comments_repo.mark_fetched(conn, story["story_id"])

        conn.commit()
        total = comments_repo.count(conn)
        total_op = comments_repo.count_op(conn)

    return CommentsReport(len(pending), stored, op, total, total_op)
