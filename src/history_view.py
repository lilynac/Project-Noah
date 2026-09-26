"""Read-only access to the conversation archive, separate from LLM context."""
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QPlainTextEdit, QLabel


class HistoryDialog(QDialog):
    def __init__(self, load_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Noah · 過去の会話")
        self.resize(620, 620)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        self.notice = QLabel("保存された会話を読み返せます。検索して Enter で次の一致へ。")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("会話を検索…")
        self.search.setAccessibleName("履歴を検索")
        next_button = QPushButton("次を検索")
        self.search.returnPressed.connect(self.find_next)
        next_button.clicked.connect(self.find_next)
        row.addWidget(self.search)
        row.addWidget(next_button)
        layout.addLayout(row)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setAccessibleName("過去の会話")
        layout.addWidget(self.text)
        self.setStyleSheet("QDialog { background: #f4f6f3; } QPlainTextEdit { background: white; color: #253932; border: 1px solid #d5ded5; border-radius: 10px; padding: 12px; }")
        try:
            content = load_text()
        except OSError:
            content = ""
            self.notice.setText("履歴を読み込めませんでした。閉じて、もう一度開いてください。")
        else:
            if not content.strip():
                self.notice.setText("保存された会話はまだありません。")
        self.text.setPlainText(content)
        self.text.moveCursor(QTextCursor.MoveOperation.End)

    def find_next(self):
        query = self.search.text().strip()
        if not query:
            return
        if not self.text.find(query):
            self.text.moveCursor(QTextCursor.MoveOperation.Start)
            if not self.text.find(query):
                self.notice.setText("一致する会話が見つかりませんでした。")
                return
        self.notice.setText("Enter で次の一致へ進みます。")
