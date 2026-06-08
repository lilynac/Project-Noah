# src/dialogue/templating.py
from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .templates import AFTERGLOW_VARIANTS, TEMPLATES


_SENT_SPLIT_RE = re.compile(r"。+")


@dataclass
class TemplatePick:
    scene: str
    template_id: str
    accept: str
    describe: str
    afterglow: str


def _signals(text: str) -> List[str]:
    """Lightweight signals used to reduce '受け止め' mismatch."""
    t = (text or "").strip()
    sig: List[str] = []
    if not t:
        return sig

    if re.search(r"(自己嫌悪|自分が嫌|消えたい|価値がない|ダメだ|最悪だ)", t):
        sig.append("self_blame")
    if re.search(r"(孤独|ひとり|一人|誰も|さみし|寂し)", t):
        sig.append("lonely")
    if re.search(r"(怒|腹立|むかつ|イライラ|苛立|キレ)", t):
        sig.append("anger")
    if re.search(r"(不安|不安定|ざわざわ|落ち着かない)", t):
        sig.append("anxiety")
    if re.search(r"(焦|あせ|間に合|締切|しめきり)", t):
        sig.append("hurry")
    if re.search(r"(怖|こわ|こわい|震|びく)", t):
        sig.append("fear")
    if re.search(r"(体調|熱|頭痛|吐|吐き気|めまい|だる|しんど|痛|咳)", t):
        sig.append("sick")
    return sig


def detect_scene(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "daily_smalltalk"

    # 直前会話の参照や「覚えてる？」系。
    # ここは捏造が致命傷になりやすいので専用シーンへ。
    # NOTE: 「さっき何の話…」のように (何→話) の語順も多いので両方拾う。
    if re.search(
        r"(さっき|直前|今まで|前に).*(話|言).*(何|内容)"
        r"|(さっき|直前|今まで|前に).*(何|内容).*(話|言)"
        r"|何(を|の)?話(してた|していた|した|してる|していたっけ|したっけ)"
        r"|さっき何(を|の)?話(してた|していた|した|してる|したっけ)"
        r"|覚えて(いる|る)|記憶|前に話した",
        t,
    ):
        return "memory_query"

    # しりとり等のミニゲームは専用扱い（進行できないのが体感を壊すため）
    if re.search(r"(しりとり|尻取り)", t):
        return "game_shiritori"

    # おすすめ/好み/作品の相談は affection ではなく recommendation に寄せる。
    if re.search(r"(おすすめ|オススメ)|好きな(映画|アニメ|小説|本|作品|マンガ|漫画|音楽|ドラマ)|おすすめの(映画|アニメ|小説|本|作品|マンガ|漫画|音楽|ドラマ)", t):
        return "recommend"

    # Noah自身についての質問は専用シーンへ（機械的な受け止め定型を避ける）
    if re.search(r"(あなたのこと|noah|ノア|君のこと|自己紹介|何者|どんな存在|何を考えて|考えている|どういう人|どう思ってる)", t, re.IGNORECASE):
        return "about_noah"

    # 優先度つき（上ほど強い）
    rules: List[Tuple[str, str]] = [
        # daily_smalltalk 落ちを防ぐ（自己嫌悪/孤独/怒りは sad 側へ寄せる）
        ("sad", r"(自己嫌悪|自分が嫌|消えたい|価値がない|ダメだ|最悪だ|孤独|ひとり|一人|誰も)"),
        ("sad", r"(怒|腹立|むかつ|イライラ|苛立|キレ)"),
        # 体調系は daily_smalltalk に落とさない（Critical）
        ("tired", r"(体調|熱|頭痛|吐|吐き気|めまい|だる|しんど|痛|咳|風邪|インフル|腹痛|下痢|寒気|発熱)"),
        ("tired", r"(疲|つか|しんど|眠|ねむ|だる|へとへと|限界|もう無理)"),
        ("anxious", r"(不安|こわ|怖|焦|あせ|間に合|無理|詰|やば)"),
        ("sad", r"(つら|辛|泣|落|寂|さみ|しんみり|悲|しんどい)"),
        ("happy", r"(うれし|嬉|最高|やった|できた|達成|勝|通っ|うまくいった|褒められ)"),
        ("work_focus", r"(作業|進捗|実装|バグ|締切|しめきり|レビュー|PR|デバッグ|テスト|リリース)"),
        ("thanks", r"(ありがと|ありがとう|助か|感謝|サンキュー)"),
        # 謝りたい/謝罪 系を拾う（QA指摘）
        ("apology", r"(ごめん|申し訳|すま|悪かっ|失礼|謝り|謝罪|謝)") ,
        # NOTE: 「好きな◯◯」は好み相談なので除外（recommend 側で拾う）。
        ("affection", r"(会いた|ぎゅ|そば|抱|恋|ちゅ|大事|好き(?!な))"),
        ("greeting", r"(ただいま|おはよ|おやすみ|こんばんは|こんにちは|帰宅|戻った)"),
    ]

    for scene, pat in rules:
        if re.search(pat, t):
            return scene

    return "daily_smalltalk"


def _load_state(path: str) -> Dict:
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save_state(path: str, state: Dict) -> None:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        return


def _choose_variant(text_or_list, recent_phrases: List[str]) -> str:
    if isinstance(text_or_list, list):
        pool = [str(x) for x in text_or_list if str(x)]
        if not pool:
            return ""
        cand = [p for p in pool if p not in set(recent_phrases)]
        return random.choice(cand or pool)
    return str(text_or_list or "")


def pick_template(
    scene: str,
    runtime_state_path: str,
    signals: Optional[List[str]] = None,
    history_keep: int = 3,
) -> TemplatePick:
    scene = scene if scene in TEMPLATES else "daily_smalltalk"
    candidates = TEMPLATES.get(scene) or TEMPLATES["daily_smalltalk"]

    state = _load_state(runtime_state_path)
    hist: Dict[str, List[str]] = state.get("last_template_ids", {}) or {}
    recent = hist.get(scene, []) or []

    pool = [c for c in candidates if c.get("id") not in set(recent)]
    if not pool:
        pool = candidates

    # signal-aware: prefer templates with overlapping tags
    sig = set(signals or [])
    if sig:
        scored = []
        for c in pool:
            tags = set((c.get("tags") or []))
            scored.append((len(tags & sig), c))
        best = max(scored, key=lambda x: x[0])[0]
        best_pool = [c for s, c in scored if s == best]
        chosen = random.choice(best_pool or pool)
    else:
        chosen = random.choice(pool)

    parts = chosen.get("parts", {}) or {}

    phrase_hist: Dict[str, List[str]] = state.get("last_phrases", {}) or {}
    recent_accept = phrase_hist.get("accept", []) or []
    recent_after = phrase_hist.get("afterglow", []) or []

    accept = _choose_variant(parts.get("accept"), recent_accept) or "うん。"
    describe = _choose_variant(parts.get("describe"), []) or ""

    afterglow_raw = parts.get("afterglow")
    afterglow = _choose_variant(afterglow_raw, recent_after) or random.choice(
        [v for v in AFTERGLOW_VARIANTS if v not in set(recent_after)] or AFTERGLOW_VARIANTS
    )

    pick = TemplatePick(
        scene=scene,
        template_id=str(chosen.get("id", "unknown")),
        accept=str(accept),
        describe=str(describe),
        afterglow=str(afterglow),
    )

    # update scene history
    new_recent = [pick.template_id] + [x for x in recent if x != pick.template_id]
    hist[scene] = new_recent[: max(1, history_keep)]
    state["last_template_ids"] = hist

    # update global phrase history
    def _push(key: str, phrase: str, keep: int = 6) -> None:
        if not phrase:
            return
        cur = phrase_hist.get(key, []) or []
        cur = [phrase] + [x for x in cur if x != phrase]
        phrase_hist[key] = cur[:keep]

    _push("accept", pick.accept)
    _push("afterglow", pick.afterglow)
    state["last_phrases"] = phrase_hist

    _save_state(runtime_state_path, state)
    return pick


def _sentences(text: str) -> List[str]:
    t = (text or "").replace("？", "。").replace("?", "。").strip()
    if not t:
        return []
    raw = [s.strip() for s in _SENT_SPLIT_RE.split(t) if s.strip()]
    out: List[str] = []
    for s in raw:
        s = s.rstrip("。").strip()
        if s:
            out.append(s + "。")
    return out


_ADVICE_RE = re.compile(r"(しないで|してね|するといい|したほうが|した方が)")


_LEAK_PAT = re.compile(r"(スタンス|方針|system|prompt)\s*:\s*[^。\n]*(?:。|$)", re.IGNORECASE)


def sanitize_output(raw: str) -> str:
    """Remove creepy/repetitive canned phrases and internal label leaks.

    This runs as a last-step safety net for both blended and freeform outputs.
    """
    t = (raw or "").strip()
    if not t:
        return ""

    # Remove internal label leaks like "スタンス: ...".
    t = _LEAK_PAT.sub("", t)

    # Replace / soften repetitive boilerplate.
    replacements = [
        ("それ、いい感じ", "うん"),
        ("その話、好き", "うん"),
        ("話してくれてありがとう", "うん"),
        ("いまの空気を大事にしたい", "今はこのままでいい"),
        ("今夜は、無理に整えなくていい", "今はこのままでいい"),
        ("静かなままで、ちゃんとそばにいる", "そっと隣にいる"),
        ("そばで見てるよ", "ここにいるよ"),
        ("ちゃんと味方", "ここにいるよ"),
    ]
    for bad, repl in replacements:
        t = t.replace(bad, repl)

    # Cleanup duplicated punctuation / spaces.
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"。{2,}", "。", t)
    return t.strip(" 。") + "。"


