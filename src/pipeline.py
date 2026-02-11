# src/pipeline.py
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from src.db import connect, init_db
from src.scoring import EMOTIONS, merge_deltas, apply_decay, apply_delta, summarize
from src.narrative_rules import narrative_from_scores

def get_or_create_entity(con, name: str, etype: str) -> int:
    row = con.execute(
        "SELECT id FROM entities WHERE canonical_name=? AND type=?",
        (name, etype)
    ).fetchone()
    if row:
        return int(row["id"])

    con.execute("INSERT INTO entities (canonical_name, type) VALUES (?,?)", (name, etype))
    entity_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])

    con.execute("INSERT OR IGNORE INTO entity_scores (entity_id) VALUES (?)", (entity_id,))
    return entity_id

def upsert_aliases(con, entity_id: int, aliases: List[str]) -> None:
    for a in aliases or []:
        con.execute(
            "INSERT OR IGNORE INTO entity_aliases (entity_id, alias) VALUES (?,?)",
            (entity_id, a)
        )

def upsert_tags(con, entity_id: int, tags: List[str]) -> None:
    for t in tags or []:
        con.execute(
            "INSERT OR IGNORE INTO entity_tags (entity_id, tag) VALUES (?,?)",
            (entity_id, t)
        )

def resolve_entity_id(con, name: str) -> Optional[int]:
    row = con.execute("SELECT id FROM entities WHERE canonical_name=?", (name,)).fetchone()
    if row:
        return int(row["id"])
    row = con.execute("""
        SELECT e.id FROM entity_aliases a
        JOIN entities e ON e.id=a.entity_id
        WHERE a.alias=?
    """, (name,)).fetchone()
    if row:
        return int(row["id"])
    return None

def load_scores(con, entity_id: int):
    row = con.execute("SELECT * FROM entity_scores WHERE entity_id=?", (entity_id,)).fetchone()
    scores_i = {e: float(row[f"{e}_i"]) for e in EMOTIONS}
    scores_b = {e: float(row[f"{e}_b"]) for e in EMOTIONS}
    decay_i = float(row["impression_decay"])
    decay_b = float(row["belief_decay"])
    return scores_i, scores_b, decay_i, decay_b

def save_scores(con, entity_id: int, scores_i: dict, scores_b: dict) -> None:
    cols = []
    vals = []
    for e in EMOTIONS:
        cols += [f"{e}_i", f"{e}_b"]
        vals += [scores_i[e], scores_b[e]]
    set_clause = ", ".join([f"{c}=?" for c in cols] + ["updated_at=datetime('now')"])
    con.execute(f"UPDATE entity_scores SET {set_clause} WHERE entity_id=?", (*vals, entity_id))

def insert_event(con, entity_id: int, obs: Dict[str, Any], delta: Dict[str, float]) -> int:
    stance_json = json.dumps(obs.get("stance", {}), ensure_ascii=False)
    delta_json = json.dumps({f"{k}_i": v for k, v in delta.items()}, ensure_ascii=False)

    con.execute("""
      INSERT INTO events (entity_id, source, evidence_text, intensity, confidence, stance_json, delta_json)
      VALUES (?,?,?,?,?,?,?)
    """, (
        entity_id,
        obs.get("source", "other"),
        obs.get("evidence_text", ""),
        float(obs.get("intensity", 1.0)),
        float(obs.get("confidence", 0.8)),
        stance_json,
        delta_json
    ))
    event_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])

    for t in obs.get("event_tags", []) or []:
        con.execute("INSERT OR IGNORE INTO event_tags (event_id, tag) VALUES (?,?)", (event_id, t))

    return event_id

def apply_observation(con, obs: Dict[str, Any]) -> None:
    name = obs["entity_name"]

    entity_id = resolve_entity_id(con, name)
    if entity_id is None:
        entity_id = get_or_create_entity(con, name, "other")

    tags = obs.get("event_tags", []) or []
    intensity = float(obs.get("intensity", 1.0))

    delta = merge_deltas(tags, intensity=intensity)

    scores_i, scores_b, decay_i, decay_b = load_scores(con, entity_id)
    apply_decay(scores_i, scores_b, decay_i=decay_i, decay_b=decay_b)
    apply_delta(scores_i, scores_b, delta, belief_weight=0.35)
    save_scores(con, entity_id, scores_i, scores_b)

    insert_event(con, entity_id, obs, delta)

    total = summarize(scores_i, scores_b)
    n = narrative_from_scores(total)
    if n:
        # 同じ entity_id + trigger_condition が既にあれば更新、なければ追加
        existing = con.execute("""
          SELECT id FROM narratives
          WHERE entity_id=? AND trigger_condition=?
        """, (entity_id, n["trigger_condition"])).fetchone()

        if existing:
            con.execute("""
              UPDATE narratives
              SET line_external=?,
                  behavior_hint=?,
                  priority=?,
                  updated_at=datetime('now')
              WHERE id=?
            """, (
              n["line_external"],
              n.get("behavior_hint"),
              10,
              int(existing["id"])
            ))
        else:
            con.execute("""
              INSERT INTO narratives (entity_id, trigger_condition, line_external, behavior_hint, priority)
              VALUES (?,?,?,?,?)
            """, (
              entity_id,
              n["trigger_condition"],
              n["line_external"],
              n.get("behavior_hint"),
              10
            ))

def apply_patch(patch: Dict[str, Any]) -> None:
    con = connect()
    try:
        con.execute("BEGIN")

        for ent in patch.get("entities", []) or []:
            name = ent["name"]
            etype = ent.get("type", "other")
            entity_id = get_or_create_entity(con, name, etype)
            upsert_aliases(con, entity_id, ent.get("aliases", []))
            upsert_tags(con, entity_id, ent.get("tags", []))

        for obs in patch.get("observations", []) or []:
            apply_observation(con, obs)

        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

if __name__ == "__main__":
    init_db()

    test_patch = {
    "entities":[{"name":"りんこ","type":"person","aliases":["凛子"],"tags":["friend","romance_candidate"]}],
    "observations":[
        {
        "entity_name":"りんこ",
        "source":"conversation",
        "event_tags":["boundary_violation","manipulation","insult"],
        "intensity":1.0,
        "confidence":0.9,
        "stance":{"empathy":0.2,"skepticism":0.8,"curiosity":0.2},
        "evidence_text":"強めに踏み込まれ、操作されている感じと棘のある言い方が重なって引っかかった。"
        }
    ]
    }

    apply_patch(test_patch)
    print("applied patch ✅")
