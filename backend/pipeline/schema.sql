-- Schema for the investment pipeline. Applied on every connect(); all
-- statements are IF NOT EXISTS, so running it repeatedly is safe.

CREATE TABLE IF NOT EXISTS companies (
    id          INTEGER PRIMARY KEY,
    source      TEXT    NOT NULL,          -- 'yc' | 'hn'
    source_key  TEXT    NOT NULL,          -- yc slug, or hn story id
    name        TEXT    NOT NULL,
    website     TEXT,                      -- as submitted; may be NULL (HN text posts)
    one_liner   TEXT,
    description TEXT,
    batch       TEXT,
    team_size   INTEGER,
    industries  TEXT,                      -- JSON array, YC's own tagging
    raw_json    TEXT,                      -- the source record, unmodified
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    UNIQUE (source, source_key)
);

CREATE TABLE IF NOT EXISTS analyses (
    id          INTEGER PRIMARY KEY,
    company_id  INTEGER NOT NULL REFERENCES companies (id) ON DELETE CASCADE,
    verdict     TEXT    NOT NULL,          -- Pass | Watch | Take a meeting
    total       REAL    NOT NULL,
    scores_json TEXT    NOT NULL,          -- 5 metrics: raw, capped, evidence URLs
    model       TEXT,
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analyses_company ON analyses (company_id);

CREATE TABLE IF NOT EXISTS founders (
    id              INTEGER PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies (id) ON DELETE CASCADE,
    linkedin_slug   TEXT    NOT NULL,      -- from the YC page; LinkedIn is never fetched
    name            TEXT,                  -- from PDL when matched, else derived
    source_url      TEXT    NOT NULL,      -- the page that named this person
    discovered_via  TEXT    NOT NULL,      -- 'yc_page' | 'pdl_search'
    pdl_matched     INTEGER NOT NULL DEFAULT 0,
    current_title   TEXT,
    current_company TEXT,
    prior_roles_json TEXT,                 -- [{title, company, start, end}], newest first
    raw_json        TEXT,                  -- full PDL record; also the credit cache
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    UNIQUE (company_id, linkedin_slug)
);

CREATE INDEX IF NOT EXISTS idx_founders_company ON founders (company_id);

-- A Hacker News post is an event, not a company. One company can launch several
-- times: rowboat has three stories over eleven months, and its real traction is
-- the sum, not any single post.
CREATE TABLE IF NOT EXISTS hn_stories (
    id          INTEGER PRIMARY KEY,
    company_id  INTEGER NOT NULL REFERENCES companies (id) ON DELETE CASCADE,
    story_id    TEXT    NOT NULL UNIQUE,   -- Algolia objectID
    title       TEXT    NOT NULL,
    url         TEXT,
    points      INTEGER,
    comments    INTEGER,
    posted_at   TEXT,                      -- ISO date
    author      TEXT,                      -- HN username of the submitter
    comments_fetched_at TEXT,              -- NULL until the thread is pulled
    raw_json    TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hn_stories_company ON hn_stories (company_id);

-- Metric 2 reads this instead of columns on `companies`, so the aggregate can
-- never drift from the stories behind it.
CREATE VIEW IF NOT EXISTS company_traction AS
SELECT company_id,
       COUNT(*)          AS story_count,
       SUM(points)       AS points,
       SUM(comments)     AS comments,
       MAX(posted_at)    AS last_posted_at,
       MIN(posted_at)    AS first_posted_at
FROM hn_stories
GROUP BY company_id;

-- One public repository for each company, when there is one. Feeds metric 2
-- and metric 1's fallback tier. `missing = 1` records that we looked and found
-- nothing public, which THESIS.md treats as the instrument not applying rather
-- than as weak traction.
CREATE TABLE IF NOT EXISTS github_repos (
    company_id    INTEGER PRIMARY KEY REFERENCES companies (id) ON DELETE CASCADE,
    owner         TEXT    NOT NULL,
    repo          TEXT,
    full_name     TEXT,
    found_via     TEXT    NOT NULL,     -- website | site_link | org_search
    homepage      TEXT,                 -- the company's real address, per GitHub
    description   TEXT,
    language      TEXT,
    stars         INTEGER NOT NULL DEFAULT 0,
    forks         INTEGER NOT NULL DEFAULT 0,
    open_issues   INTEGER NOT NULL DEFAULT 0,
    contributors  INTEGER NOT NULL DEFAULT 0,
    org_followers INTEGER NOT NULL DEFAULT 0,
    is_fork       INTEGER NOT NULL DEFAULT 0,
    archived      INTEGER NOT NULL DEFAULT 0,
    gh_created_at TEXT,
    pushed_at     TEXT,                 -- recency of work, the cheap commit signal
    missing       INTEGER NOT NULL DEFAULT 0,
    raw_json      TEXT,
    checked_at    TEXT    NOT NULL,     -- the refresh window reads this
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);

-- Founders answer questions in their own launch thread: where they worked, why
-- now, who the users are. It is the only free source of a founder speaking for
-- themselves, every line has a permalink, and it is what the LLM reads when
-- scoring metrics 1 and 4.
CREATE TABLE IF NOT EXISTS hn_comments (
    id          INTEGER PRIMARY KEY,
    story_id    TEXT    NOT NULL,          -- hn_stories.story_id
    comment_id  TEXT    NOT NULL UNIQUE,   -- Algolia objectID
    author      TEXT,
    text        TEXT    NOT NULL,          -- HTML stripped
    is_op       INTEGER NOT NULL DEFAULT 0,-- written by the story submitter
    posted_at   TEXT,
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hn_comments_story ON hn_comments (story_id);
CREATE INDEX IF NOT EXISTS idx_hn_comments_op ON hn_comments (story_id, is_op);

-- A folded row must not come back. Without this, sync re-inserts the Hacker
-- News twin every run and merge deletes it again, so `added` never settles at
-- zero and "safe to re-run" stops being true.
CREATE TABLE IF NOT EXISTS merged_rows (
    source      TEXT    NOT NULL,          -- the connector the row came from
    source_key  TEXT    NOT NULL,          -- its natural key
    company_id  INTEGER NOT NULL REFERENCES companies (id) ON DELETE CASCADE,
    merged_at   TEXT    NOT NULL,
    PRIMARY KEY (source, source_key)
);
