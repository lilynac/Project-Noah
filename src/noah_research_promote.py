# src/noah_research_promote.py
import os
import re
from collections import Counter
from datetime import datetime
from typing import List, Set, Tuple

from .paths import NOAH_RESEARCH_PATH, RESEARCH_PROMOTED_PATH

THRESHOLD = 3  # 3回以上で昇格


def safe_read(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def safe_append(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def _norm(s: str) -> str:
    # 軽い正規化（空白・全角スペース）
    s = s.replace("\u3000", " ").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def extract_topics(research_text: str) -> List[str]:
    """
    noah_research.txt から 'トピックX:' を抜く
    """
    topics: List[str] = []
    for line in research_text.splitlines():
        line = line.strip()
        # トピック1: / トピック2: を想定
        if line.startswith("トピック") and ":" in line:
            _, val = line.split(":", 1)
            t = _norm(val)
            if t:
                topics.append(t)
    return topics


def extract_promoted_topics(promoted_text: str) -> Set[str]:
    """
    research_promoted.txt の既存昇格トピックをセット化
    フォーマット: - 関心（定着）: <topic>（出現 n）
    """
    s: Set[str] = set()
    for line in promoted_text.splitlines():
        line = line.strip()
        if line.startswith("- 関心（定着）:"):
            body = line.replace("- 関心（定着）:", "").strip()
            # （出現 n）を落とす
            body = re.sub(r"（出現\s*\d+）\s*$", "", body).strip()
            if body:
                s.add(_norm(body))
    return s


def is_already_promoted(topic: str, promoted_set: Set[str]) -> bool:
    """
    厳密一致にしすぎると運用で困るので「包含」もOKにする
    """
    t = _norm(topic)
    for p in promoted_set:
        if t == p or t in p or p in t:
            return True
    return False


def promote_research_topics() -> bool:
    """
    - noah_research.txt を集計し、同一トピックが THRESHOLD 回以上なら昇格
    - 昇格済みは追加しない
    - 追加があったら True
    """
    research_text = safe_read(NOAH_RESEARCH_PATH)
    if not research_text:
        return False

    topics = extract_topics(research_text)
    if not topics:
        return False

    counts = Counter(topics)

    promoted_text = safe_read(RESEARCH_PROMOTED_PATH)
    promoted_set = extract_promoted_topics(promoted_text)

    newly: List[Tuple[str, int]] = []
    for topic, c in counts.items():
        if c >= THRESHOLD and not is_already_promoted(topic, promoted_set):
            newly.append((topic, c))

    if not newly:
        return False

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"[{ts}]"]
    for topic, c in sorted(newly, key=lambda x: (-x[1], x[0])):
        lines.append(f"- 関心（定着）: {topic}（出現 {c}）")

    safe_append(RESEARCH_PROMOTED_PATH, "\n".join(lines) + "\n\n")
    return True
