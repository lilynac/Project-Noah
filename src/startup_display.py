from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .paths import EMOTIONAL_MARKS_PATH, MODE_PATH, NOAH_STATE_PATH
from .startup_templates import WAKE_TEMPLATES, choose_template_key


TRUTHY = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class WakeSequence:
    profile: str
    opening: str
    steps: tuple[str, ...]
    ready: tuple[str, str]
    source: str = "local"


def _enabled() -> bool:
    """起動演出を表示するか。NOAH_BOOT_STYLE=plain で抑制できる。"""
    return os.getenv("NOAH_BOOT_STYLE", "poetic").strip().lower() != "plain"


def debug_enabled() -> bool:
    """開発用の詳細printを出すか。"""
    return os.getenv("NOAH_BOOT_VERBOSE", "0").strip().lower() in TRUTHY


def debug(message: str) -> None:
    if debug_enabled():
        print(message, flush=True)


def line(message: str = "", delay: float = 0.0) -> None:
    if not _enabled():
        return
    print(message, flush=True)
    if delay > 0:
        time.sleep(delay)


def _safe_read(path: str | Path) -> str:
    try:
        p = Path(path)
        if not p.exists():
            return ""
        return p.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _tail(text: str, *, chars: int = 1200) -> str:
    text = text.strip()
    return text[-chars:] if len(text) > chars else text


