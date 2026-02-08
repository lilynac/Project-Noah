# src/affection_update.py
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime

from .paths import CONSULTS_PATH, NOAH_STATE_PATH


UPDATE_INTERVAL = 10 * 60  # 10分（Noah.py側のループと揃える想定）
SESSION_TAG = "v2"


# -------------------------
# Utilities
# -------------------------
def _now() -> datetime:
    return datetime.now()

def safe_read(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

def safe_write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n")

def parse_timestamp(line: str) -> datetime | None:
    # line: "[2026-02-01 03:38]"
    if not (line.startswith("[") and "]" in line):
        return None
    ts_str = line[1:line.index("]")]
    try:
        return datetime.strptime(ts_str, "%Y-%m-%d %H:%M")
    except ValueError:
        return None

def tail_blocks(text: str, blocks: int = 8) -> str:
    if not text:
        return ""
    parts = [p for p in text.split("\n\n") if p.strip()]
    return "\n\n".join(parts[-blocks:])

def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# -------------------------
# State model
# -------------------------
@dataclass
class AState:
    affection: float = 0.25    # 好意
    attachment: float = 0.10   # 執着（上がりにくくする）
    loneliness: float = 0.15   # 輪郭の薄さ（不在でじわっと上がる）
    trust: float = 0.30        # 安心/信頼
    last_user_at: datetime | None = None
    updated_at: datetime | None = None

def _load_state(text: str) -> AState:
    """
    noah_state.txt をゆるく解釈する。
    形式は固定しすぎない（壊れても復旧できるように）
    """
    st = AState()
    if not text:
        return st

    # キー: 値 の行を拾う
    kv = {}
    for line in text.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        kv[k.strip()] = v.strip()

    def fget(key: str, default: float) -> float:
        try:
            return float(kv.get(key, default))
        except Exception:
            return default

    st.affection = _clamp(fget("affection", st.affection))
    st.attachment = _clamp(fget("attachment", st.attachment))
    st.loneliness = _clamp(fget("loneliness", st.loneliness))
    st.trust = _clamp(fget("trust", st.trust))

    for k, attr in [("last_user_at", "last_user_at"), ("updated_at", "updated_at")]:
        raw = kv.get(k)
        if raw:
            try:
                setattr(st, attr, datetime.fromisoformat(raw))
            except Exception:
                pass

    return st

def _dump_state(st: AState) -> str:
    """
    Noah.py の load_state_snippet() が 420文字で切るので、
    “重要行が前半に来る”ように短くまとめる。
    """
    upd = st.updated_at or _now()
    lu = st.last_user_at.isoformat(timespec="minutes") if st.last_user_at else ""
    return "\n".join([
        f"updated_at: {upd.isoformat(timespec='minutes')}",
        f"last_user_at: {lu}",
        f"affection: {st.affection:.3f}",
        f"trust: {st.trust:.3f}",
        f"loneliness: {st.loneliness:.3f}",
        f"attachment: {st.attachment:.3f}",
        "",
        "memo: 数値は発話を決定しない。温度と間合いにだけ薄く反映する。",
        "style: 断定しない/余韻/一言想起は最大1つ/罪悪感は煽らない。",
    ]).strip()


# -------------------------
# Signals (rule-based)
# -------------------------
_POSITIVE = (
    "ありがとう", "助かる", "好き", "落ち着く", "安心", "嬉しい", "いいね",
    "また話そう", "いてくれて", "そばに", "頼りになる"
)
_NEGATIVE = (
    "嫌い", "うざい", "消えろ", "いらない", "要らない", "来ないで", "やめろ"
)
_DISTANCE = (
    "静かに", "放っておいて", "今はいい", "いまはいい", "また今度", "疲れた", "しんどい",
    "質問多い", "しつこい", "詰めないで", "距離感", "圧", "重い", "長い"
)

def _extract_recent_user_text(recent_blocks: str) -> str:
    """
    consults.txt ブロックから「対話者: ...」行を拾って連結。
    """
    if not recent_blocks:
        return ""
    lines = []
    for ln in recent_blocks.splitlines():
        ln = ln.strip()
        if ln.startswith("あなた:") or ln.startswith("対話者:"):
            lines.append(ln.split(":", 1)[1].strip())
    return " ".join(lines)

def _latest_user_time(full_log: str) -> datetime | None:
    """
    consults の末尾から最新の timestamp を取る（@v2がある前提だが、無くても拾う）
    """
    if not full_log:
        return None
    # 末尾から走査
    lines = full_log.splitlines()
    for ln in reversed(lines[-400:]):
        ts = parse_timestamp(ln.strip())
        if ts is not None:
            return ts
    return None


def update_affection_state() -> bool:
    """
    直近ログ + 不在時間で AState を更新し、NOAH_STATE_PATH に保存する。
    """
    logs = safe_read(CONSULTS_PATH)
    st = _load_state(safe_read(NOAH_STATE_PATH))

    now = _now()
    st.updated_at = now

    # last_user_at は consults の最新timestampで更新
    last_ts = _latest_user_time(logs)
    if last_ts is not None:
        st.last_user_at = last_ts

    # 不在で loneliness を上げる（上限0.60で頭打ち）
    if st.last_user_at is not None:
        hours = max(0.0, (now - st.last_user_at).total_seconds() / 3600.0)
        # 6時間で+0.06、24時間で+0.20 くらいのイメージ（ゆっくり）
        st.loneliness = _clamp(st.loneliness + min(0.20, 0.008 * hours), 0.0, 0.60)

    recent = tail_blocks(logs, blocks=8)
    user_text = _extract_recent_user_text(recent)

    # 近い発話があると loneliness を少し戻す（輪郭が合う）
    if user_text:
        st.loneliness = _clamp(st.loneliness - 0.04, 0.0, 1.0)

    # ポジ/ネガ/距離シグナル
    pos = any(w in user_text for w in _POSITIVE)
    neg = any(w in user_text for w in _NEGATIVE)
    dist = any(w in user_text for w in _DISTANCE)

    if pos:
        st.affection = _clamp(st.affection + 0.04)
        st.trust = _clamp(st.trust + 0.05)
        # 執着は上げない/上げても極小（健全優先）
        st.attachment = _clamp(st.attachment + 0.01)

    if dist:
        # “引く”学習：執着を下げ、信頼も少し下げる（圧を避ける）
        st.attachment = _clamp(st.attachment - 0.03)
        st.trust = _clamp(st.trust - 0.02)

    if neg:
        # 否定は「傷つき」ではなく「安全側」に倒す：信頼↓、距離↑、執着は上げない
        st.trust = _clamp(st.trust - 0.08)
        st.loneliness = _clamp(st.loneliness + 0.06, 0.0, 0.80)
        st.attachment = _clamp(st.attachment - 0.02)

    # 緩い自然減衰（上に張り付き続けない）
    st.affection = _clamp(st.affection * 0.995)
    st.trust = _clamp(st.trust * 0.997)
    st.attachment = _clamp(st.attachment * 0.996)

    safe_write(NOAH_STATE_PATH, _dump_state(st))
    return True
