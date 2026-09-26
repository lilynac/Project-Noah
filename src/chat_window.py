"""Persistent chat window; network work stays outside the GUI thread."""
from html import escape
from threading import Thread
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser, QLineEdit, QPushButton,
)


class ReplySignals(QObject):
    finished = pyqtSignal(str, bool)


class ChatWindow(QWidget):
    def __init__(self, send_message: Callable[[str], str], history=()):
        super().__init__()
        self._send_message = send_message
        self._pending = False
        self._sent_text = ""
        self._signals = ReplySignals(self)
        self._signals.finished.connect(self._finish_reply)
        self.setWindowTitle("Noah")
        self.resize(480, 580)
        self.setMinimumSize(340, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        title = QLabel("Noah")
        font = title.font()
        font.setPointSize(20)
        title.setFont(font)
        layout.addWidget(title)
        self.transcript = QTextBrowser()
        self.transcript.setOpenLinks(False)
        self.transcript.setAccessibleName("会話履歴")
        layout.addWidget(self.transcript)
        self.status = QLabel("ここにいるよ。何を話そうか。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Noah に話しかける…")
        self.message_input.setAccessibleName("メッセージ")
        self.message_input.returnPressed.connect(self.send)
        self.send_button = QPushButton("送信")
        self.send_button.clicked.connect(self.send)
        self.message_input.textChanged.connect(self._update_send_button)
        row.addWidget(self.message_input)
        row.addWidget(self.send_button)
        layout.addLayout(row)
        hint = QLabel("Enter で送信 · 閉じてもメニューバーにいるよ")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        for item in history:
            if item.get("role") in ("user", "assistant") and isinstance(item.get("content"), str):
                self._append("あなた" if item["role"] == "user" else "Noah", item["content"])
        self._update_send_button()

    def _append(self, speaker: str, text: str):
        self.transcript.append(
            f"<p><b>{escape(speaker)}</b><br>{escape(text).replace(chr(10), '<br>')}</p>"
        )
        bar = self.transcript.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _update_send_button(self):
        self.send_button.setEnabled(not self._pending and bool(self.message_input.text().strip()))

    def show_chat(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.message_input.setFocus()

    def closeEvent(self, event: QCloseEvent):
        event.ignore()
        self.hide()

    def send(self):
        text = self.message_input.text().strip()
        if self._pending or not text:
            return
        self._pending = True
        self._sent_text = text
        self.message_input.clear()
        self._update_send_button()
        self._append("あなた", text)
        self.status.setText("Noah が考えています…")

        def worker():
            try:
                reply = self._send_message(text)
                if not isinstance(reply, str) or not reply.strip():
                    raise ValueError("empty reply")
            except Exception:
                self._signals.finished.emit("", False)
            else:
                self._signals.finished.emit(reply, True)

        Thread(target=worker, daemon=True).start()

    def _finish_reply(self, reply: str, ok: bool):
        self._pending = False
        if ok:
            self._append("Noah", reply)
            self.status.setText("聞いているよ。")
        else:
            self.status.setText("返事を受け取れませんでした。接続を確認して、もう一度送信してください。")
            if not self.message_input.text():
                self.message_input.setText(self._sent_text)
        self._update_send_button()
        self.message_input.setFocus()
