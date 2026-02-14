# src/memory/decay.py
import math
from datetime import datetime, timezone
from typing import Iterable, Tuple

from src.db import connect


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _now_iso() -> str:
    # SQLite datetime('now') はUTC扱いなので、合わせてUTCのISOを使う
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _half_life_days(importance: float, kind: str) -> float:
    """
    importance=0 -> 短い半減期
    importance=1 -> 長い半減期
    kindで少し差を付ける（narrativeは長め）
    """
    imp = _clamp01(float(importance))
    if kind == "episode":
        lo, hi = 7.0, 180.0
    elif kind == "summary":
        lo, hi = 14.0, 365.0
    else:  # narrative
        lo, hi = 30.0, 540.0
    return lo + (hi - lo) * imp


def _decay_factor(dt_days: float, half_life_days: float) -> float:
    # strength *= exp(-ln2 * dt/half_life)
    if dt_days <= 0:
        return 1.0
    return math.exp(-math.log(2.0) * (dt_days / max(1e-6, half_life_days)))


def apply_decay(kind: str, limit: int = 500) -> int:
    """
    kind: 'episode'|'summary'|'narrative'
    古い順にlimit件だけ decay を適用（軽量運用）
    """
    table = {
        "episode": "episode_memories",
        "summary": "summary_memories",
        "narrative": "narrative_memories",
    }[kind]

    con = connect()
    try:
        # last_access_at を基準に、古いものから更新
        rows = con.execute(
            f"""
            SELECT id, importance, strength, last_access_at
            FROM {table}
            ORDER BY last_access_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        updated = 0
        now = datetime.now(timezone.utc)

        for r in rows:
            _id = int(r["id"])
            importance = float(r["importance"])
            strength = float(r["strength"])
            last_access_at = r["last_access_at"]  # "YYYY-MM-DD HH:MM:SS"

            try:
                last = datetime.strptime(last_access_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                # フォーマット揺れがあればスキップ
                continue

            dt_days = (now - last).total_seconds() / 86400.0
            hl = _half_life_days(importance, kind=kind)
            factor = _decay_factor(dt_days, hl)

            new_strength = _clamp01(strength * factor)

            # 変化が小さすぎる場合は更新しない（無駄な書き込み抑制）
            if abs(new_strength - strength) < 1e-4:
                continue

            con.execute(
                f"UPDATE {table} SET strength=? WHERE id=?",
                (float(new_strength), _id),
            )
            updated += 1

        if updated:
            con.commit()
        return updated
    finally:
        con.close()


def reinforce(kind: str, memory_id: int, delta: float) -> None:
    """
    retrieve で呼ぶ想定：
    strength を少し回復 + last_access_at更新
    """
    table = {
        "episode": "episode_memories",
        "summary": "summary_memories",
        "narrative": "narrative_memories",
    }[kind]

    con = connect()
    try:
        row = con.execute(
            f"SELECT strength FROM {table} WHERE id=?",
            (int(memory_id),),
        ).fetchone()
        if not row:
            return
        s = float(row["strength"])
        d = max(0.0, float(delta))
        s2 = _clamp01(s + d * (1.0 - s))
        con.execute(
            f"UPDATE {table} SET strength=?, last_access_at=? WHERE id=?",
            (float(s2), _now_iso(), int(memory_id)),
        )
        con.commit()
    finally:
        con.close()
