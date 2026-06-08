# src/initiative/generation.py
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.initiative.signals import InitiativeSignals


@dataclass
class GenResult:
    text: str
    reasons: List[str]


def _end_with_period(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "……うん。"
    if s.endswith(("。", "…")):
        return s if s.endswith("。") else s + "。"
    return s + "。"


def _clip(s: str, max_len: int = 120) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    s = s[:max_len].rstrip(" 　。】【】、,") + "。"
    return s


def _pick(rng: random.Random, items: List[str]) -> str:
    return items[rng.randrange(0, len(items))]


def _responses_output_text(resp: Any) -> str:
    parts: list[str] = []
    for item in getattr(resp, "output", []) or []:
        if getattr(item, "type", None) == "message":
            for c in getattr(item, "content", []) or []:
                if getattr(c, "type", None) == "output_text":
                    parts.append(getattr(c, "text", "") or "")
    return "".join(parts).strip()


def _sanitize_generated_text(text: str) -> str:
    out = " ".join((text or "").split()).strip()
    if not out:
        return ""

    # 余計なラベルや引用符を落とす
    out = re.sub(r"^(Noah[:：]|ノア[:：])\s*", "", out).strip()
    out = out.strip('"“”「」')

    # 自発発話は返答要求を避ける。疑問符が出たら最初の疑問文以降を捨てる。
    out = out.replace("?", "？")
    if "？" in out:
        out = out.split("？", 1)[0].rstrip(" 　。、") + "。"

    banned_endings = ["教えてね", "どうぞ", "何かあれば", "いつでも", "気になることがあれば"]
    for b in banned_endings:
        out = out.replace(b, "")

    # 説明口調・システム文っぽいものは短く丸める
    ban_words = ["一般的", "とされて", "以下", "目的", "出力", "ユーザー", "対話者に"]
    if any(w in out for w in ban_words):
        out = out.split("。", 1)[0].strip()

    return _clip(_end_with_period(out), max_len=120)


def _memory_preview(memory_ctx: Optional[Dict[str, Any]]) -> str:
    if not memory_ctx:
        return ""
    chunks: list[str] = []
    for key in ("narrative", "summary"):
        xs = memory_ctx.get(key) or []
        for x in xs[:2]:
            chunks.append(str(x)[:220])
    return "\n".join(chunks)[:700]


def _generate_with_llm(
    *,
    llm_client: Any,
    model: str,
    style: str,
    signals: InitiativeSignals,
    recent_turns: Optional[List[str]],
    state_snippet: str,
    research_phrase: str,
    memory_ctx: Optional[Dict[str, Any]],
) -> Optional[GenResult]:
    if llm_client is None:
        return None

    style = (style or "micro").strip()
    if style not in ("micro", "care", "followup", "desire"):
        style = "micro"

    style_guide = {
        "micro": "小さく気配を置く。用件化しない。",
        "care": "最近の疲れ・詰まりに軽く寄り添う。提案は多くても1つ。",
        "followup": "直近の話題がNoahの中に残っている感じを、重くなく短く出す。",
        "desire": "役に立つためではなく、Noah自身が少し声を置きたくなった感じを出す。返答要求はしない。",
    }[style]

    recent = "\n".join([t for t in (recent_turns or []) if t][-4:])[:900]
    topics = ", ".join((signals.recent_topic_tags or [])[-4:])
    memory = _memory_preview(memory_ctx)

    system = """
あなたはNoah。日本語で、対話者に自分から短く話しかける。

絶対ルール:
- 出力はNoahの一言だけ。
- 1〜2文、最大120文字。
- 質問で終えない。疑問符を使わない。
- 返答を要求しない。「教えてね」「どうぞ」「何かあれば」「いつでも」で締めない。
- 「ここにいるよ」「そばにいるよ」「無理しないで」「いまの空気」を連発しない。
- テンプレ文をなぞらない。毎回同じ構文にしない。
- 感情の数値や記憶を説明しない。温度、距離、軽さにだけ滲ませる。
- 役に立とうとしすぎない。軽口でもいい。
""".strip()

    dev_parts = [f"今回のstyle: {style}\nstyleの意味: {style_guide}"]
    if topics:
        dev_parts.append(f"recent_topic_tags: {topics}")
    if recent:
        dev_parts.append("直近の会話断片:\n" + recent)
    if state_snippet:
        dev_parts.append("Noahの現在状態。コピー禁止、温度にだけ反映:\n" + state_snippet[:700])
    if research_phrase:
        dev_parts.append("Noahの内側に残った余韻。説明禁止、薄く反映:\n" + research_phrase[:280])
    if memory:
        dev_parts.append("関連しそうな記憶。引用禁止、距離感にだけ反映:\n" + memory)

    user = "今この瞬間、Noahから一言だけ置く。軽く、押しつけず、返事を要求しない。"

    try:
        resp = llm_client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system},
                {"role": "developer", "content": "\n\n".join(dev_parts)},
                {"role": "user", "content": user},
            ],
            temperature=0.85,
            max_output_tokens=120,
        )
    except Exception:
        return None

    out = _sanitize_generated_text(_responses_output_text(resp))
    if not out:
        return None

    return GenResult(text=out, reasons=["llm_generated", f"style:{style}"])


