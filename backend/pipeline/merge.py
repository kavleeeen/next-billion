"""Fold a company's Hacker News row into its Y Combinator row.

The two sources carry disjoint evidence. Measured over 1,038 companies:

    source  long_desc  team_size  hn_traction
    yc         485        517          0
    hn           0          0        509

No company had both, so metric 2 could never see launch traction for a YC
company, and metrics 3 to 5 judged a Hacker News company on a post title. 34
companies were present in both sources as two separate rows.

The YC row survives, because it carries the richer fields.

Three rules keep this safe:

  * The batch code is a second key. Of the 34 pairs, 29 had a batch on both
    rows and every one agreed, 5 had none on the HN side, and none conflicted.
    A conflicting batch blocks the merge.
  * A name matching more than one YC row is skipped, not guessed. Live data
    already holds one: `candor` and `candor-security` are both named "Candor"
    and both W25, so neither the name nor the batch can separate them.
  * The fold is recorded in `merged_rows` before the row is deleted, so the
    next sync knows not to re-create it.
"""
from __future__ import annotations

import logging
import sqlite3

from .db import utcnow

log = logging.getLogger(__name__)

# Pairs to fold. The subquery is the ambiguity guard: a name that matches more
# than one YC row cannot be resolved by name or batch, so it is left alone.
PAIRS = """
SELECT y.id AS keep_id, h.id AS drop_id, y.name AS name,
       h.source AS drop_source, h.source_key AS drop_key
FROM companies y
JOIN companies h
  ON lower(trim(h.name)) = lower(trim(y.name))
 AND h.source = 'hn'
WHERE y.source = 'yc'
  AND (h.batch IS NULL OR h.batch = y.batch)
  AND (SELECT COUNT(*) FROM companies y2
       WHERE y2.source = 'yc'
         AND lower(trim(y2.name)) = lower(trim(y.name))) = 1
"""

AMBIGUOUS = """
SELECT DISTINCT lower(trim(y.name)) AS name, COUNT(*) AS yc_rows
FROM companies y
JOIN companies h
  ON lower(trim(h.name)) = lower(trim(y.name)) AND h.source = 'hn'
WHERE y.source = 'yc'
GROUP BY lower(trim(y.name))
HAVING COUNT(*) > 1
"""

BACKFILL = """
UPDATE companies SET
    website   = COALESCE(website,   (SELECT website   FROM companies WHERE id = :drop_id)),
    one_liner = COALESCE(one_liner, (SELECT one_liner FROM companies WHERE id = :drop_id))
WHERE id = :keep_id
"""

REPOINT_STORIES = "UPDATE hn_stories SET company_id = :keep_id WHERE company_id = :drop_id"

# Drop the losing side of a founder collision BEFORE re-pointing. `UPDATE OR
# REPLACE` would delete the row that is already on the surviving company and
# keep the incoming one — discarding a yc_page founder with paid-for prior
# roles in favour of an inferred pdl_search row with none.
DROP_DUPLICATE_FOUNDERS = """
DELETE FROM founders
WHERE company_id = :drop_id
  AND linkedin_slug IN (SELECT linkedin_slug FROM founders WHERE company_id = :keep_id)
"""

REPOINT_FOUNDERS = "UPDATE founders SET company_id = :keep_id WHERE company_id = :drop_id"

# Recorded before the delete, so sync can suppress the row next time instead of
# re-inserting it and merging it again on every run.
RECORD = """
INSERT INTO merged_rows (source, source_key, company_id, merged_at)
VALUES (:drop_source, :drop_key, :keep_id, :now)
ON CONFLICT (source, source_key) DO UPDATE SET
    company_id = excluded.company_id,
    merged_at  = excluded.merged_at
"""

DELETE = "DELETE FROM companies WHERE id = :drop_id"


def merge_cross_source(conn: sqlite3.Connection) -> int:
    """Fold every unambiguous HN row into its YC twin. Returns how many merged.

    Called at the end of sync(), after both sources have been written.
    """
    for row in conn.execute(AMBIGUOUS).fetchall():
        log.warning(
            "skipping merge for %r: %s YC rows share that name, so neither the "
            "name nor the batch identifies which one the HN post belongs to",
            row["name"], row["yc_rows"],
        )

    merged = 0
    for pair in conn.execute(PAIRS).fetchall():
        params = {
            "keep_id": pair["keep_id"],
            "drop_id": pair["drop_id"],
            "drop_source": pair["drop_source"],
            "drop_key": pair["drop_key"],
            "now": utcnow(),
        }
        conn.execute(BACKFILL, params)
        conn.execute(REPOINT_STORIES, params)
        conn.execute(DROP_DUPLICATE_FOUNDERS, params)
        conn.execute(REPOINT_FOUNDERS, params)
        conn.execute(RECORD, params)
        conn.execute(DELETE, params)
        merged += 1
        log.info("merged hn row into yc row: %s", pair["name"])

    return merged
