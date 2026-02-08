# src/noah_research_promote.py
import os
import re
from collections import Counter
from datetime import datetime
from typing import Dict, List, Set, Tuple

from .paths import NOAH_RESEARCH_PATH, RESEARCH_PROMOTED_PATH

THRESHOLD = 5            # 5回以上で昇格
MIN_DISTINCT_DAYS = 2    # 「別日」条件（登場した日付の種類）


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
    noah_research.txt から 'トピックX:' を抜く（従来互換）
    """
    topics: List[str] = []
    for line in research_text.splitlines():
        line = line.strip()
        if line.startswith("トピック") and ":" in line:
            _, val = line.split(":", 1)
            t = _norm(val)
            if t:
                topics.append(t)
    return topics


def extract_topics_with_days(research_text: str) -> List[Tuple[str, str]]:
    """
    noah_research.txt から (topic, day) を抜く
    day は 'YYYY-MM-DD'
    ブロック先頭の [YYYY-MM-DD HH:MM] を利用する
    """
    pairs: List[Tuple[str, str]] = []
    current_day: str | None = None

    # 例: [2026-02-04 20:06]
    ts_pat = re.compile(r"^\[(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}\]")

    for raw in research_text.splitlines():
        line = raw.strip()

        m = ts_pat.match(line)
        if m:
            current_day = m.group(1)
            continue

        if line.startswith("トピック") and ":" in line and current_day:
            _, val = line.split(":", 1)
            t = _norm(val)
            if t:
                pairs.append((t, current_day))

    return pairs


def extract_promoted_topics(promoted_text: str) -> Set[str]:
    """
    research_promoted.txt の既存昇格トピックをセット化
    既存フォーマット例:
      - 関心（定着）: <topic>（出現 n）
    新フォーマット例:
      - 関心（定着）: <topic>（出現 n / 日数 d）
    """
    s: Set[str] = set()
    for line in promoted_text.splitlines():
        line = line.strip()
        if line.startswith("- 関心（定着）:"):
            body = line.replace("- 関心（定着）:", "").strip()

            # 末尾の（出現 n）や（出現 n / 日数 d）を落とす
            body = re.sub(r"（出現\s*\d+(?:\s*/\s*日数\s*\d+)?）\s*$", "", body).strip()

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
    - noah_research.txt を集計し、同一トピックが THRESHOLD 回以上
      かつ、登場日が MIN_DISTINCT_DAYS 日以上なら昇格
    - 昇格済みは追加しない
    - 追加があったら True
    """
    research_text = safe_read(NOAH_RESEARCH_PATH)
    if not research_text:
        return False

    # (topic, day) を集計
    pairs = extract_topics_with_days(research_text)
    if not pairs:
        return False

    counts: Counter[str] = Counter()
    days_seen: Dict[str, Set[str]] = {}

    for topic, day in pairs:
        counts[topic] += 1
        days_seen.setdefault(topic, set()).add(day)

    promoted_text = safe_read(RESEARCH_PROMOTED_PATH)
    promoted_set = extract_promoted_topics(promoted_text)

    newly: List[Tuple[str, int, int]] = []
    for topic, c in counts.items():
        d = len(days_seen.get(topic, set()))
        if c >= THRESHOLD and d >= MIN_DISTINCT_DAYS and not is_already_promoted(topic, promoted_set):
            newly.append((topic, c, d))

    if not newly:
        return False

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"[{ts}]"]
    # 出現回数→日数→トピック名で安定ソート
    for topic, c, d in sorted(newly, key=lambda x: (-x[1], -x[2], x[0])):
        lines.append(f"- 関心（定着）: {topic}（出現 {c} / 日数 {d}）")

    safe_append(RESEARCH_PROMOTED_PATH, "\n".join(lines) + "\n\n")
    return True
