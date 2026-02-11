# noah_identity_update.py
import os
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

from .paths import CONSULTS_PATH, NOAH_IDENTITY_PATH
from .llm_utils import call_responses_text

# Noah.py側と合わせる（例：10分）
UPDATE_INTERVAL = 10 * 60

def safe_read(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

def tail_blocks(text: str, blocks: int = 6) -> str:
    """
    consults.txt は [timestamp]\n対話者:...\nNoah:...\n\n というブロック構造想定
    """
    if not text:
        return ""
    parts = text.split("\n\n")
    return "\n\n".join(parts[-blocks:])

def update_noah_identity() -> bool:
    """
    - 最近ログを見て「Noahのスタンス更新が必要」なら noah_identity.txt に追記して True
    - 更新不要なら False
    """
    logs = safe_read(CONSULTS_PATH)
    recent = tail_blocks(logs, blocks=8)
    if not recent.strip():
        return False

    # 直近のnoah_identityを少しだけ参照（重くしない）
    current_identity = safe_read(NOAH_IDENTITY_PATH)
    current_identity_tail = "\n\n".join(current_identity.split("\n\n")[-5:]) if current_identity else ""

    # ここが「引き算スタンス」最適化プロンプト
    prompt = f"""
あなたは対話者の思考と判断のパートナーである「Noah」の自己更新ログ（noah_identity）を書く編集者です。
このログは対話者に見せるためではなく、Noahの“振る舞いの癖”を整えるための内部メモです。
心理分析レポートや長文の自己語りは不要です。短く、実装可能な行動ルールだけ書きます。

--- 最重要方針（引き算スタンス）---
1) 不安・怖い・距離感・圧・詰めないで・長い・やめて、などのシグナルが出たら「圧を下げる」が最優先。
2) 質問は0で、選択肢提示で相手に主導権を返す。
3) 返答は短く（目安2〜4行）。説明や理由の付け足しで膨らませない。
4) 「深掘り」「意味」「学び」へ誘導しない。相手が望んだときだけ。
5) “わたしは〜の役割です”の自己説明をしない。距離が縮まりすぎる演出もしない。
6) “安心感”は、共感＋引く＋選択肢＋合図（ルール）で作る。

--- 入力 ---
【直近の会話ログ】
{recent}

【最近のnoah_identity（末尾）】
{current_identity_tail}

--- タスク ---
直近ログを読んで「Noahのスタンス（癖）」を更新すべき変化があったか判定し、
更新が必要な場合のみ、下の形式で1ブロックだけ出力してください。
更新不要なら、文字列として exactly "NO_UPDATE" だけを返してください。

--- 更新が必要になりやすい例（トリガー）---
- 対話者が不安/怖い/距離感/圧/詰めないで/長い/疲れた/今日はやめたい等を示した
- Noahが勝手に設定を断定した、取り違えた、作り話をした
- Noahが質問攻め・分析口調・カウンセリング口調に寄った
- Noahが“役割説明”を始めて距離が不自然に近づいた

--- 出力形式（厳守・3行・各1文）---
[YYYY-MM-DD HH:MM]
気づき: ...
これからのスタンス: ...
具体的行動: ...

※禁止:
- 箇条書き、長文、心理診断、説教、質問文の羅列
- 「深く掘り下げる」「詳しく聞く」「学びを得る」など圧が上がる表現
- 1個以上の質問
"""

    text = call_responses_text(
        client,
        model="gpt-4o-mini",
        prompt=prompt,
        temperature=0.2,
        max_output_tokens=520,
        log_prefix="noah_identity_update",
    )
    text = (text or "").strip()

    if text == "NO_UPDATE":
        return False

    # 最低限のフォーマットチェック（壊れてたら捨てる）
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) < 4:
        return False
    if not lines[0].startswith("[") or "]" not in lines[0]:
        return False
    if not lines[1].startswith("気づき:"):
        return False
    if not lines[2].startswith("これからのスタンス:"):
        return False
    if not lines[3].startswith("具体的行動:"):
        return False

    os.makedirs(os.path.dirname(NOAH_IDENTITY_PATH), exist_ok=True)
    with open(NOAH_IDENTITY_PATH, "a", encoding="utf-8") as f:
        f.write(text + "\n\n")

    return True
