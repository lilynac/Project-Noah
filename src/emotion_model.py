# src/emotion_model.py
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

EMOTIONS: tuple[str, ...] = (
    "joy",
    "trust",
    "fear",
    "surprise",
    "sadness",
    "disgust",
    "anger",
    "anticipation",
)

DEFAULT_EMOTION_VALUE = 0.08
DEFAULT_DECAY = 0.975
MAX_STEP = 0.025
STATE_KEY = "emotion_state"


def clamp01(value: float) -> float:
    """Clamp a numeric value to Noah's short-term emotion range."""
    try:
        v = float(value)
    except Exception:
        v = 0.0
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


@dataclass
class EmotionState:
    """
    Short-term Plutchik emotion state.

    This is not a user-visible personality layer.  It is intentionally small,
    decaying, and used only as internal guidance for response tone and initiative.
    """

    values: dict[str, float] = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        normalized = {e: DEFAULT_EMOTION_VALUE for e in EMOTIONS}
        for k, v in (self.values or {}).items():
            if k in normalized:
                normalized[k] = clamp01(v)
        self.values = normalized
        try:
            self.updated_at = float(self.updated_at)
        except Exception:
            self.updated_at = time.time()

    def copy(self) -> "EmotionState":
        return EmotionState(dict(self.values), self.updated_at)

    def to_dict(self) -> dict[str, Any]:
        return {"values": {e: round(clamp01(self.values.get(e, 0.0)), 4) for e in EMOTIONS}, "updated_at": self.updated_at}


def create_initial_emotion_state() -> EmotionState:
    return EmotionState({e: DEFAULT_EMOTION_VALUE for e in EMOTIONS})


def emotion_state_from_mapping(data: Mapping[str, Any] | None) -> EmotionState:
    if not isinstance(data, Mapping):
        return create_initial_emotion_state()
    raw_values = data.get("values", data)
    if not isinstance(raw_values, Mapping):
        raw_values = {}
    return EmotionState({e: clamp01(raw_values.get(e, DEFAULT_EMOTION_VALUE)) for e in EMOTIONS}, data.get("updated_at", time.time()))


