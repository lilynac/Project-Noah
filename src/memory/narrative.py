# src/memory/narrative.py
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

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


def _tag_label(tag: str) -> str:
    # narrative文を自然にするためのラベル（必要なら増やしてOK）
    mapping = {
        "noah_project": "Noahの開発",
        "memory_system": "記憶の仕組み",
        "initiative": "自発発話",
        "work": "仕事",
        "study": "学習",
        "health": "体調",
        "mood": "気分",
        "relationship": "人間関係",
        "media": "趣味・コンテンツ",
        "food": "食べ物",
        "date_time": "日付・季節",
        "schedule": "予定",
        "plan": "予定",
        "project": "予定・進捗",
        "chat": "あいさつ",
        "misc": "雑談",
    }
    return mapping.get(tag, tag)


def _merge_narrative(tag: str, old_text: str, new_points: List[str]) -> str:
    """
    最小の“混ざり”：
    - 既存narrativeに、新しい要点を1〜2個だけ足して、冗長になったら丸める
    """
    label = _tag_label(tag)
    new_points = [p.strip() for p in new_points if p and p.strip()]
    new_points = new_points[:2]

    base = (old_text or "").strip()
    if not base:
        # 初回生成
        if not new_points:
            return f"最近の{label}は、まだ断片的。"
        joined = " / ".join(new_points)
        return f"最近の{label}は、{joined}。"

    # 既存がある場合：末尾に “最近は〜” を足す
    if new_points:
        joined = " / ".join(new_points)
        merged = base
        # 末尾の句点の扱いを雑に整える
        if not merged.endswith(("。", "！", "？")):
            merged += "。"
        merged += f" 最近は、{joined}。"
    else:
        merged = base

    # 長くなりすぎたら丸める（人間の記憶っぽく）
    if len(merged) > 220:
        merged = merged[:220] + "…"
    return merged


def update_narratives_from_summaries(
    window_days: int = 14,
    min_summaries_per_tag: int = 3,
    max_summaries_used: int = 6,
) -> Dict[str, int]:
    """
    summary_memories をタグで束ねて narrative_memories を更新する。
    - 1タグ1レコード（meta_json.primary_tag で管理）
    - 直近window_daysのsummaryを対象
    - 各タグで min_summaries_per_tag 以上あれば更新
    """
    con = connect()
    stats = {"tags_considered": 0, "narratives_updated": 0, "narratives_created": 0}

    try:
        rows = con.execute(
            """
            SELECT id, summary_text, tags_json, importance, strength, created_at
            FROM summary_memories
            WHERE created_at >= datetime('now', ?)
            ORDER BY created_at DESC
            """,
            (f"-{int(window_days)} days",),
        ).fetchall()

        summaries = [dict(r) for r in rows]

        by_tag: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for s in summaries:
            tags = _parse_tags(s.get("tags_json"))
            if not tags:
                continue
            primary = tags[0]
            by_tag[primary].append(s)

        stats["tags_considered"] = len(by_tag)

        for tag, items in by_tag.items():
            if tag == "misc":
                continue  # miscの自己物語は作らない（ノイズ回避）
            if len(items) < int(min_summaries_per_tag):
                continue

            # 使うsummaryを絞る（新しい順）
            items = items[: int(max_summaries_used)]
            summary_ids = [int(x["id"]) for x in items]
            points = [str(x["summary_text"]) for x in items[:2]]  # narrativeに入れる“新しい要点”は2つまで

            imps = [float(x["importance"]) for x in items]
            strs = [float(x["strength"]) for x in items]

            new_importance = _clamp01(max(imps) * 0.7 + (sum(imps) / len(imps)) * 0.3)
            new_strength = _clamp01(max(strs) * 0.85)

            meta = {"primary_tag": tag}
            meta_json = json.dumps(meta, ensure_ascii=False)

            # 既存narrativeを探す（meta_jsonでprimary_tag管理）
            existing = con.execute(
                """
                SELECT id, narrative_text, summary_ids_json, importance, strength
                FROM narrative_memories
                WHERE meta_json = ?
                LIMIT 1
                """,
                (meta_json,),
            ).fetchone()

            if existing:
                nid = int(existing["id"])
                old_text = str(existing["narrative_text"] or "")
                merged_text = _merge_narrative(tag, old_text, points)

                # 既存の根拠summaryも少し残す（最大10個）
                old_ids = []
                try:
                    old_ids = json.loads(existing["summary_ids_json"] or "[]") or []
                except Exception:
                    old_ids = []
                merged_ids = []
                for sid in summary_ids + [int(x) for x in old_ids if str(x).isdigit()]:
                    if sid not in merged_ids:
                        merged_ids.append(sid)
                    if len(merged_ids) >= 10:
                        break

                con.execute(
                    """
                    UPDATE narrative_memories
                    SET narrative_text = ?,
                        tags_json = ?,
                        summary_ids_json = ?,
                        importance = ?,
                        strength = ?,
                        last_access_at = ?
                    WHERE id = ?
                    """,
                    (
                        merged_text,
                        json.dumps([tag], ensure_ascii=False),
                        json.dumps(merged_ids, ensure_ascii=False),
                        float(new_importance),
                        float(new_strength),
                        _now_utc_str(),
                        nid,
                    ),
                )
                stats["narratives_updated"] += 1
            else:
                # 新規作成
                merged_text = _merge_narrative(tag, "", points)
                con.execute(
                    """
                    INSERT INTO narrative_memories
                      (narrative_text, tags_json, summary_ids_json, importance, strength, source, meta_json)
                    VALUES
                      (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        merged_text,
                        json.dumps([tag], ensure_ascii=False),
                        json.dumps(summary_ids[:10], ensure_ascii=False),
                        float(new_importance),
                        float(new_strength),
                        "system",
                        meta_json,
                    ),
                )
                stats["narratives_created"] += 1

        con.commit()
        return stats

    finally:
        con.close()
