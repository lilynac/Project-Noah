# src/qt_entry.py
from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path
from threading import Thread, Event

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QStyle, QSystemTrayIcon, QMessageBox

from datetime import datetime

from .tray import TrayController, TrayDeps
from .service import run_http_service
from .desktop_noah import create_overlay
from .paths import MODE_PATH



def _resolve_icon_path() -> Path:
    # 優先順位: data/assets/icon.png → src/assets/icon.png → その他
    project_root = Path(__file__).resolve().parents[1]
    here = Path(__file__).resolve().parent

    candidates = [
        project_root / "data" / "assets" / "icon.png",
        here / "assets" / "icon.png",
        project_root / "assets" / "icon.png",
        here / "icon.png",
        project_root / "icon.png",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def _post_chat(message: str, timeout: float = 30.0) -> str:
    url = "http://127.0.0.1:8765/chat"
    data = json.dumps({"message": message}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    obj = json.loads(raw)
    return str(obj.get("reply") or obj.get("text") or "")


def main():
    app = QApplication(sys.argv)
    stop_event = Event()
    print("[qt_entry] stop_event created")

    # ★これが重要：ウィンドウがなくてもアプリを終了させない
    app.setQuitOnLastWindowClosed(False)

    print("[qt_entry] starting…")

    # ---- IPC サービス起動（/chat, /health）----
    server_thread = Thread(target=run_http_service, args=("127.0.0.1", 8765, stop_event))
    server_thread.start()
    print("[qt_entry] http service thread started")

    # ---- Noah initiative loop ----
    from . import Noah as noah
    noah_thread = Thread(target=noah.initiative_loop, args=(stop_event,))  # ← daemonにしない
    noah_thread.start()
    print("[qt_entry] initiative loop thread started")

    # ---- Tray deps ----
    def send_user_utterance(text: str):
        try:
            reply = _post_chat(text, timeout=60.0)
            print(f"[Reply] {reply}")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"[ERROR] HTTP {e.code}: {body}")
        except Exception as e:
            print(f"[ERROR] {repr(e)}")


    def set_mode(mode: str):
        p = Path(MODE_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)

        # 既存内容を読む（なければ雛形）
        if p.exists():
            lines = p.read_text(encoding="utf-8").splitlines()
        else:
            lines = [
                "mode: off",
                "since: ",
                "set_by: tray",
                "note: ",
            ]

        def upsert(prefix: str, value: str):
            for i, line in enumerate(lines):
                if line.strip().startswith(prefix):
                    lines[i] = f"{prefix} {value}".rstrip()
                    return
            lines.append(f"{prefix} {value}".rstrip())

        upsert("mode:", mode.lower())  # Normal -> normal, Work -> work
        upsert("since:", datetime.now().strftime("%Y-%m-%d %H:%M"))
        upsert("set_by:", "tray")

        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[Mode] set to {mode} -> {MODE_PATH}")


    def quit_app():
        print("[Quit] quitting…")
        try:
            tray.tray.hide()  # macで残像が残るのを防ぐ
        except Exception:
            pass

        # stop_event はあとで作る（この時点ではまだ定義しない）
        try:
            stop_event.set()
        except Exception:
            pass

        app.quit()


    # availabilityログ
    print(f"[qt_entry] tray available = {QSystemTrayIcon.isSystemTrayAvailable()}")

    if not QSystemTrayIcon.isSystemTrayAvailable():
        msg = (
            "System Tray が利用できない環境のため Noah を起動できません。\n"
            "Tray対応のデスクトップ環境で実行してください。"
        )
        print("[WARN] System tray is not available. quitting.")

        # ヘッドレス環境（例: LinuxのCI）ではダイアログを出さずに終了する
        import os
        headless = False
        if sys.platform.startswith("linux"):
            if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
                headless = True

        if os.environ.get("NOAH_NO_DIALOG") == "1":
            headless = True

        if not headless:
            try:
                QMessageBox.critical(None, "Noah", msg)
            except Exception:
                pass

        app.quit()
        return

    overlay = create_overlay()  # ★参照保持（GC対策＆後で操作するため）

    # ---- Tray を作る（←これが抜けてた）----
    icon_path = _resolve_icon_path()
    icon = QIcon(str(icon_path)) if icon_path.exists() else app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)

    deps = TrayDeps(
        icon=icon,
        send_user_utterance=send_user_utterance,
        set_mode=set_mode,
        quit_app=quit_app,
    )
    tray = TrayController(deps)

    tray.show()
    print("[qt_entry] tray.show() called")

    # ★保険：Qtイベントループが落ちないよう、何もしないタイマーを回す
    keepalive = QTimer()
    keepalive.timeout.connect(lambda: None)
    keepalive.start(10_000)

    code = 0
    try:
        code = app.exec()
        print(f"[qt_entry] app.exec() returned {code}")
    finally:
        print("[qt_entry] stopping threads…")
        stop_event.set()

        # Noahを先に止める（UIに影響しにくい）
        try:
            noah_thread.join(timeout=5.0)
        except Exception as e:
            print(f"[WARN] noah_thread join failed: {e}")

        # サーバは“止め方”を次のStepで入れる（いったんjoinは短く）
        try:
            server_thread.join(timeout=2.0)
        except Exception as e:
            print(f"[WARN] server_thread join failed: {e}")

    sys.exit(code)



if __name__ == "__main__":
    main()
