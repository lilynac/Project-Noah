import argparse
import time
import importlib
from threading import Thread

from .bootstrap import bootstrap_once


def run_service_forever(noah):
    """入力なしで常駐するモード（menubar Start 用）"""
    # 起動演出 + 起動挨拶
    noah.startup_sequence()

    # HTTP IPC（localhost）
    from .service import run_http_service
    Thread(target=run_http_service, daemon=True).start()

    # バックグラウンド更新
    Thread(target=noah.emotional_update_loop, daemon=True).start()
    Thread(target=noah.noah_identity_update_loop, daemon=True).start()
    Thread(target=noah.preferences_update_loop, daemon=True).start()
    Thread(target=noah.noah_research_update_loop, daemon=True).start()
    Thread(target=noah.research_promote_loop, daemon=True).start()
    Thread(target=noah.initiative_loop, daemon=True).start()

    while True:
        time.sleep(1.0)


def run_once(noah, message: str):
    """1回だけ返信して終了（menubar Talk... 用）"""
    noah.startup_sequence()
    reply = noah.generate_reply(message)
    print(reply)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--service",
        action="store_true",
        help="run Noah as background service (no input loop)",
    )
    parser.add_argument(
        "--once",
        nargs=argparse.REMAINDER,
        help="reply once and exit (remaining args are the message)",
    )
    args = parser.parse_args()

    # どのモードでも最初にブートストラップ（既に初期化済みなら何もしない）
    bootstrap_once(verbose=True)

    # Noahは「モジュールとして」1回だけ掴む（グローバルの分裂を防ぐ）
    noah = importlib.import_module("src.Noah")

    if args.service:
        run_service_forever(noah)
        return

    if args.once is not None:
        text = " ".join(args.once).strip()
        if text:
            run_once(noah, text)
        return

    # 従来どおり：python -m src でCLI起動
    noah.main()


if __name__ == "__main__":
    main()
