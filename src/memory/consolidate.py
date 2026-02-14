# src/memory/consolidate.py
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Any, Optional

from src.db import connect


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _now_utc_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_tags(tags_json: Optional[str]) -> List[str]:
    if not tags_json:
        return []
    try:
        v = json.loads(tags_json)
        return [str(x) for x in (v or []) if str(x).strip()]
    except Exception:
        return []


def _summarize_cluster(rows: List[Dict[str, Any]]) -> str:
    """
    ルール要約（LLMなし）。
    - user発話を優先
    - 最初の1文 + 代表キーワード少し、くらいの温度
    """
    user_texts = [r["text"].strip() for r in rows if r["source"] == "user" and (r["text"] or "").strip()]
    all_texts = [r["text"].strip() for r in rows if (r["text"] or "").strip()]

    base = (user_texts[0] if user_texts else (all_texts[0] if all_texts else "")).strip()
    base = base.replace("\n", " ")
    if len(base) > 60:
        base = base[:60] + "…"

    # 2つ目の要点（userが他にもいれば拾う）
    extra = ""
    if len(user_texts) >= 2:
        t2 = user_texts[1].replace("\n", " ")
        if len(t2) > 40:
            t2 = t2[:40] + "…"
        extra = t2

    if extra:
        return f"{base} / {extra}"
    return base


def run_consolidation(
    window_hours: int = 24,
    min_strength: float = 0.08,
    max_episodes_per_tag: int = 12,
    absorb_strength_multiplier: float = 0.5,
    delete_below: float = 0.03,
    delete_older_than_days: int = 30,
) -> Dict[str, int]:
    """
    episode -> summary の最小バッチ
    - 直近window_hoursの未吸収episodeを tags でクラスタ
    - summaryを作成してsummary_memoriesへ保存
    - 吸収されたepisodeは absorbed_into_summary_id を埋めて strength を下げる
    - strengthが十分低く、古いepisodeは自然消滅（削除）
    """
    con = connect()
    stats = {
        "episodes_considered": 0,
        "clusters": 0,
        "summaries_created": 0,
        "episodes_absorbed": 0,
        "episodes_deleted": 0,
    }

    try:
        # 直近window_hoursの未吸収episodeを取得
        rows = con.execute(
            """
            SELECT id, text, tags_json, importance, strength, source, created_at, last_access_at
            FROM episode_memories
            WHERE absorbed_into_summary_id IS NULL
            AND created_at >= datetime('now', ?)
            AND strength >= ?
            AND source = 'user'
            ORDER BY created_at ASC
            """,
            (f"-{int(window_hours)} hours", float(min_strength)),
        ).fetchall()

        episodes = [dict(r) for r in rows]
        stats["episodes_considered"] = len(episodes)

        # tag -> episodes クラスタ
        clusters: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for ep in episodes:
            tags = _parse_tags(ep.get("tags_json"))
            if not tags:
                clusters["misc"].append(ep)
                continue
            # 1エピソードが複数タグを持つ場合は、先頭タグを主タグにする（クラスタ割れ防止）
            clusters[tags[0]].append(ep)

        # まとめる順序：件数が多いtagから
        cluster_items = sorted(clusters.items(), key=lambda kv: len(kv[1]), reverse=True)
        # debug: cluster sizes
        stats["cluster_sizes"] = {k: len(v) for k, v in clusters.items()}

        for tag, eps in cluster_items:
            if tag == "misc":
                continue
            # 少なすぎるクラスタはまとめない（ノイズ防止）
            min_n = 2
            if len(eps) < min_n:
                continue


            # 上限（暴発防止）
            eps = eps[: int(max_episodes_per_tag)]

            summary_text = _summarize_cluster(eps)
            if not summary_text:
                continue

            # summaryのimportance/strength推定
            imps = [float(e["importance"]) for e in eps]
            strs = [float(e["strength"]) for e in eps]
            imp = _clamp01(max(imps) * 0.7 + (sum(imps) / max(1, len(imps))) * 0.3)
            st = _clamp01(max(strs) * (0.5 if tag == "misc" else 0.8))

            # summaryに入れるtagsは主タグ + 代表2つくらい
            tagset = [tag]
            # episode側のタグも少し混ぜる
            for e in eps:
                for t in _parse_tags(e.get("tags_json")):
                    if t not in tagset:
                        tagset.append(t)
                    if len(tagset) >= 3:
                        break
                if len(tagset) >= 3:
                    break

            episode_ids = [int(e["id"]) for e in eps]

            cur = con.execute(
                """
                INSERT INTO summary_memories
                  (summary_text, tags_json, episode_ids_json, importance, strength, source)
                VALUES
                  (?, ?, ?, ?, ?, ?)
                """,
                (
                    summary_text,
                    json.dumps(tagset, ensure_ascii=False),
                    json.dumps(episode_ids, ensure_ascii=False),
                    float(imp),
                    float(st),
                    "system",
                ),
            )
            summary_id = int(cur.lastrowid)
            stats["summaries_created"] += 1
            stats["clusters"] += 1

            # episodeを吸収扱いにし、strengthを下げる
            for eid in episode_ids:
                old = con.execute(
                    "SELECT strength FROM episode_memories WHERE id=?",
                    (int(eid),)
                ).fetchone()
                old_s = float(old["strength"]) if old else 0.0
                new_s = _clamp01(old_s * float(absorb_strength_multiplier))

                con.execute(
                    """
                    UPDATE episode_memories
                    SET absorbed_into_summary_id = ?,
                        strength = ?
                    WHERE id = ?
                    """,
                    (summary_id, float(new_s), int(eid)),
                )
                stats["episodes_absorbed"] += 1

        con.commit()
        from src.memory.narrative import update_narratives_from_summaries
        n = update_narratives_from_summaries(window_days=30, min_summaries_per_tag=2)
        stats["narrative"] = n

        # 自然消滅：古くて弱いものを削除
        # ※ summaryに吸収されていようがいまいが、十分古くて弱いなら消す
        cur = con.execute(
            """
            DELETE FROM episode_memories
            WHERE strength < ?
              AND created_at < datetime('now', ?)
            """,
            (float(delete_below), f"-{int(delete_older_than_days)} days"),
        )
        stats["episodes_deleted"] = cur.rowcount
        con.commit()

        return stats

    finally:
        con.close()
