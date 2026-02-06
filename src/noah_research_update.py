# src/noah_research_update.py
import os
import re
from datetime import datetime, timedelta

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

from .paths import CONSULTS_PATH, NOAH_RESEARCH_PATH

# どれくらいの頻度で “芽” を拾うか（まずは1時間に1回くらいが安全）
UPDATE_INTERVAL = 60 * 60  # 60分

# 1回の更新で拾う候補数（増やさない。軽さが命）
MAX_TOPICS = 2

SESSION_TAG = "v2"


# =========================
# Utilities
# =========================
def safe_read(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def safe_append(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def parse_timestamp(line: str):
    # line: "[2026-02-01 03:38]"
    if not (line.startswith("[") and "]" in line):
        return None
    ts_str = line[1:line.index("]")]
    try:
        return datetime.strptime(ts_str, "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def extract_logs_between(full_log: str, start_time: datetime, end_time: datetime) -> str:
    """
    consults.txt から時間帯で切り出し。
    さらに @v2 ブロックのみ対象。
    """
    lines = full_log.splitlines()
    selected = []
    in_range = False

    for line in lines:
        ts = parse_timestamp(line)
        if ts is not None:
            in_range = (start_time <= ts <= end_time)

        if in_range:
            selected.append(line)

    text = "\n".join(selected).strip()
    if not text:
        return ""

    blocks = [b for b in text.split("\n\n") if b.strip()]
    blocks = [b for b in blocks if f"@{SESSION_TAG}" in b.splitlines()[0]]
    return "\n\n".join(blocks).strip()


def already_written_recently(end: datetime) -> bool:
    """
    同じ時間帯の重複追記を避ける（ゆるいガード）
    """
    current = safe_read(NOAH_RESEARCH_PATH)
    if not current:
        return False
    key = f"[{end.strftime('%Y-%m-%d %H:%M')}]"
    return key in current[-4000:]  # 末尾だけ見れば十分


def _extract_candidate_phrases(text: str) -> list[str]:
    """
    超ざっくり候補抽出（LLM前の軽いフィルタ）
    - 「曲名」「作品名」「技法」「悩み」っぽい単語列を拾う
    """
    if not text:
        return []
    # 例：カタカナ、アルファベット、漢字の連なりをざっくり拾う
    tokens = re.findall(r"[ァ-ヶー]{3,}|[A-Za-z0-9\-\_]{3,}|[一-龠]{2,}", text)
    # ノイズ削減
    stop = {"Soul", "Noah", "initiative", "対応", "心理", "スタンス", "今日", "最近"}
    tokens = [t for t in tokens if t not in stop]
    # 頻出の上位だけ（無制限にしない）
    freq = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [t for t, c in ranked[:10]]


# =========================
# Main updater
# =========================
def update_noah_research() -> bool:
    """
    直近ログから、Soulの関心の“芽”を hidden に短文保存する。
    - 会話文は生成しない
    - 断定しない
    - 調べすぎない（短い）
    """
    end = datetime.now().replace(second=0, microsecond=0)
    start = end - timedelta(seconds=UPDATE_INTERVAL)

    logs = safe_read(CONSULTS_PATH)
    if not logs:
        return False

    recent_logs = extract_logs_between(logs, start, end)
    if not recent_logs:
        return False

    if already_written_recently(end):
        return False

    candidates = _extract_candidate_phrases(recent_logs)

    prompt = f"""
あなたは「Noah」の内部メモ（Soulには見せない）を書く編集者です。
目的は “次の会話で圧をかけずに寄り添うための背景理解” であり、会話文や提案文は書きません。

【絶対ルール】
- 断定しない（〜かもしれない、まで）
- 長文禁止：1トピックにつき最大140字
- 専門解説・レビュー口調禁止
- 「調べた」「検索した」などの自己報告は禁止
- 行動命令（〜すべき、〜すると良い）禁止
- トピックは最大 {MAX_TOPICS} 個

【入力（直近ログ）】
{recent_logs}

【参考（候補語）】
{", ".join(candidates) if candidates else "（なし）"}

【出力形式（厳守）】
[{end.strftime('%Y-%m-%d %H:%M')}]
トピック1: ...
関心: ...
メモ: ...

（トピックが2つある場合のみ続けて）
トピック2: ...
関心: ...
メモ: ...
"""

    try:
        resp = client.responses.create(
            model="gpt-4o-mini",
            input=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_output_tokens=520,
        )
    except Exception as e:
        print("noah_research_update: OpenAI error:", repr(e))
        return False

    parts = []
    for item in resp.output:
        if item.type == "message":
            for c in item.content:
                if c.type == "output_text":
                    parts.append(c.text)

    text = ("".join(parts) or "").strip()
    if not text:
        return False

    # 最低限のフォーマットガード（壊れたら捨てる）
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines or not (lines[0].startswith("[") and "]" in lines[0]):
        return False
    if not any(ln.startswith("トピック1:") for ln in lines):
        return False

    safe_append(NOAH_RESEARCH_PATH, text + "\n\n")
    return True
