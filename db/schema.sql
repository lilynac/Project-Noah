PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS entities (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_name TEXT NOT NULL,
  type          TEXT NOT NULL CHECK (type IN (
                  'person','work','character','concept','organization','place','other'
                )),
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_unique
  ON entities(canonical_name, type);

CREATE TABLE IF NOT EXISTS entity_aliases (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id  INTEGER NOT NULL,
  alias      TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_alias_unique
  ON entity_aliases(alias);

CREATE TABLE IF NOT EXISTS entity_tags (
  entity_id  INTEGER NOT NULL,
  tag        TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (entity_id, tag),
  FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS entity_scores (
  entity_id   INTEGER PRIMARY KEY,

  joy_i           REAL NOT NULL DEFAULT 0,
  trust_i         REAL NOT NULL DEFAULT 0,
  fear_i          REAL NOT NULL DEFAULT 0,
  surprise_i      REAL NOT NULL DEFAULT 0,
  sadness_i       REAL NOT NULL DEFAULT 0,
  disgust_i       REAL NOT NULL DEFAULT 0,
  anger_i         REAL NOT NULL DEFAULT 0,
  anticipation_i  REAL NOT NULL DEFAULT 0,

  joy_b           REAL NOT NULL DEFAULT 0,
  trust_b         REAL NOT NULL DEFAULT 0,
  fear_b          REAL NOT NULL DEFAULT 0,
  surprise_b      REAL NOT NULL DEFAULT 0,
  sadness_b       REAL NOT NULL DEFAULT 0,
  disgust_b       REAL NOT NULL DEFAULT 0,
  anger_b         REAL NOT NULL DEFAULT 0,
  anticipation_b  REAL NOT NULL DEFAULT 0,

  confidence      REAL NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),

  impression_decay REAL NOT NULL DEFAULT 0.92 CHECK (impression_decay > 0 AND impression_decay <= 1),
  belief_decay     REAL NOT NULL DEFAULT 0.995 CHECK (belief_decay > 0 AND belief_decay <= 1),

  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id   INTEGER NOT NULL,

  source      TEXT NOT NULL CHECK (source IN ('conversation','research','memory','other')),
  occurred_at TEXT NOT NULL DEFAULT (datetime('now')),

  evidence_text TEXT NOT NULL,

  intensity   REAL NOT NULL DEFAULT 1 CHECK (intensity >= 0 AND intensity <= 1),
  confidence  REAL NOT NULL DEFAULT 0.8 CHECK (confidence >= 0 AND confidence <= 1),

  stance_json TEXT,
  delta_json  TEXT,

  FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_events_entity_time
  ON events(entity_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS event_tags (
  event_id   INTEGER NOT NULL,
  tag        TEXT NOT NULL,
  PRIMARY KEY (event_id, tag),
  FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_event_tags_tag
  ON event_tags(tag);

CREATE TABLE IF NOT EXISTS narratives (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_id   INTEGER NOT NULL,

  trigger_condition TEXT NOT NULL,

  line_internal  TEXT,
  line_external  TEXT NOT NULL,

  behavior_hint  TEXT,
  grounding_json TEXT,

  priority    INTEGER NOT NULL DEFAULT 0,

  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now')),

  FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_narratives_entity_priority
  ON narratives(entity_id, priority DESC, updated_at DESC);

CREATE TABLE IF NOT EXISTS entity_activity (
  entity_id     INTEGER PRIMARY KEY,
  last_mentioned_at TEXT NOT NULL DEFAULT (datetime('now')),
  mention_count INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
);

CREATE TRIGGER IF NOT EXISTS trg_entities_updated
AFTER UPDATE ON entities
FOR EACH ROW
BEGIN
  UPDATE entities SET updated_at = datetime('now') WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_entity_scores_updated
AFTER UPDATE ON entity_scores
FOR EACH ROW
BEGIN
  UPDATE entity_scores SET updated_at = datetime('now') WHERE entity_id = OLD.entity_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_narratives_updated
AFTER UPDATE ON narratives
FOR EACH ROW
BEGIN
  UPDATE narratives SET updated_at = datetime('now') WHERE id = OLD.id;
END;

-- =========================================================
-- Task3: Human-like Memory (episode / summary / narrative)
-- =========================================================

CREATE TABLE IF NOT EXISTS summary_memories (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,

  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  last_access_at  TEXT NOT NULL DEFAULT (datetime('now')),

  summary_text    TEXT NOT NULL,

  tags_json       TEXT,
  episode_ids_json TEXT,

  importance      REAL NOT NULL DEFAULT 0.5 CHECK (importance >= 0 AND importance <= 1),
  strength        REAL NOT NULL DEFAULT 0.5 CHECK (strength >= 0 AND strength <= 1),

  source          TEXT NOT NULL DEFAULT 'system' CHECK (source IN ('user','noah','system')),

  meta_json       TEXT
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

  tags_json       TEXT,

  importance      REAL NOT NULL DEFAULT 0.3 CHECK (importance >= 0 AND importance <= 1),
  strength        REAL NOT NULL DEFAULT 0.6 CHECK (strength >= 0 AND strength <= 1),

  source          TEXT NOT NULL CHECK (source IN ('user','noah','system')),

  importance_reasons_json TEXT,

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

  tags_json       TEXT,
  summary_ids_json TEXT,

  importance      REAL NOT NULL DEFAULT 0.7 CHECK (importance >= 0 AND importance <= 1),
  strength        REAL NOT NULL DEFAULT 0.7 CHECK (strength >= 0 AND strength <= 1),

  source          TEXT NOT NULL DEFAULT 'system' CHECK (source IN ('user','noah','system')),

  meta_json       TEXT
);

CREATE INDEX IF NOT EXISTS idx_narrative_strength_access
  ON narrative_memories(strength DESC, last_access_at DESC);

CREATE INDEX IF NOT EXISTS idx_narrative_created
  ON narrative_memories(created_at DESC);


CREATE TABLE IF NOT EXISTS memory_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