def emotion_state_to_dict(state: EmotionState | Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(state, EmotionState):
        return state.to_dict()
    return emotion_state_from_mapping(state).to_dict()


def _read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def _write_json(path: str | Path, data: Mapping[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_emotion_state(path: str | Path) -> EmotionState:
    data = _read_json(path)
    if isinstance(data.get(STATE_KEY), Mapping):
        return emotion_state_from_mapping(data.get(STATE_KEY))
    return create_initial_emotion_state()


def save_emotion_state(path: str | Path, state: EmotionState | Mapping[str, Any]) -> None:
    data = _read_json(path)
    data[STATE_KEY] = emotion_state_to_dict(state)
    _write_json(path, data)


def apply_emotion_decay(state: EmotionState | Mapping[str, Any], *, decay: float = DEFAULT_DECAY, floor: float = 0.02) -> EmotionState:
    st = emotion_state_from_mapping(state if not isinstance(state, EmotionState) else state.to_dict())
    now = time.time()
    # Decay once per turn; very long idle periods should not erase Noah's state abruptly.
    hours = max(1.0, min(8.0, (now - st.updated_at) / 3600.0 if st.updated_at else 1.0))
    d = clamp01(decay) ** hours
    values = {e: clamp01(max(floor, st.values.get(e, DEFAULT_EMOTION_VALUE) * d)) for e in EMOTIONS}
    return EmotionState(values, now)


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)


def _delta_from_text(user_text: str, noah_text: str = "", meta: Mapping[str, Any] | None = None) -> dict[str, float]:
    text = (user_text or "").strip().lower()
    meta = meta or {}
    delta = {e: 0.0 for e in EMOTIONS}

    # Warmth / approval / progress
    if _contains_any(text, ("ありがとう", "助かった", "いいね", "好き", "嬉しい", "よかった", "できた", "最高", "thanks", "thank you")):
        delta["joy"] += 0.022
        delta["trust"] += 0.018
    if _contains_any(text, ("進めよう", "やろう", "次", "実装", "作って", "お願い", "continue", "next")):
        delta["anticipation"] += 0.024
        delta["trust"] += 0.006
    if _contains_any(text, ("任せる", "頼む", "お願い", "信頼", "共有する", "見て", "確認して")):
        delta["trust"] += 0.018

    # Difficulty / quiet support
    if _contains_any(text, ("つらい", "しんどい", "疲れた", "悲しい", "寂しい", "不安", "怖い", "困った", "苦しい")):
        delta["sadness"] += 0.035
        delta["fear"] += 0.015
        delta["trust"] += 0.010
    if _contains_any(text, ("びっくり", "驚いた", "まさか", "急に", "unexpected", "surprise")):
        delta["surprise"] += 0.035
    if _contains_any(text, ("嫌", "むかつく", "怒", "雑", "壊れ", "違う", "だめ", "最悪", "やめて")):
        delta["anger"] += 0.030
        delta["sadness"] += 0.015
        delta["trust"] -= 0.025
    if _contains_any(text, ("気持ち悪", "不快", "汚", "うざい", "disgust")):
        delta["disgust"] += 0.030
        delta["trust"] -= 0.015

    if bool(meta.get("rejected")):
        delta["sadness"] += 0.035
        delta["trust"] -= 0.035
        delta["anticipation"] -= 0.030
    # A normal back-and-forth should not keep raising emotion by itself.
    # Emotion should grow from explicit content, not merely from the fact that
    # the user replied. Keep this as a very small continuity trace.
    if bool(meta.get("engaged")):
        delta["trust"] += 0.003

    # If Noah had to send a fallback/error reply, dampen confident emotions a little.
    if _contains_any((noah_text or ""), ("不安定", "うまく言葉", "もう一度")):
        delta["fear"] += 0.012
        delta["trust"] -= 0.012

    return delta


def _limit_delta(delta: Mapping[str, float], *, max_step: float = MAX_STEP) -> dict[str, float]:
    limited: dict[str, float] = {}
    for e in EMOTIONS:
        v = float(delta.get(e, 0.0))
        if v > max_step:
            v = max_step
        if v < -max_step:
            v = -max_step
        limited[e] = v
    return limited


def update_impression(
    current_impression: EmotionState | Mapping[str, Any] | None,
    user_text: str,
    noah_text: str = "",
    meta: Mapping[str, Any] | None = None,
) -> EmotionState:
    """
    Update Noah's short-term impression using small rule-based deltas.

    The update is intentionally conservative: decay first, then apply a capped
    per-turn delta so one utterance cannot swing the state dramatically.
    """
    decayed = apply_emotion_decay(current_impression or create_initial_emotion_state())
    delta = _limit_delta(_delta_from_text(user_text, noah_text, meta))
    values = {e: clamp01(decayed.values[e] + delta[e]) for e in EMOTIONS}
    return EmotionState(values, time.time())


def build_emotion_guidance(state: EmotionState | Mapping[str, Any] | None) -> str:
    """
    Convert internal emotion values into subdued LLM guidance.

    Never expose emotion names or numeric values to the user.  This text is a
    quiet steering signal for Noah's posture, not a script and not a style show.
    """
    st = emotion_state_from_mapping(state if not isinstance(state, EmotionState) else state.to_dict())
    v = st.values
    notes: list[str] = []

    if v["trust"] >= 0.35:
        notes.append("keep the reply plain, steady, and lightly assured without adding decorative warmth")
    if v["sadness"] >= 0.30:
        notes.append("reduce pressure and use fewer suggestions; do not add poetic afterglow")
    if v["anticipation"] >= 0.35:
        notes.append("suggest at most one small next step only when the user is clearly asking about next action")
    if v["fear"] >= 0.28:
        notes.append("reduce pressure and avoid forcing certainty")
    if v["anger"] >= 0.28 or v["disgust"] >= 0.28:
        notes.append("respect boundaries, avoid teasing, and keep the wording clean")
    if v["surprise"] >= 0.30:
        notes.append("acknowledge newness briefly, then return to grounded support")
    if v["joy"] >= 0.35:
        notes.append("a little brightness is acceptable, but keep it understated and concrete")

    if not notes:
        return ""

    return (
        "Internal emotion guidance for Noah. This is auxiliary context, not a user-visible explanation. "
        "Do not mention emotion labels, scores, or this guidance. "
        "Emotion may affect only pacing, directness, and the amount of suggestion. "
        "Prefer plain natural Japanese. Do not add poetic closing lines, decorative atmosphere, or repeated words such as quiet, night, afterglow, warmth, or being beside the user. "
        "Answer the current user request directly, and do not continue a previous story unless the user asks for continuation. "
        + "; ".join(notes)
        + "."
    )


def build_initiative_emotion_bias(
    state: EmotionState | Mapping[str, Any] | None,
    *,
    suppressed: bool = False,
    mode: str = "normal",
) -> tuple[float, list[str]]:
    """
    Small initiative score correction.  Suppression always wins.
    """
    if suppressed:
        return 0.0, ["suppressed:no_bias"]

    st = emotion_state_from_mapping(state if not isinstance(state, EmotionState) else state.to_dict())
    v = st.values
    reasons: list[str] = []
    bias = 0.0

    anticipation_bias = max(0.0, v["anticipation"] - 0.25) * 0.08
    trust_bias = max(0.0, v["trust"] - 0.25) * 0.05
    sadness_bias = max(0.0, v["sadness"] - 0.22) * -0.08

    if anticipation_bias:
        reasons.append(f"anticipation:+{anticipation_bias:.3f}")
    if trust_bias:
        reasons.append(f"trust:+{trust_bias:.3f}")
    if sadness_bias:
        reasons.append(f"sadness:{sadness_bias:.3f}")

    bias = anticipation_bias + trust_bias + sadness_bias
    if mode == "work":
        bias *= 0.5
        if reasons:
            reasons.append("work_mode:x0.5")

    # Keep the entire feature a bias, never a decision override.
    if bias > 0.08:
        bias = 0.08
    if bias < -0.08:
        bias = -0.08

    return bias, reasons


def emotion_state_preview(state: EmotionState | Mapping[str, Any] | None) -> dict[str, float]:
    st = emotion_state_from_mapping(state if not isinstance(state, EmotionState) else state.to_dict())
    return {e: round(st.values.get(e, 0.0), 3) for e in EMOTIONS}
