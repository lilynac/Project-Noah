from __future__ import annotations
from dataclasses import dataclass

from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication


@dataclass
class TrayDeps:
    open_chat: callable  # () -> None
    set_mode: callable             # (mode: str) -> None
    quit_app: callable             # () -> None
    icon: QIcon                    # ★ QIconを直接渡す（統一）


class TrayController:
    def __init__(self, deps):
        self.deps = deps

        # ★参照保持（GC対策）
        self.tray = QSystemTrayIcon(self.deps.icon)
        self.menu = QMenu()

        # Talk...
        self.act_talk = QAction("会話を開く", self.menu)
        self.act_talk.triggered.connect(self.on_talk)
        self.menu.addAction(self.act_talk)

        # Mode submenu
        self.mode_menu = self.menu.addMenu("Mode")

        self.act_normal = QAction("Normal", self.mode_menu)
        self.act_normal.triggered.connect(lambda: self._safe_set_mode("Normal"))
        self.mode_menu.addAction(self.act_normal)

        self.act_work = QAction("Work", self.mode_menu)
        self.act_work.triggered.connect(lambda: self._safe_set_mode("Work"))
        self.mode_menu.addAction(self.act_work)

        self.menu.addSeparator()

        # Quit
        self.act_quit = QAction("Quit", self.menu)
        self.act_quit.triggered.connect(self._safe_quit)
        self.menu.addAction(self.act_quit)

        self.tray.setContextMenu(self.menu)

    def show(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("[WARN] System tray is not available on this environment.")
            return
        self.tray.show()

    # --- safe wrappers ---

    def _safe_quit(self):
        try:
            if hasattr(self.deps, "quit_app") and self.deps.quit_app:
                self.deps.quit_app()
                return
        except Exception as e:
            print(f"[WARN] quit_app failed: {e}")

        # フォールバック：最悪でもアプリ終了要求だけ出す（未定義 app 参照はしない）
        app = QApplication.instance()
        if app:
            app.quit()

    def _safe_set_mode(self, mode: str):
        try:
            if hasattr(self.deps, "set_mode") and self.deps.set_mode:
                self.deps.set_mode(mode)
        except Exception as e:
            print(f"[WARN] set_mode failed: {e}")

    def on_talk(self):
        self.deps.open_chat()
