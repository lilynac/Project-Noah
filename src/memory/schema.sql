CREATE TABLE IF NOT EXISTS summary_memories (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,

  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  last_access_at  TEXT NOT NULL DEFAULT (datetime('now')),

  summary_text    TEXT NOT NULL,

  tags_json       TEXT,  -- JSON array of strings
  episode_ids_json TEXT, -- JSON array of episode ids

  importance      REAL NOT NULL DEFAULT 0.5 CHECK (importance >= 0 AND importance <= 1),
  strength        REAL NOT NULL DEFAULT 0.5 CHECK (strength >= 0 AND strength <= 1),

  source          TEXT NOT NULL DEFAULT 'system' CHECK (source IN ('user','noah','system')),

  meta_json       TEXT  -- future use (e.g., reasons, model info, etc.)
);

CREATE INDEX IF NOT EXISTS idx_summary_strength_access
  ON summary_memories(strength DESC, last_access_at DESC);

CREATE INDEX IF NOT EXISTS idx_summary_created
  ON summary_memories(created_at DESC);


CREATE TABLE IF NOT EXISTS episode_memories (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,

  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  last_access_at  TEXT NOT NULL DEFAULT (datetime('now')),

  text            TEXT NOT NULL,

  tags_json       TEXT,  -- JSON array of strings

  importance      REAL NOT NULL DEFAULT 0.3 CHECK (importance >= 0 AND importance <= 1),
  strength        REAL NOT NULL DEFAULT 0.6 CHECK (strength >= 0 AND strength <= 1),

  source          TEXT NOT NULL CHECK (source IN ('user','noah','system')),

  importance_reasons_json TEXT, -- JSON array of strings

  absorbed_into_summary_id INTEGER,
  FOREIGN KEY(absorbed_into_summary_id) REFERENCES summary_memories(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_episode_strength_access
  ON episode_memories(strength DESC, last_access_at DESC);

CREATE INDEX IF NOT EXISTS idx_episode_created
  ON episode_memories(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_episode_absorbed
  ON episode_memories(absorbed_into_summary_id);


CREATE TABLE IF NOT EXISTS narrative_memories (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,

  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  last_access_at  TEXT NOT NULL DEFAULT (datetime('now')),

  narrative_text  TEXT NOT NULL,

  tags_json       TEXT,  -- JSON array of strings
  summary_ids_json TEXT, -- JSON array of summary ids

  importance      REAL NOT NULL DEFAULT 0.7 CHECK (importance >= 0 AND importance <= 1),
  strength        REAL NOT NULL DEFAULT 0.7 CHECK (strength >= 0 AND strength <= 1),

  source          TEXT NOT NULL DEFAULT 'system' CHECK (source IN ('user','noah','system')),

  meta_json       TEXT
);

CREATE INDEX IF NOT EXISTS idx_narrative_strength_access
  ON narrative_memories(strength DESC, last_access_at DESC);

CREATE INDEX IF NOT EXISTS idx_narrative_created
  ON narrative_memories(created_at DESC);


-- Optional: meta table for bookkeeping (e.g. last consolidation run)
CREATE TABLE IF NOT EXISTS memory_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
