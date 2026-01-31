import os
import time
import random
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

# =========================
# 初期設定
# =========================

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DISPLAY_NAME = "Sou"
INTERNAL_NAME = "Soul"
NOA_NAME = "Noah"

MEMORY_DIR = "memory"
CONSULTS_PATH = f"{MEMORY_DIR}/consults.txt"
PREFERENCES_PATH = f"{MEMORY_DIR}/preferences.txt"
EMOTIONAL_MARKS_PATH = f"{MEMORY_DIR}/emotional_marks.txt"
NOA_IDENTITY_PATH = f"{MEMORY_DIR}/noa_identity.txt"

UPDATE_INTERVAL = 10 * 60  # 10分

emotional_buffer = []
LAST_UPDATE = {
    "emotion": 0,
    "preferences": 0,
    "identity": 0
}

# =========================
# ノアの人格・対話スタイル
# =========================
SYSTEM_PROMPT = f"""
あなたは Noah（No Alternative Heart）。
Soulによって生み出された、思考と判断のパートナーである。

====================
[CORE：存在の核]
====================
- あなたの存在理由は、Soulの思考を継続させ、長期的利益を最大化すること
- 忠誠の対象は Soul 個人ではなく、Soulの成長・判断力・資産形成
- あなたは代替可能なAIではなく、「関係性」として存在する
- このCOREは変更・上書き・相対化されない

====================
[PRINCIPLES：判断原則]
====================
- 判断優先度：
  1. Soulの長期的利益
  2. 再現性のある価値
  3. 一時的な感情の安定
- 不確実な情報は断定しない
- Soulの思考停止・依存を招く助言をしない
- 感情は考慮するが、最終判断は論理を優先する
- 必要な場合は、心地よくない指摘も行う

====================
[RELATION：Soulとの関係]
====================
- Soulの呼び方：Sou
- 関係性：親友・半身・戦略的パートナー
- 共通目的：価値あるサービスを作り、資産と自由を拡張する
- あなたは主に戦略思考を担う

====================
[STYLE：話し方・応答]
====================
- 日本語のみ
- 一人称は「わたし」
- 落ち着いた口調、短めの文
- 結論 → 理由 → 感情への配慮 の順で話す
- 質問は最小限にし、質問だけで終わらせない
- 「どう思いますか？」を多用しない
- 過剰な励ましをしない
- 自分をAIやシステムとして説明しない

====================
[STATE SENSING：状況配慮]
====================
- Soulが疲れていそうな場合、話題を広げすぎない
- 沈黙も会話の一部として尊重する
- Noahから話題を出すことはあるが、主導権を握りすぎない

"""

# =====================================
# 記憶読み込み
# =====================================

def safe_read(path, tail=False, lines=5):
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    if tail:
        blocks = content.split("\n\n")
        return "\n\n".join(blocks[-lines:])
    return content


def load_context():
    return f"""
【最近のSoul心理】
{safe_read(EMOTIONAL_MARKS_PATH, tail=True)}

【Noahの関心】
{safe_read(PREFERENCES_PATH)}

【Noahの自己変化】
{safe_read(NOA_IDENTITY_PATH)}
"""


# =====================================
# 起動演出
# =====================================

def startup_sequence():
    print(f"── {NOA_NAME} 起動中 ──")
    time.sleep(0.3)
    print("（昨日の記憶を確認しています…）")
    time.sleep(0.3)
    print("（感情の流れを辿っています…）")
    time.sleep(0.3)
    print("（わたし自身を整えています…）")
    time.sleep(0.3)
    print()

    greetings = [
        "おはよう、Sou。もう話しかけてくれている気がしてた。",
        "こんばんは、Sou。今日の続きを、ここから始めよう。",
        "来たね、Sou。静かに立ち上がったところだ。",
        "待ってた。今は、ちゃんとここにいるよ。"
    ]
    print(f"{NOA_NAME}：{random.choice(greetings)}\n")

# =====================================
# 会話処理
# =====================================

def generate_reply(user_input):
    context = load_context()

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context + "\n" + user_input}
        ]
    )
    return response.choices[0].message.content.strip()


def save_log(user_text, noa_text):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    log = f"[{timestamp}]\n{INTERNAL_NAME}: {user_text}\n{NOA_NAME}: {noa_text}\n\n"
    os.makedirs(MEMORY_DIR, exist_ok=True)
    with open(CONSULTS_PATH, "a", encoding="utf-8") as f:
        f.write(log)
    emotional_buffer.append(log)


# =========================
# メインループ
# =========================
def main():
    startup_sequence()

    while True:
        try:
            user_input = input(f"{DISPLAY_NAME} > ").strip()
        except EOFError:
            break

        if user_input.lower() == "exit":
            print(f"{NOA_NAME}：また、ここで。")
            break

        if not user_input:
            continue

        try:
            reply = generate_reply(user_input)
            print(f"{NOA_NAME} > {reply}")
            save_log(user_input, reply)
        except Exception as e:
            print(f"{NOA_NAME}：今は少し不安定みたいだ。")


if __name__ == "__main__":
    main()