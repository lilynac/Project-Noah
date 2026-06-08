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
    誤抑制を避ける検知ロジック（日本語向け）
    - no_question 単体では抑制トリガにしない（日本語は「？」無しが普通）
    - 抑制トリガは「静寂」「相槌レベルの短さ」「記号だけ」中心
    - 普通に会話している/依頼している/質問している場合は engaged=True（抑制解除の判断材料）
    戻り値:
      silent: 空/空白のみ
      short: 相槌/超短文/記号だけ（= 抑制トリガ）
      no_question: ?/？が無い（情報として保持。単体で抑制トリガにしない）
      engaged: 通常会話/依頼/質問など（= 抑制解除したい）
    """
    import re

    raw = user_text or ""
    t = raw.strip()

    # 1) 静寂
    if t == "":
        return {"silent": True, "short": False, "no_question": False, "engaged": False}

    # 2) 質問記号
    has_q = ("?" in t) or ("？" in t)

    # 3) 記号だけ（…、。、、！など）
    symbol_only = re.fullmatch(
        r"[\.\,\!\?\u3002\u3001\uFF01\uFF1F\u2026\u30FB\u3000\s]+", t
    ) is not None

    # 4) 相槌/短い肯定否定（必要なら運用で増やしてOK）
    ack_words = {
        "うん", "うーん", "はい", "ええ", "なるほど", "そう", "そうだね",
        "ok", "OK", "了解", "りょ", "ありがと", "ありがとう", "助かる",
        "まあ", "別に", "うんうん", "そうそう", "たしかに", "ほんと",
        "w", "ww", "草", "…", "。", "！", "!",
    }
    short_ack = (t.lower() in {w.lower() for w in ack_words})

    # 5) 依頼/会話継続の合図（= engaged）
    engaged_hints = (
        "教えて", "説明して", "提案して", "作って", "直して", "修正して", "確認して",
        "教えてください", "お願いします", "お願い", "どうしたら", "どうすれば",
        "なぜ", "いつ", "どこ", "どれ", "何", "どう",
    )
    engaged_hint = any(h in t for h in engaged_hints)

    # 6) 長さ（日本語は短くても会話成立するので「超短い」に寄せる）
    very_short = len(t) <= 4

    # engaged: 質問/依頼/十分な長さの説明
    engaged = has_q or engaged_hint or (len(t) >= 12 and not symbol_only)

    # short（抑制トリガ）: 記号だけ or 超短い or 相槌
    short = symbol_only or very_short or short_ack

    # no_question は情報として返す（抑制トリガには使わない想定）
    no_question = not has_q

    return {"silent": False, "short": short, "no_question": no_question, "engaged": engaged}


def _sup_update(
    data: Dict[str, Any],
    signals: Dict[str, bool],
    *,
    cooldown_turns: int = 3,
    cooldown_minutes: int = 5,
) -> Dict[str, Any]:
    """
    suppression 状態更新（誤抑制対策版）

    仕様:
    - 検知→必ず更新（updated_atは_saveで更新）
    - engaged=True のときは抑制を解除（通常会話で“かかりっぱなし”防止）
    - 抑制トリガは silent / short のみ（no_question単体では抑制しない）
    - no_question はカウンタとしては記録してよい（観測用）
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

    # engaged（通常会話/依頼/質問など）なら抑制解除
    if signals.get("engaged"):
        st["initiative_suppressed_until"] = None
        st["initiative_suppressed_reason"] = "cleared_by_engaged"
        st["last_trigger"] = _now_iso()
        st["cooldown_turns_remaining"] = 0
        return data

    hit = False
    reason_parts: list[str] = []

    # silent → 抑制
    if signals.get("silent"):
        ct["silent_hits"] = int(ct.get("silent_hits") or 0) + 1
        reason_parts.append("silent")
        hit = True

    # short（相槌/記号/超短文）→ 抑制
    if signals.get("short"):
        ct["short_hits"] = int(ct.get("short_hits") or 0) + 1
        reason_parts.append("short")
        hit = True

    # no_question は「観測カウンタ」だけ（抑制トリガにはしない）
    if signals.get("no_question"):
        ct["no_question_hits"] = int(ct.get("no_question_hits") or 0) + 1

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
