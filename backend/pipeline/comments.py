"""Pull launch-thread comments for stories that have none yet.

Free and unauthenticated, one request per thread. Threads fetch in parallel and
are written on one thread, because a SQLite connection is not safe to share.
Highest-scoring threads go first — those are the ones a shortlist is likely to
contain.

Called at the end of sync() with a per-run ceiling, and available on its own as
`pipeline comments` for a bigger backfill.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import Settings, settings as default_settings
from .db import connect
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
    *, settings: Settings = default_settings, limit: int = 20
) -> CommentsReport:
    """Pull up to `limit` threads in parallel, then write them."""
    settings.ensure_dirs()
    stored = op = 0

    with connect(settings.db_path) as conn:
        pending = comments_repo.stories_needing_comments(conn, limit)
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
