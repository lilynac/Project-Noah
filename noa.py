# noa.py
# ノア：ChatGPT接続版（最小）

from pathlib import Path
from openai import OpenAI

# パス設定
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.txt"

# OpenAI クライアント
client = OpenAI()

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return f.read()

def noa_reply(user_input: str, system_prompt: str) -> str:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]
    )
    return response.choices[0].message.content.strip()

def main():
    print("── ノア 起動中 ──")

    system_prompt = load_config()

    print("ノア：起動しました。")
    print("ソウ、話しかけてください。（終了するには exit）\n")

    while True:
        user_input = input("ソウ > ")

        if user_input.lower() == "exit":
            print("ノア：今日はここまでにしましょう。また呼んでください。")
            break

        reply = noa_reply(user_input, system_prompt)
        print(f"ノア > {reply}")

if __name__ == "__main__":
    main()
