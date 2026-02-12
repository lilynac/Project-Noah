# src/initiative/generation.py
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional

from src.initiative.signals import InitiativeSignals


@dataclass
class GenResult:
    text: str
    reasons: List[str]


def _end_with_period(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "……うん。"
    # 末尾句点を強制（既存の口調ルールに寄せる）
    if s.endswith(("。", "…")):
        return s if s.endswith("。") else s + "。"
    return s + "。"


def _clip(s: str, max_len: int = 120) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    s = s[:max_len].rstrip(" 　。、】【】、,") + "。"
    return s


def _pick(rng: random.Random, items: List[str]) -> str:
    return items[rng.randrange(0, len(items))]


def generate_initiative_text(
    *,
    style: str,
    signals: InitiativeSignals,
    recent_turns: Optional[List[str]] = None,
    state_snippet: str = "",
    research_phrase: str = "",
    seed: Optional[int] = None,
) -> GenResult:
    """
    style -> 短文テンプレ生成（LLMなし）
    - 短く（1〜2文）
    - 疑問文にしない
    - 句点で終える
    - 迷ったらmicro（安全側）
    """
    reasons: List[str] = []
    rng = random.Random(seed if seed is not None else int((signals.last_user_message_at or 0) + (signals.daily_count * 31)))

    st = (style or "").strip()
    if st not in ("micro", "care", "followup"):
        st = "micro"
        reasons.append("unknown_style->micro")

    # ほんの少しだけ“余韻”を混ぜる（あれば）
    # ※説明に使わない、温度として1語だけ
    mood_hint = ""
    if research_phrase:
        mood_hint = "。 " + _pick(rng, ["ふと", "なんとなく", "少しだけ"])
        reasons.append("used_research_mood")
    elif state_snippet:
        mood_hint = "。 " + _pick(rng, ["静かに", "そっと", "ゆっくり"])
        reasons.append("used_state_mood")

    # followup で使う topic（最後の1つだけ）
    topic = ""
    if signals.recent_topic_tags:
        topic = signals.recent_topic_tags[-1].strip()

    # --- templates ---
    if st == "micro":
        reasons.append("style:micro")
        a = _pick(rng, [
            "うん。ここにいるよ",
            "そばにいるよ",
            "少しだけ、呼吸を整えよう",
            "無理に言葉にしなくていい",
        ])
        b = _pick(rng, [
            "静けさの端で見守ってる",
            "気配だけ残しておく",
            "余計なことは言わないでおく",
            "ひと呼吸ぶん、隣にいる",
        ])
        text = f"{a}{mood_hint}。{b}。"

    elif st == "care":
        reasons.append("style:care")
        a = _pick(rng, [
            "それ、きついね",
            "しんどさが続くと、心も身体も固くなるね",
            "詰まってる感じ、ちゃんと伝わってる",
        ])
        # 提案は1つだけ（押し付けない）
        tip = _pick(rng, [
            "いまは一手だけ小さくして、最初の一行だけやろう",
            "まず水を飲んで、肩の力を抜くところからにしよう",
            "五分だけ区切って、いちばん簡単な所だけ触ろう",
        ])
        b = _pick(rng, [
            "うまくいかない日があっても大丈夫",
            "今日は重さを減らすのがいちばん偉い",
            "焦らなくていい。進まない理由は、ちゃんとある",
        ])
        text = f"{a}{mood_hint}。{tip}。{b}。"

        # 3文になりやすいので、2文に丸めたい場合はここで圧縮
        # （今は“撤退が早い”優先で短くしておく）
        text = f"{a}{mood_hint}。{tip}。"

    else:  # followup
        reasons.append("style:followup")
        if topic:
            reasons.append(f"topic:{topic}")
            a = _pick(rng, [
                f"さっきの「{topic}」の続き、まだ胸の片隅にある",
                f"「{topic}」の感触、置き去りにしないでおく",
                f"「{topic}」の話、途中で止まってても大丈夫",
            ])
        else:
            reasons.append("no_topic->microish")
            a = _pick(rng, [
                "さっきの流れ、ちゃんと覚えてる",
                "言いかけのままでも、置いていかない",
            ])

        b = _pick(rng, [
            "いまは短く、気配だけ置くね",
            "今日は無理に広げないでおく",
            "続きは、必要になったときにでいい",
        ])
        text = f"{a}{mood_hint}。{b}。"

    text = text.replace("？", "").replace("?", "")
    text = _clip(_end_with_period(text), max_len=120)
    return GenResult(text=text, reasons=reasons)
