# preferences_update.py
import os
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

from .paths import PREFERENCES_PATH, PREFERENCES_HISTORY_PATH, CONSULTS_PATH

# =========================
# Utilities
# =========================
def safe_read(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

def safe_write(path: str, text: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text.strip() + "\n")

def safe_append(path: str, text: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)

def tail_blocks(text: str, blocks: int = 6) -> str:
    if not text:
        return ""
    parts = text.split("\n\n")
    return "\n\n".join(parts[-blocks:])

def backup_preferences(old_text: str):
    """
    preferences の更新前内容を履歴として保存する。
    追記のみ・削除しない。
    """
    if not old_text.strip():
        return

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"[{ts}]\n"
        f"{old_text}\n\n"
    )
    safe_append(PREFERENCES_HISTORY_PATH, entry)

# =========================
# Main updater
# =========================
def update_preferences() -> bool:
    """
    - 直近の会話ログを見て
    - preferences.txt を「削る / 緩める」必要があるか判断
    - 更新前は必ず履歴に退避
    - 必要な場合のみ上書き保存
    """
    current_prefs = safe_read(PREFERENCES_PATH)
    logs = safe_read(CONSULTS_PATH)

    recent_logs = tail_blocks(logs, blocks=8)

    if not current_prefs or not recent_logs:
        return False

    prompt = f"""
あなたは Soul の思考負荷を下げるために
preferences.txt を最小化・最適化する編集者です。

【重要ルール】
- preferences は「判断を減らすための恒常ルール」
- 追加は原則禁止
- やるなら「削除」か「表現を弱める」だけ
- 変更は最小限（1〜2箇所まで）
- 変更不要なら "NO_UPDATE" とだけ返す

【トリガー例】
- Soul が「重い」「長い」「そこまで求めてない」等を示した
- ルールが厳しすぎて会話が不自然になった
- Noah がルールを守るために迷っている様子が出た

--- 現在の preferences.txt ---
{current_prefs}

--- 直近の会話ログ ---
{recent_logs}

--- 出力形式 ---
更新が必要な場合のみ、
【変更後の preferences.txt 全文】をそのまま出力。

不要な場合：
NO_UPDATE
"""

    text = call_responses_text(
        client,
        model="gpt-4o-mini",
        prompt=prompt,
        temperature=0.2,
        max_output_tokens=520,
        log_prefix="preferences_update",
    )
    if not text:
        return False

    if text == "NO_UPDATE":
        return False

    # =========================
    # Safety checks
    # =========================
    required_sections = [
        "[RESPONSE_LENGTH]",
        "[QUESTION_POLICY]",
        "[STOP_SIGNALS]"
    ]

    if not all(sec in text for sec in required_sections):
        return False

    # =========================
    # Apply update
    # =========================
    backup_preferences(current_prefs)
    safe_write(PREFERENCES_PATH, text)

    return True
from .llm_utils import call_responses_text

