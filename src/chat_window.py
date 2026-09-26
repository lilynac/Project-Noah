"""Persistent chat window; network work stays outside the GUI thread."""
from threading import Thread
from typing import Callable

from .history_view import HistoryDialog
from .companion_view import CompanionDialog, message_html
from .character_view import CharacterView

from PyQt6.QtCore import QObject, pyqtSignal, Qt, QTimer, QEvent
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QLabel, QScrollArea, QFrame, QLineEdit, QPushButton, QSizePolicy,
)


class ConversationView(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAccessibleName("会話履歴")
        self._messages = []
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.timeout.connect(self._scroll_to_end)
        content = QWidget()
        content.setObjectName("conversation")
        self.rows = QVBoxLayout(content)
        self.rows.setContentsMargins(8, 20, 8, 20)
        self.rows.setSpacing(20)
        self.empty = QLabel("ここから、ふたりの会話を。\n今日のことでも、ふと思ったことでも。")
        self.empty.setObjectName("empty")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.rows.addWidget(self.empty)
        self.rows.addStretch()
        self.setWidget(content)

    def append_message(self, speaker, text):
        bar = self.verticalScrollBar()
        follow = bar.maximum() - bar.value() < 40
        self.empty.hide()
        self._messages.append(f"{speaker}\n{text}")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        bubble = QFrame()
        bubble.setObjectName("userBubble" if speaker == "あなた" else "noahBubble")
        body = QVBoxLayout(bubble)
        body.setContentsMargins(16, 12, 16, 14)
        body.setSpacing(7)
        name = QLabel(speaker)
        name.setObjectName("speaker")
        message = QLabel(message_html(text))
        message.setTextFormat(Qt.TextFormat.RichText)
        message.setOpenExternalLinks(True)
        message.setWordWrap(True)
        message.setMinimumWidth(0)
        message.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        message.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        body.addWidget(name)
        body.addWidget(message)
        if speaker == "あなた":
            row.addStretch(1)
            row.addWidget(bubble, 5)
        else:
            row.addWidget(bubble, 5)
            row.addStretch(1)
        self.rows.insertLayout(self.rows.count() - 1, row)
        if follow or speaker == "あなた":
            self._scroll_timer.start(0)

    def _scroll_to_end(self):
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def toPlainText(self):
        return "\n\n".join(self._messages)


CHAT_STYLE = """
QWidget { color: #253932; font-size: 14px; }
ChatWindow { background: #f4f6f3; }
QLabel { background: transparent; }
QLabel#brand { font-size: 25px; font-weight: 600; letter-spacing: 1px; }
QLabel#subtitle, QLabel#hint { color: #66786e; font-size: 12px; }
QLabel#presence { color: #356b52; background: #e4eee6; border-radius: 12px; padding: 6px 12px; font-size: 12px; }
QLabel#avatar { background: #244e3c; color: #ffffff; border-radius: 21px; font-size: 21px; font-weight: 600; }
QScrollArea, QWidget#conversation { background: #f4f6f3; border: none; }
QFrame#noahBubble { background: #ffffff; border: 1px solid #e0e7e0; border-radius: 16px; }
QFrame#userBubble { background: #e1ebe3; border: 1px solid #d5e1d8; border-radius: 16px; }
QLabel#speaker { color: #557365; font-size: 11px; font-weight: 600; }
QLabel#empty { color: #78877d; padding: 64px 12px; font-size: 14px; }
QLabel#status { color: #61786b; font-size: 12px; padding: 2px 4px; }
QFrame#composer { background: #ffffff; border: 1px solid #d5ded5; border-radius: 16px; }
QLineEdit { border: none; background: transparent; padding: 12px 6px; selection-background-color: #d1e5d8; }
QLineEdit:focus { background: #f3f8f4; border-radius: 8px; }
QPushButton { background: #285b43; color: #ffffff; border: none; border-radius: 11px; padding: 11px 18px; font-weight: 600; }
QPushButton#historyButton { background: #e4eee6; color: #356b52; padding: 7px 12px; font-size: 12px; }
QPushButton:hover { background: #367457; }
QPushButton:pressed { background: #1b422f; }
QPushButton:disabled { background: #e8eee9; color: #89998c; }
QScrollBar:vertical { width: 6px; background: transparent; margin: 4px 0; }
QScrollBar::handle:vertical { background: #c4d0c6; border-radius: 3px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


class ReplySignals(QObject):
    finished = pyqtSignal(str, bool)


class ChatWindow(QWidget):
    def __init__(self, send_message: Callable[[str], str], history=(), archive_loader=None, *, companion=None, portrait_path=None):
        super().__init__()
        self._send_message = send_message
        self._archive_loader = archive_loader
        self._history_dialog = None
        self._companion_dialog = None
        self._companion = companion
        self._seen_initiatives = set()
        if companion:
            try:
                self._seen_initiatives = {item['id'] for item in companion.snapshot()['outbox']}
            except (OSError, ValueError, KeyError, TypeError):
                pass
        self._companion_timer = QTimer(self)
        self._companion_timer.timeout.connect(self.receive_initiatives)
        if companion:
            self._companion_timer.start(1000)
        self._boot_lines = []
        self._booting = False
        self._boot_timer = QTimer(self)
        self._boot_timer.timeout.connect(self._advance_boot)
        self._pending = False
        self._sent_text = ""
        self._signals = ReplySignals(self)
        self._signals.finished.connect(self._finish_reply)
        self.setWindowTitle("Noah")
        self.resize(1020, 760)
        self.setStyleSheet(CHAT_STYLE)
        self.setMinimumSize(360, 560)

        self.body = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self.body.setContentsMargins(20, 20, 20, 20)
        self.body.setSpacing(24)
        self.character = CharacterView(portrait_path, self)
        self.body.addWidget(self.character, 4)
        self.motion_button = QPushButton('動き ON', self.character)
        self.motion_button.setCheckable(True)
        self.motion_button.setChecked(True)
        self.motion_button.setGeometry(16, 16, 84, 32)
        self.motion_button.setStyleSheet('QPushButton { background: rgba(20, 34, 28, 170); color: white; border-radius: 12px; padding: 4px 8px; font-size: 12px; }')
        self.motion_button.setAccessibleName('キャラクターの動き')
        self.motion_button.toggled.connect(self._set_character_motion)
        chat_panel = QWidget()
        self.body.addWidget(chat_panel, 6)
        layout = QVBoxLayout(chat_panel)
        self._chat_layout = layout
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        header = QHBoxLayout()
        header.setSpacing(12)
        branding = QVBoxLayout()
        branding.setSpacing(2)
        title = QLabel("Noah")
        title.setObjectName("brand")
        subtitle = QLabel("いつもの場所で、あなたのそばに。")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        branding.addWidget(title)
        branding.addWidget(subtitle)
        header.addLayout(branding, 1)
        self.presence = QLabel("待機中")
        self.presence.setObjectName("presence")
        header.addWidget(self.presence, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header)
        toolbar = QHBoxLayout()
        toolbar.addStretch()
        self.companion_button = QPushButton('Noah の日々')
        self.companion_button.setObjectName('historyButton')
        self.companion_button.setEnabled(companion is not None)
        self.companion_button.clicked.connect(self.open_companion)
        toolbar.addWidget(self.companion_button)
        self.history_button = QPushButton("過去の会話")
        self.history_button.setObjectName("historyButton")
        self.history_button.clicked.connect(self.open_history)
        toolbar.addWidget(self.history_button)
        layout.addLayout(toolbar)
        self.boot_card = QFrame()
        self.boot_card.setObjectName("noahBubble")
        boot_layout = QVBoxLayout(self.boot_card)
        self.boot_label = QLabel()
        self.boot_label.setTextFormat(Qt.TextFormat.PlainText)
        self.boot_label.setWordWrap(True)
        boot_layout.addWidget(self.boot_label)
        self.boot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.boot_card)
        self.boot_card.hide()
        self.transcript = ConversationView()
        layout.addWidget(self.transcript, 1)
        self.status = QLabel("ここにいるよ。何を話そうか。")
        self.status.setObjectName("status")
        self.status.setMinimumHeight(28)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        composer = QFrame()
        composer.setObjectName("composer")
        row = QHBoxLayout(composer)
        row.setContentsMargins(8, 5, 8, 5)
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Noah に話しかける…")
        self.message_input.setAccessibleName("メッセージ")
        self.message_input.returnPressed.connect(self.send)
        self.send_button = QPushButton("送信")
        self.send_button.clicked.connect(self.send)
        self.message_input.textChanged.connect(self._update_send_button)
        row.addWidget(self.message_input)
        row.addWidget(self.send_button)
        layout.addWidget(composer)
        hint = QLabel("Enter で送信 · 閉じてもメニューバーにいるよ")
        hint.setObjectName("hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._chat_widgets = (self.history_button, self.companion_button, self.transcript, self.status, composer, hint)
        for item in history:
            if item.get("role") in ("user", "assistant") and isinstance(item.get("content"), str):
                self._append("あなた" if item["role"] == "user" else "Noah", item["content"])
        self._update_send_button()
        self._arrange_character()

    def _set_character_motion(self, enabled):
        self.character.set_motion_enabled(enabled)
        self.motion_button.setText('動き ON' if enabled else '動き OFF')

    def _arrange_character(self):
        if self.width() < 800:
            self.body.setDirection(QBoxLayout.Direction.TopToBottom)
            height = max(140, min(240, int(self.height() * .28)))
            self.character.setMinimumSize(0, height)
            self.character.setMaximumHeight(height)
            self.body.setStretch(0, 0)
            self.body.setStretch(1, 1)
        else:
            self.body.setDirection(QBoxLayout.Direction.LeftToRight)
            self.character.setMinimumSize(280, 0)
            self.character.setMaximumHeight(16777215)
            self.body.setStretch(0, 4)
            self.body.setStretch(1, 6)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'character'):
            self._arrange_character()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, 'character'):
            self.character._sync_timer()

    def start_boot(self, sequence, interval_ms=550):
        self._booting = True
        self.presence.setText("目覚めています")
        self.character.set_state('boot')
        for widget in self._chat_widgets:
            widget.hide()
        if self._history_dialog is not None:
            self._history_dialog.close()
        if self._companion_dialog is not None:
            self._companion_dialog.close()
        self._chat_layout.setStretchFactor(self.boot_card, 1)
        self._boot_lines = list(sequence.steps) + list(sequence.ready)
        self.boot_label.setText(sequence.opening)
        self.boot_card.show()
        self._boot_timer.start(interval_ms)

    def _advance_boot(self):
        if self._boot_lines:
            self.boot_label.setText(self._boot_lines.pop(0))
        else:
            self.finish_boot()

    def finish_boot(self):
        self._boot_timer.stop()
        self._boot_lines.clear()
        self.boot_card.hide()
        self._booting = False
        self._chat_layout.setStretchFactor(self.boot_card, 0)
        for widget in self._chat_widgets:
            widget.show()
        self.presence.setText("待機中")
        self.character.set_state('idle')
        self.message_input.setFocus()
        self.transcript._scroll_timer.start(0)

    def open_history(self):
        if self._booting:
            return
        if self._history_dialog is not None:
            self._history_dialog.close()
            self._history_dialog.deleteLater()
        loader = self._archive_loader or self.transcript.toPlainText
        self._history_dialog = HistoryDialog(loader, self)
        self._history_dialog.show()

    def _append(self, speaker: str, text: str):
        self.transcript.append_message(speaker, text)

    def open_companion(self):
        if self._booting or self._companion is None:
            return
        if self._companion_dialog is not None:
            self._companion_dialog.close()
            self._companion_dialog.deleteLater()
        self._companion_dialog = CompanionDialog(self._companion, self)
        self._companion_dialog.show()

    def receive_initiatives(self):
        if self._booting or self._pending or self._companion is None:
            return
        try:
            messages = self._companion.snapshot()['outbox']
            for item in messages:
                if item['id'] not in self._seen_initiatives:
                    self._append('Noah', item['text'])
                    self.character.set_state('reply')
                    self._seen_initiatives.add(item['id'])
        except (OSError, ValueError, KeyError, TypeError):
            return

    def _update_send_button(self):
        self.send_button.setEnabled(not self._pending and bool(self.message_input.text().strip()))

    def show_chat(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.message_input.setFocus()

    def closeEvent(self, event: QCloseEvent):
        if getattr(self, '_quitting', False):
            event.accept()
            return
        event.ignore()
        self.hide()

    def prepare_shutdown(self):
        """Allow QApplication.quit to close the window instead of hiding it."""
        self._quitting = True

    def send(self):
        text = self.message_input.text().strip()
        if self._booting or self._pending or not text:
            return
        self._pending = True
        self._sent_text = text
        self.message_input.clear()
        self._update_send_button()
        self._append("あなた", text)
        self.status.setText("Noah が考えています…")
        self.presence.setText("考え中")
        self.character.set_state('thinking')

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
        self.presence.setText("待機中" if ok else "送信エラー")
        self.character.set_state('reply' if ok else 'error')
        if ok:
            self._append("Noah", reply)
            self.status.setText("聞いているよ。")
        else:
            self.status.setText("返事を受け取れませんでした。接続を確認して、もう一度送信してください。")
            if not self.message_input.text():
                self.message_input.setText(self._sent_text)
        self._update_send_button()
        self.message_input.setFocus()
