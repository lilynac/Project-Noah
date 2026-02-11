from __future__ import annotations
from dataclasses import dataclass

from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QInputDialog, QMessageBox


@dataclass
class TrayDeps:
    send_user_utterance: callable  # (text: str) -> None
    set_mode: callable             # (mode: str) -> None
    quit_app: callable             # () -> None
    icon: QIcon                    # ★ QIconを直接渡す（統一）


class TrayController:
    def __init__(self, deps: TrayDeps):
        self.deps = deps

        # ★保持（GC対策）
        self.tray = QSystemTrayIcon(self.deps.icon)
        self.menu = QMenu()

        # Talk...
        self.act_talk = QAction("Talk…", self.menu)
        self.act_talk.triggered.connect(self.on_talk)
        self.menu.addAction(self.act_talk)

        # Mode submenu
        self.mode_menu = self.menu.addMenu("Mode")

        self.act_normal = QAction("Normal", self.mode_menu)
        self.act_normal.triggered.connect(lambda: self.deps.set_mode("Normal"))
        self.mode_menu.addAction(self.act_normal)

        self.act_work = QAction("Work", self.mode_menu)
        self.act_work.triggered.connect(lambda: self.deps.set_mode("Work"))
        self.mode_menu.addAction(self.act_work)

        self.menu.addSeparator()

        # Quit
        self.act_quit = QAction("Quit", self.menu)
        self.act_quit.triggered.connect(self.deps.quit_app)
        self.menu.addAction(self.act_quit)

        self.tray.setContextMenu(self.menu)

    def show(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("[WARN] System tray is not available on this environment.")
            return
        self.tray.show()

        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.warning(None, "Noah", "この環境ではSystem Trayが利用できません。")
            app.quit()
            return

    def on_talk(self):
        text, ok = QInputDialog.getText(
            None,
            "Noah",
            "聞かせて。いまの気持ちを",
        )
        if ok:
            text = (text or "").strip()
            if text:
                self.deps.send_user_utterance(text)
