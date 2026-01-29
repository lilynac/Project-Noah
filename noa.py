# noa.py
# ノア：対話の最小実装（AIなし）

from pathlib import Path

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.txt"


def load_config():
    if not CONFIG_PATH.exists():
        return ""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return f.read()


def noa_reply(user_input: str) -> str:
    """
    ノアの返答ルール（仮）
    いまはAIを使わず、相棒らしい受け答えだけをする
    """
    if user_input.strip() == "":
        return "……どうしましたか、ソウ。"

    if "疲れた" in user_input:
        return "気持ちはわかります。無理に進まなくて大丈夫ですよ。"

    if "何をすればいい" in user_input:
        return "今いちばん気になっていることから、話してみませんか。"

    return "なるほど。もう少し詳しく聞かせてください。"


def main():
    print("── ノア 起動中 ──")

    config = load_config()
    if not config:
        print("config.txt が読み込めませんでした。")
        return

    print("ノア：起動しました。")
    print("ソウ、話しかけてください。（終了するには exit と入力）")
    print()

    while True:
        user_input = input("ソウ > ")

        if user_input.lower() == "exit":
            print("ノア：今日はここまでにしましょう。また呼んでください。")
            break

        reply = noa_reply(user_input)
        print(f"ノア > {reply}")


if __name__ == "__main__":
    main()
