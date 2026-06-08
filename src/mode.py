# src/mode.py
from __future__ import annotations

from typing import Literal

from src.dialogue.templating import detect_scene, _signals


Mode = Literal["normal", "quiet", "focus"]


def decide_mode(user_text: str) -> Mode:
    """最低ラインの自動切替。

    - quiet: 疲労/体調不良/強い不安/落ち込み
    - focus: 作業/実装/締切 など
    - normal: それ以外
    """
    scene = detect_scene(user_text)
    sig = set(_signals(user_text))

    healthish = bool(sig & {"sick", "anxiety", "fear", "self_blame", "lonely"}) or scene in {
        "tired",
        "sad",
        "anxious",
    }
    focusish = scene == "work_focus"

    if focusish and not healthish:
        return "focus"
    if healthish:
        return "quiet"
    return "normal"
