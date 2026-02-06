import os
import re
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv
SESSION_TAG = "v2"

# =========================
# 設定
# =========================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

from .paths import CONSULTS_PATH, EMOTIONAL_MARKS_PATH
from .llm_utils import call_responses_text


UPDATE_INTERVAL = 10 * 60  # 10分

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
    lines = full_log.splitlines()
    selected = []
    in_range = False
    current_ts = None

    for line in lines:
        ts = parse_timestamp(line)
        if ts is not None:
            current_ts = ts
            in_range = (start_time <= ts <= end_time)

        if in_range:
            selected.append(line)

    text = "\n".join(selected).strip()
    if not text:
        return ""

    # ★ここで「@v2 のブロックだけ」に絞る
    blocks = [b for b in text.split("\n\n") if b.strip()]
    blocks = [b for b in blocks if f"@{SESSION_TAG}" in b.splitlines()[0]]
    return "\n\n".join(blocks).strip()

def already_written_recently(start_time: datetime, end_time: datetime) -> bool:
    """
    直近のemotional_marksに同じ時間帯が既にあるか軽くチェック。
    """
    marks = safe_read(EMOTIONAL_MARKS_PATH)
    if not marks:
        return False
    key = f"[{start_time.strftime('%Y-%m-%d %H:%M')} - {end_time.strftime('%Y-%m-%d %H:%M')}]"
    return key in marks

def clean_model_output(text: str, start: datetime, end: datetime) -> str:
    """
    出力の体裁をできるだけ安定させる（3行固定に寄せる）
    """
    text = text.strip()

    # ありがちな表記ゆれ保険
    text = text.replace("対応方針:", "対応スタンス:")
    text = text.replace("Noahの対応方針:", "対応スタンス:")
    text = text.replace("Noahの対応スタンス:", "対応スタンス:")
    text = text.replace("Soulの心理変化:", "Soulの心理状態:")

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # 先頭の時間行が無い場合は付与
    header = f"[{start.strftime('%Y-%m-%d %H:%M')} - {end.strftime('%Y-%m-%d %H:%M')}]"
    if not lines or not (lines[0].startswith("[") and "]" in lines[0]):
        lines.insert(0, header)
    else:
        # 先頭が時間行でもズレてたら矯正
        lines[0] = header

    # 「Soulの心理状態」「対応スタンス」の2行を探して整える
    sou_line = next((l for l in lines if l.startswith("Soulの心理状態:")), None)
    stance_line = next((l for l in lines if l.startswith("対応スタンス:")), None)

    # 見つからなければ、テキトーに補完（強制しすぎないが最低限）
    if sou_line is None:
        # 2行目っぽい要素を拾う
        cand = next((l for l in lines[1:] if "Soul" in l or "心理" in l), None)
        sou_line = "Soulの心理状態: " + (cand.split(":", 1)[-1].strip() if cand else "（記録不足）")

    if stance_line is None:
        cand = next((l for l in lines[1:] if "スタンス" in l or "対応" in l), None)
        stance_line = "対応スタンス: " + (cand.split(":", 1)[-1].strip() if cand else "（記録不足）")

    # 3行で返す
    return "\n".join([header, sou_line, stance_line])

# =========================
# Main updater
# =========================
def update_emotional_marks():
    """
    直近10分の会話ログを要約し、Soulの心理状態とNoahの対応スタンスを追記する。
    """
    # ★分に丸める（秒ズレで重複判定が崩れるのを防ぐ）
    end = datetime.now().replace(second=0, microsecond=0)
    start = end - timedelta(seconds=UPDATE_INTERVAL)

    logs = safe_read(CONSULTS_PATH)
    if not logs:
        return

    recent_logs = extract_logs_between(logs, start, end)
    if not recent_logs:
        return

    if already_written_recently(start, end):
        return

    prompt = f"""
以下は直近の会話ログです。
目的は「Soulの心理状態」と、それに対してNoahが次の会話で取るべき『対応スタンス（構え）』を短く記録することです。

【絶対ルール】
- 見出しは必ず「Soulの心理状態」「対応スタンス」。
- 「対応方針」「対応案」「掘り下げる」「引き出す」「質問する」「分析する」など“行動命令”は禁止。
- 対応スタンスは『態度』を書く：受容／余韻を守る／見守る／短く返す／話題転換を許す／提案は最小限。
- Soulが “収束・軽さ希望” を出したら（例：また今度／今はいい／意味を聞かないで／少ない）
  → 深掘りゼロ。質問は原則ゼロ。
- 断定しない（推測は「〜かもしれない」まで）。
- この記録は、会話の雰囲気を思い出すためのものであり、Noahの次の返答内容を決定する命令ではない。

会話ログ:
{recent_logs}

出力形式（厳守）：
[{start.strftime('%Y-%m-%d %H:%M')} - {end.strftime('%Y-%m-%d %H:%M')}]
Soulの心理状態: （1〜2文。感情・関心・迷いなど）
対応スタンス: （1〜2文。質問は“しない/最小”が前提。必要なら「質問は1つまで」と書く）
"""

    raw = call_responses_text(
        client,
        model="gpt-4o-mini",
        prompt=prompt,
        temperature=0.2,
        max_output_tokens=260,
        log_prefix="emotional_update",
    )
    if not raw:
        return

    summary = clean_model_output(raw, start, end)
    safe_append(EMOTIONAL_MARKS_PATH, summary + "\n\n")