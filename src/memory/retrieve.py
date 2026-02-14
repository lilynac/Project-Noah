# src/memory/retrieve.py
import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.db import connect
from src.memory.decay import reinforce
from src.memory.store import estimate_importance_and_tags  # 既存ルールで tags 抽出に流用


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _parse_tags(tags_json: Optional[str]) -> List[str]:
    if not tags_json:
        return []
    try:
        v = json.loads(tags_json)
        return [str(x) for x in (v or []) if str(x).strip()]
    except Exception:
        return []


def _recency_score(dt_seconds: float, tau_days: float = 7.0) -> float:
    # 0..1：新しいほど高い（指数でなめらか）
    tau = max(1e-6, tau_days * 86400.0)
    return math.exp(-dt_seconds / tau)


def _safe_dt(s: str) -> Optional[datetime]:
    # SQLite datetime('now') 由来 "YYYY-MM-DD HH:MM:SS" を想定
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _jaccard(a: List[str], b: List[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    inter = len(sa & sb)
    uni = len(sa | sb)
    return inter / uni if uni else 0.0


def _score(sim: float, strength: float, recency: float) -> float:
    # おすすめ配合：類似0.55 + strength0.35 + recency0.10
    return (0.55 * sim) + (0.35 * strength) + (0.10 * recency)


def retrieve_memories(
    query_text: str,
    top_narrative: int = 2,
    top_summary: int = 4,
    top_episode: int = 3,
    min_strength: float = 0.06,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    3階層で返す：
      narrative 少数 → summary 数件 → episode 必要最少数
    返したものは reinforce（再固定）する。
    """
    q = (query_text or "").strip()
    qtags = estimate_importance_and_tags(q, source="user").tags  # tagsだけ利用
    now = datetime.now(timezone.utc)

    con = connect()
    try:
        # narrative
        nrows = con.execute(
            """
            SELECT id, narrative_text AS text, tags_json, importance, strength, last_access_at, created_at
            FROM narrative_memories
            WHERE strength >= ?
            ORDER BY strength DESC, last_access_at DESC
            LIMIT 60
            """,
            (float(min_strength),),
        ).fetchall()

        # summary
        srows = con.execute(
            """
            SELECT id, summary_text AS text, tags_json, importance, strength, last_access_at, created_at
            FROM summary_memories
            WHERE strength >= ?
            ORDER BY strength DESC, last_access_at DESC
            LIMIT 120
            """,
            (float(min_strength),),
        ).fetchall()

        # episode（吸収済みは薄くしたいので、基本は未吸収優先）
        erows = con.execute(
            """
            SELECT id, text, tags_json, importance, strength, last_access_at, created_at, absorbed_into_summary_id
            FROM episode_memories
            WHERE strength >= ?
            ORDER BY (absorbed_into_summary_id IS NOT NULL) ASC, strength DESC, last_access_at DESC
            LIMIT 160
            """,
            (float(min_strength),),
        ).fetchall()

        def rank(rows, kind: str) -> List[Dict[str, Any]]:
            scored = []
            for r in rows:
                d = dict(r)
                tags = _parse_tags(d.get("tags_json"))
                sim = _jaccard(qtags, tags) if qtags else (1.0 if q in (d.get("text") or "") else 0.0)

                last = _safe_dt(d.get("last_access_at") or "") or _safe_dt(d.get("created_at") or "")
                if last:
                    rec = _recency_score((now - last).total_seconds(), tau_days=7.0)
                else:
                    rec = 0.0

                st = float(d.get("strength") or 0.0)
                sc = _score(sim, st, rec)

                scored.append(
                    {
                        "kind": kind,
                        "id": int(d["id"]),
                        "text": d.get("text") or "",
                        "tags": tags,
                        "importance": float(d.get("importance") or 0.0),
                        "strength": st,
                        "score": sc,
                    }
                )
            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored

        ranked_n = rank(nrows, "narrative")[: int(top_narrative)]
        ranked_s = rank(srows, "summary")[: int(top_summary)]
        ranked_e = rank(erows, "episode")[: int(top_episode)]

        # reinforce（返した分だけ）
        for it in ranked_n:
            reinforce("narrative", it["id"], 0.03)
        for it in ranked_s:
            reinforce("summary", it["id"], 0.05)
        for it in ranked_e:
            reinforce("episode", it["id"], 0.08)

        return {"narrative": ranked_n, "summary": ranked_s, "episode": ranked_e, "query_tags": qtags}

    finally:
        con.close()


def format_memory_block(mem: Dict[str, List[Dict[str, Any]]]) -> str:
    """
    Noahのプロンプトに入れるための短い文字列。
    """
    lines: List[str] = []
    qtags = mem.get("query_tags") or []
    if qtags:
        lines.append(f"query_tags: {qtags}")

    ns = mem.get("narrative") or []
    ss = mem.get("summary") or []
    es = mem.get("episode") or []

    if ns:
        lines.append("NARRATIVE:")
        for it in ns:
            lines.append(f"- {it['text']}")

    if ss:
        lines.append("SUMMARY:")
        for it in ss:
            lines.append(f"- {it['text']}")

    if es:
        lines.append("EPISODE:")
        for it in es:
            t = it["text"].replace("\n", " ")
            if len(t) > 80:
                t = t[:80] + "…"
            lines.append(f"- {t}")

    return "\n".join(lines).strip()