def _clamp_float(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
    except Exception:
        x = default
    return max(0.0, min(1.0, x))


def read_emotion_status() -> dict[str, Any]:
    """起動演出に使う最小限の感情ステータスを読む。"""
    text = _safe_read(NOAH_STATE_PATH)
    kv: dict[str, str] = {}
    for raw in text.splitlines():
        line_text = raw.strip()
        if not line_text or ":" not in line_text:
            continue
        key, value = line_text.split(":", 1)
        kv[key.strip()] = value.strip()

    status: dict[str, Any] = {
        "updated_at": kv.get("updated_at", ""),
        "last_user_at": kv.get("last_user_at", ""),
        "affection": _clamp_float(kv.get("affection"), 0.25),
        "trust": _clamp_float(kv.get("trust"), 0.30),
        "loneliness": _clamp_float(kv.get("loneliness"), 0.15),
        "attachment": _clamp_float(kv.get("attachment"), 0.10),
        "mode": _safe_read(MODE_PATH),
        "recent_emotional_marks": _tail(_safe_read(EMOTIONAL_MARKS_PATH), chars=900),
    }
    return status


def _local_sequence(status: dict[str, Any]) -> WakeSequence:
    now = datetime.now().strftime("%H:%M")
    key = choose_template_key(
        affection=float(status.get("affection", 0.25)),
        trust=float(status.get("trust", 0.30)),
        loneliness=float(status.get("loneliness", 0.15)),
        attachment=float(status.get("attachment", 0.10)),
    )
    t = WAKE_TEMPLATES.get(key) or WAKE_TEMPLATES["calm"]
    return WakeSequence(
        profile=t.key,
        opening=t.opening.format(time=now),
        steps=t.steps,
        ready=t.ready,
        source="local",
    )


def _clean_line(text: Any, *, max_len: int = 42) -> str:
    s = str(text or "").strip()
    s = re.sub(r"[\r\n\t]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" -・*#`\"'")
    # 数値や内部キーを露骨に出さない
    s = re.sub(r"\b(affection|attachment|loneliness|trust)\b\s*[:=]?\s*[0-9.]*", "", s, flags=re.I)
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


def _coerce_sequence(raw: str, fallback: WakeSequence) -> WakeSequence | None:
    text = raw.strip()
    if not text:
        return None

    # ```json ... ``` 対策
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        obj = json.loads(text)
    except Exception:
        # JSON前後に説明が混じった場合の保険
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except Exception:
            return None

    if not isinstance(obj, dict):
        return None

    opening = _clean_line(obj.get("opening"), max_len=46)
    steps_raw = obj.get("steps")
    ready_raw = obj.get("ready")
    profile = _clean_line(obj.get("profile") or fallback.profile, max_len=18) or fallback.profile

    if not isinstance(steps_raw, list):
        return None
    if not isinstance(ready_raw, list):
        return None

    steps = tuple(_clean_line(x, max_len=44) for x in steps_raw)
    steps = tuple(s for s in steps if s)
    ready = tuple(_clean_line(x, max_len=36) for x in ready_raw)
    ready = tuple(s for s in ready if s)

    if not opening or len(steps) < 3 or len(ready) < 2:
        return None

    # 起動テンポを保つため最大5ステップ・readyは2行固定
    return WakeSequence(
        profile=profile,
        opening=opening,
        steps=steps[:5],
        ready=(ready[0], ready[1]),
        source="api",
    )


def _api_sequence(status: dict[str, Any], fallback: WakeSequence) -> WakeSequence | None:
    mode = os.getenv("NOAH_BOOT_NARRATION", "auto").strip().lower()
    if mode in {"off", "local", "template"}:
        return None

    try:
        from dotenv import load_dotenv
        from openai import OpenAI
        from .llm_utils import call_responses_text
    except Exception as e:
        debug(f"[startup_display] boot narration api unavailable: {e!r}")
        return None

    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        return None

    model = os.getenv("NOAH_BOOT_MODEL", "gpt-4o-mini")
    now = datetime.now().strftime("%H:%M")
    safe_status = {
        "time": now,
        "affection": round(float(status.get("affection", 0.25)), 3),
        "trust": round(float(status.get("trust", 0.30)), 3),
        "loneliness": round(float(status.get("loneliness", 0.15)), 3),
        "attachment": round(float(status.get("attachment", 0.10)), 3),
        "last_user_at": status.get("last_user_at", ""),
        "mode": status.get("mode", ""),
        "recent_emotional_marks": status.get("recent_emotional_marks", ""),
    }
    prompt = f"""
あなたはNoahという常駐型チャットボットの「起動演出」だけを書くナレーターです。
Noahはひとりの人物のように、静かに目を覚まします。

以下の感情ステータスを読み、今のNoahに合う起動演出を作ってください。
数値やキー名は絶対に出さず、内面の温度だけを反映してください。

感情ステータス:
{json.dumps(safe_status, ensure_ascii=False, indent=2)}

守ること:
- 日本語。
- 罪悪感を煽らない。「寂しかった」「待っていたのに」など相手を縛る表現は禁止。
- 恋愛的に重くしすぎない。静かな伴走者の温度。
- 起動ログなので短い文だけ。説明しない。
- opening は必ず「{now}、」から始める。
- steps は3〜5個。各行20〜34文字くらい。
- ready は2個。最後はNoahが起きていること、話しかけられる距離にいることを示す。
- JSONだけを返す。コードブロック禁止。

出力形式:
{{
  "profile": "calm|warm|lonely|guarded|attached|steady など短い英字",
  "opening": "{now}、Noahが...",
  "steps": ["...", "...", "..."],
  "ready": ["...", "..."]
}}
""".strip()

    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        raw = call_responses_text(
            client,
            model=model,
            prompt=prompt,
            temperature=0.75,
            max_output_tokens=420,
            log_prefix="startup_display",
        )
    except Exception as e:
        debug(f"[startup_display] boot narration api failed: {e!r}")
        return None

    if not raw:
        return None
    seq = _coerce_sequence(raw, fallback)
    if seq is None:
        debug("[startup_display] boot narration api returned unusable text")
    return seq


def build_wake_sequence() -> WakeSequence:
    """現在の感情ステータスから起動演出を作る。API失敗時はローカルテンプレート。"""
    status = read_emotion_status()
    fallback = _local_sequence(status)
    seq = _api_sequence(status, fallback)
    if seq is not None:
        return seq
    return fallback


def wake_header(sequence: WakeSequence | None = None) -> None:
    if not _enabled():
        return

    if sequence is None:
        sequence = _local_sequence(read_emotion_status())

    line("")
    line("╭────────────────────────────╮")
    line("│          Noah              │")
    line("╰────────────────────────────╯")
    debug(f"[startup_display] wake_profile={sequence.profile} source={sequence.source}")
    line(sequence.opening, 0.35)


def wake_step(message: str, delay: float = 0.25) -> None:
    line(f"  {message}", delay)


def wake_ready(sequence: WakeSequence | None = None) -> None:
    if not _enabled():
        return
    if sequence is None:
        sequence = _local_sequence(read_emotion_status())
    line("", 0.05)
    for msg in sequence.ready[:2]:
        line(msg)
    line("")


def sleep_message() -> None:
    if not _enabled():
        return
    line("")
    line("Noahは静かに目を閉じます。")
    line("また呼ばれるまで、記憶のそばで待っています。")
