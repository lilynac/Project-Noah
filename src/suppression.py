# suppression.py
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

JST = timezone(timedelta(hours=9))

DEFAULT_SUPPRESSION: Dict[str, Any] = {
    "version": 1,
    "updated_at": None,
    "state": {
        "initiative_suppressed_until": None,   # ISO8601 str or None
        "initiative_suppressed_reason": None,  # str or None
        "last_trigger": None,                  # ISO8601 str or None
        "cooldown_turns_remaining": 0,         # int
    },
    "counters": {
        "silent_hits": 0,
        "short_hits": 0,
        "no_question_hits": 0,
    },
}


def _now_iso() -> str:
    return datetime.now(JST).isoformat()


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    _ensure_parent_dir(path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _sup_load(path: str) -> Dict[str, Any]:
    """
    永続 suppression.json を読む。
    - 無ければ作る
    - 壊れてたら復旧（D4の「確実」を優先）
    """
    _ensure_parent_dir(path)
    if not os.path.exists(path):
        data = dict(DEFAULT_SUPPRESSION)
        data["updated_at"] = _now_iso()
        _atomic_write_json(path, data)
        return data

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = dict(DEFAULT_SUPPRESSION)
        data["updated_at"] = _now_iso()
        _atomic_write_json(path, data)
        return data

    # 最低限のマイグレーション/補完
    if not isinstance(data, dict):
        data = dict(DEFAULT_SUPPRESSION)
    data.setdefault("version", 1)
    data.setdefault("updated_at", _now_iso())
    data.setdefault("state", {})
    data.setdefault("counters", {})

    st = data["state"]
    st.setdefault("initiative_suppressed_until", None)
    st.setdefault("initiative_suppressed_reason", None)
    st.setdefault("last_trigger", None)
    st.setdefault("cooldown_turns_remaining", 0)

    ct = data["counters"]
    ct.setdefault("silent_hits", 0)
    ct.setdefault("short_hits", 0)
    ct.setdefault("no_question_hits", 0)

    return data


def _sup_save(path: str, data: Dict[str, Any]) -> None:
    data["updated_at"] = _now_iso()
    _atomic_write_json(path, data)


def _sup_detect(user_text: str) -> Dict[str, bool]:
    """
    D4用の抑制トリガ検知:
    - silent: 空/空白のみ
    - short : 短文（しきい値は強め）
    - no_question: ?/？が無い
    """
    t = (user_text or "").strip()
    if t == "":
        return {"silent": True, "short": False, "no_question": True}

    short = len(t) <= 6
    no_question = ("?" not in t) and ("？" not in t)
    return {"silent": False, "short": short, "no_question": no_question}


def _sup_update(
    data: Dict[str, Any],
    signals: Dict[str, bool],
    *,
    cooldown_turns: int = 3,
    cooldown_minutes: int = 5,
) -> Dict[str, Any]:
    """
    検知→必ず更新（D4の主因を状態化）
    - silent/short/no_question のいずれかで抑制を強化（時間＆ターン）
    - 毎ターン cooldown_turns_remaining を1減らす（下限0）
    """
    data.setdefault("state", {})
    data.setdefault("counters", {})
    st = data["state"]
    ct = data["counters"]

    # ターン減衰（毎入力で1減らす）
    try:
        st["cooldown_turns_remaining"] = max(0, int(st.get("cooldown_turns_remaining") or 0) - 1)
    except Exception:
        st["cooldown_turns_remaining"] = 0

    hit = False
    reason_parts: list[str] = []

    if signals.get("silent"):
        ct["silent_hits"] = int(ct.get("silent_hits") or 0) + 1
        reason_parts.append("silent")
        hit = True

    if signals.get("short"):
        ct["short_hits"] = int(ct.get("short_hits") or 0) + 1
        reason_parts.append("short")
        hit = True

    if signals.get("no_question"):
        ct["no_question_hits"] = int(ct.get("no_question_hits") or 0) + 1
        reason_parts.append("no_question")
        hit = True

    if hit:
        now = datetime.now(JST)
        until = now + timedelta(minutes=cooldown_minutes)
        st["initiative_suppressed_until"] = until.isoformat()
        st["initiative_suppressed_reason"] = "+".join(reason_parts)
        st["last_trigger"] = now.isoformat()

        # ターン抑制も上書き（強い方を採用）
        cur = int(st.get("cooldown_turns_remaining") or 0)
        st["cooldown_turns_remaining"] = max(cur, cooldown_turns)

    return data


def _sup_is_suppressed(data: Dict[str, Any]) -> bool:
    st = (data or {}).get("state", {})
    # ターン抑制
    try:
        if int(st.get("cooldown_turns_remaining") or 0) > 0:
            return True
    except Exception:
        pass

    # 時間抑制
    until = st.get("initiative_suppressed_until")
    if not until:
        return False
    try:
        dt_until = datetime.fromisoformat(until)
        return datetime.now(JST) < dt_until
    except Exception:
        return False


def _sup_system_prompt(data: Dict[str, Any]) -> str:
    """
    build_messages() へ常時注入する system prompt。
    モデル側にも「今は広げない」を明確に伝える。
    """
    st = (data or {}).get("state", {})
    reason = st.get("initiative_suppressed_reason") or "unknown"
    until = st.get("initiative_suppressed_until")
    turns = st.get("cooldown_turns_remaining") or 0
    suppressed = _sup_is_suppressed(data)

    return (
        "【suppression（永続状態）】\n"
        f"- initiativeは抑制中: {suppressed}\n"
        f"- 理由: {reason}\n"
        f"- until: {until}\n"
        f"- 残ターン: {turns}\n\n"
        "運用ルール:\n"
        "- 無質問/短文/静寂のとき、こちらから会話を広げない。\n"
        "- 追撃質問や提案を自発的に出さず、必要最低限の応答だけ。\n"
        "- ユーザが明確に依頼/質問した時のみ通常モード。\n"
    )