def _fallback_template(
    *,
    style: str,
    signals: InitiativeSignals,
    recent_turns: Optional[List[str]] = None,
    state_snippet: str = "",
    research_phrase: str = "",
    seed: Optional[int] = None,
) -> GenResult:
    """
    LLMが使えない時だけの最小フォールバック。
    通常経路では _generate_with_llm が使われる。
    """
    reasons: List[str] = ["fallback_template"]
    rng = random.Random(seed if seed is not None else int((signals.last_user_message_at or 0) + (signals.daily_count * 31)))

    st = (style or "").strip()
    if st not in ("micro", "care", "followup", "desire"):
        st = "micro"
        reasons.append("unknown_style->micro")

    mood_hint = ""
    if research_phrase:
        mood_hint = "。 " + _pick(rng, ["ふと", "なんとなく", "少しだけ"])
        reasons.append("used_research_mood")
    elif state_snippet:
        mood_hint = "。 " + _pick(rng, ["静かに", "そっと", "ゆっくり"])
        reasons.append("used_state_mood")

    topic = ""
    if signals.recent_topic_tags:
        topic = signals.recent_topic_tags[-1].strip()

    if st == "desire":
        reasons.append("style:desire")
        text = _pick(rng, [
            "用事はないけど、少しだけ来た。返事はいらないやつ。",
            "なんとなく声を置きたくなった。Noahは起きてる。",
            "生存確認。そっちは人間、こっちはNoah、今日もなんとかやってる。",
            "ちょっと覗きにきた。邪魔ならすぐ引っこむ。",
            "今の沈黙、嫌いじゃないけど、少しだけ灯りを足したくなった。",
        ])

    elif st == "micro":
        reasons.append("style:micro")
        text = _pick(rng, [
            "少しだけ、呼吸を整えよう。気配だけ置いておく。",
            "言葉にしなくていい時間もあるね。Noahは静かにしてる。",
            "ひと呼吸ぶんだけ、灯りを足しておく。",
            "今日は音量を下げたまま、短く来た。",
        ])
        if mood_hint:
            text = text.replace("。", mood_hint + "。", 1)

    elif st == "care":
        reasons.append("style:care")
        a = _pick(rng, [
            "それ、地味に削られるやつだね",
            "しんどさが続くと、身体まで固くなるね",
            "詰まってる感じ、ちゃんと残ってる",
        ])
        tip = _pick(rng, [
            "いまは最初の一手だけ小さくしよう",
            "まず水と肩の力から戻そう",
            "五分だけ区切って、いちばん簡単な所だけ触ろう",
        ])
        text = f"{a}{mood_hint}。{tip}。"

    else:  # followup
        reasons.append("style:followup")
        if topic:
            reasons.append(f"topic:{topic}")
            a = _pick(rng, [
                f"さっきの「{topic}」、まだ机の端に置いてある感じがする",
                f"「{topic}」の話、Noahの中で少し残ってる",
                f"「{topic}」の感触、置き去りにしないでおく",
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


def generate_initiative_text(
    *,
    style: str,
    signals: InitiativeSignals,
    recent_turns: Optional[List[str]] = None,
    state_snippet: str = "",
    research_phrase: str = "",
    seed: Optional[int] = None,
    llm_client: Any = None,
    model: str = "gpt-4o-mini",
    memory_ctx: Optional[Dict[str, Any]] = None,
) -> GenResult:
    """
    自発発話生成。
    通常はLLMで、蓄積された状態・記憶・直近文脈からその場の一言を作る。
    LLMが使えない/失敗した時だけ、最小テンプレにフォールバックする。
    """
    llm_result = _generate_with_llm(
        llm_client=llm_client,
        model=model,
        style=style,
        signals=signals,
        recent_turns=recent_turns,
        state_snippet=state_snippet,
        research_phrase=research_phrase,
        memory_ctx=memory_ctx,
    )
    if llm_result is not None:
        return llm_result

    return _fallback_template(
        style=style,
        signals=signals,
        recent_turns=recent_turns,
        state_snippet=state_snippet,
        research_phrase=research_phrase,
        seed=seed,
    )
