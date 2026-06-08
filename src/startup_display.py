from __future__ import annotations

import os
import sys
import time
from datetime import datetime


TRUTHY = {"1", "true", "yes", "on"}


def _enabled() -> bool:
    """起動演出を表示するか。NOAH_BOOT_STYLE=plain で抑制できる。"""
    return os.getenv("NOAH_BOOT_STYLE", "poetic").strip().lower() != "plain"


def debug_enabled() -> bool:
    """開発用の詳細printを出すか。"""
    return os.getenv("NOAH_BOOT_VERBOSE", "0").strip().lower() in TRUTHY


def debug(message: str) -> None:
    if debug_enabled():
        print(message, flush=True)


def line(message: str = "", delay: float = 0.0) -> None:
    if not _enabled():
        return
    print(message, flush=True)
    if delay > 0:
        time.sleep(delay)


def wake_header() -> None:
    if not _enabled():
        return

    now = datetime.now().strftime("%H:%M")
    line("")
    line("╭────────────────────────────╮")
    line("│          Noah              │")
    line("╰────────────────────────────╯")
    line(f"{now}、Noahが目を覚まします。", 0.35)


def wake_step(message: str, delay: float = 0.25) -> None:
    line(f"  {message}", delay)


def wake_ready() -> None:
    if not _enabled():
        return
    line("", 0.05)
    line("Noahは起きています。")
    line("話しかけられる距離にいます。")
    line("")


def sleep_message() -> None:
    if not _enabled():
        return
    line("")
    line("Noahは静かに目を閉じます。")
    line("また呼ばれるまで、記憶のそばで待っています。")
