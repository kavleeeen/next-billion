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
