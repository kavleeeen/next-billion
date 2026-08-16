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

-- Credits are a shared monthly budget, so the spend has to outlive one process.
-- max_calls_per_run alone bounds a single call; N HTTP requests would otherwise
-- allow N x that against a 100/month plan.
CREATE TABLE IF NOT EXISTS pdl_usage (
    id        INTEGER PRIMARY KEY,
    called_at TEXT    NOT NULL,     -- ISO timestamp
    calls     INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pdl_usage_at ON pdl_usage (called_at);