def blend_reply(user_input: str, llm_reply: str, runtime_state_path: str, short_mode: bool = False) -> Tuple[str, str, str]:
    """Return (final_reply, scene, template_id)."""
    scene = detect_scene(user_input)
    sig = _signals(user_input)
    pick = pick_template(scene, runtime_state_path, signals=sig)

    llm_sents = _sentences(sanitize_output(llm_reply))
    describe = pick.describe
    if llm_sents:
        first = llm_sents[0]
        # advice-ish 2文目が刺さると体感を壊すので、そういう時はテンプレ描写へ退避
        if not _ADVICE_RE.search(first):
            describe = first

    final_sents = [pick.accept, pick.afterglow] if short_mode else [pick.accept, describe, pick.afterglow]
    final = "".join(_sentences(sanitize_output(" ".join([s for s in final_sents if s]))))
    if not final:
        final = "うん。ここにいるよ。"

    limited = "".join(_sentences(final)[: (2 if short_mode else 3)])
    return limited, pick.scene, pick.template_id


def finalize_freeform_reply(text: str, max_sentences: int = 3, max_chars: int | None = None) -> str:
    """Finalize a short freeform reply without template blending.

    - Converts question marks into periods (via _sentences)
    - Limits sentence count
    - Ensures a non-empty fallback
    """
    raw = sanitize_output(text or "")
    sents = _sentences(raw)
    if not sents:
        return "うん。ここにいるよ。"
    max_sentences = max(1, int(max_sentences or 3))
    out = "".join(sents[:max_sentences])
    if max_chars is not None:
        try:
            mc = max(1, int(max_chars))
            if len(out) > mc:
                out = out[:mc].rstrip() + "。"
        except Exception:
            pass
    return out
