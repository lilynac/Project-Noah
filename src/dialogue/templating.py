# src/dialogue/templating.py
from __future__ import annotations

import json
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .templates import TEMPLATES, AFTERGLOW_VARIANTS


_SENT_SPLIT_RE = re.compile(r"。+")


@dataclass
class TemplatePick:
    scene: str
    template_id: str
    accept: str
    describe: str
    afterglow: str


def detect_scene(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return "daily_smalltalk"

    # 優先度つき（上ほど強い）
    rules: List[Tuple[str, str]] = [
        ("tired", r"(疲|つか|しんど|眠|ねむ|だる|へとへと|限界|もう無理)"),
        ("anxious", r"(不安|こわ|怖|焦|あせ|間に合|無理|詰|やば)"),
        ("sad", r"(つら|辛|泣|落|寂|さみ|しんみり|悲|しんどい)"),
        ("happy", r"(うれし|嬉|最高|やった|できた|達成|勝|通っ|うまくいった)"),
        ("work_focus", r"(作業|進捗|実装|バグ|締切|しめきり|レビュー|PR|デバッグ|テスト|リリース)"),
        ("thanks", r"(ありがと|ありがとう|助か|感謝|サンキュー)"),
        ("apology", r"(ごめん|申し訳|すま|悪かっ|失礼)"),
        ("affection", r"(好き|会いた|ぎゅ|そば|抱|恋|ちゅ|大事)"),
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
        # 状態保存に失敗しても会話は止めない
        return


def pick_template(scene: str, runtime_state_path: str, history_keep: int = 3) -> TemplatePick:
    scene = scene if scene in TEMPLATES else "daily_smalltalk"
    candidates = TEMPLATES.get(scene) or TEMPLATES["daily_smalltalk"]

    state = _load_state(runtime_state_path)
    hist: Dict[str, List[str]] = state.get("last_template_ids", {}) or {}
    recent = hist.get(scene, []) or []

    pool = [c for c in candidates if c.get("id") not in set(recent)]
    if not pool:
        pool = candidates

    chosen = random.choice(pool)
    parts = chosen.get("parts", {}) or {}

    afterglow = parts.get("afterglow") or random.choice(AFTERGLOW_VARIANTS)
    pick = TemplatePick(
        scene=scene,
        template_id=str(chosen.get("id", "unknown")),
        accept=str(parts.get("accept", "うん。")),
        describe=str(parts.get("describe", "")),
        afterglow=str(afterglow),
    )

    # update history
    new_recent = [pick.template_id] + [x for x in recent if x != pick.template_id]
    new_recent = new_recent[: max(1, history_keep)]
    hist[scene] = new_recent
    state["last_template_ids"] = hist
    _save_state(runtime_state_path, state)

    return pick


def _sentences(text: str) -> List[str]:
    t = (text or "").replace("？", "。").replace("?", "。").strip()
    if not t:
        return []
    # 句点ベースで分割し、各文に句点を付け直す
    raw = [s.strip() for s in _SENT_SPLIT_RE.split(t) if s.strip()]
    out = []
    for s in raw:
        s = s.rstrip("。")
        if not s:
            continue
        out.append(s + "。")
    return out


def blend_reply(user_input: str, llm_reply: str, runtime_state_path: str, short_mode: bool = False) -> Tuple[str, str, str]:
    """Return (final_reply, scene, template_id)."""
    scene = detect_scene(user_input)
    pick = pick_template(scene, runtime_state_path)

    llm_sents = _sentences(llm_reply)
    # LLMの1文目を「描写」として使い、テンプレの骨格に温度を足す
    describe = pick.describe
    if llm_sents:
        describe = llm_sents[0]

    # short_mode は2文に縮める
    if short_mode:
        final_sents = [pick.accept, pick.afterglow]
    else:
        final_sents = [pick.accept, describe, pick.afterglow]

    # 念のため整形
    final = "".join(_sentences(" ".join(final_sents)))
    if not final:
        final = "うん。ここにいるよ。"
    # 最大3文に制限
    limited = "".join(_sentences(final)[: (2 if short_mode else 3)])
    return limited, pick.scene, pick.template_id
