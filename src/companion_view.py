"""A small window onto Noah's interests, discoveries and chosen plans."""
from .companion import RESEARCH_DAILY_LIMIT, TALK_DAILY_LIMIT, INTEREST_PILLARS, interest_pillar

from datetime import datetime
from html import escape
from urllib.parse import urlsplit

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QCheckBox, QDialog, QLabel, QTextBrowser, QVBoxLayout


def safe_link(url, title=None):
    try:
        parsed = urlsplit(url)
        if parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username:
            return '<a href="' + escape(url, quote=True) + '">' + escape(title or url) + '</a>'
    except ValueError:
        pass
    return escape(title or url)


def message_html(value):
    # Only a standalone HTTP(S) URL becomes a link. All other content is escaped.
    return '<br>'.join(safe_link(line) if line.startswith(('https://', 'http://'))
                       else escape(line) for line in value.split('\n'))


def date_label(timestamp):
    return datetime.fromtimestamp(timestamp).strftime("%m/%d %H:%M") if timestamp else "これから決める"


def journal_html(state):
    parts = ['<h3>このあとの予定</h3>', '<p>' + escape(state['plan_reason']) + '</p>']
    for key, label, enabled in (("research", "気になることを調べる", "research_enabled"),
                                ("talk", "あなたに話したい", "talk_enabled")):
        if key == 'research' and state['research_topic']:
            label = '「' + escape(state['research_topic']) + '」を調べる'
        when = date_label(state['next_' + key + '_at']) if state[enabled] else 'お休み中'
        parts.append('<p>' + label + ' · ' + when + '</p>')
    parts.append('<p>予定は目安。会話中や作業中は待つこともあるよ。</p>')
    if state['last_error']:
        parts.append('<p>' + escape(state['last_error']) + '</p>')
    parts.append('<h3>いま気になっていること</h3>')
    for pillar, label in INTEREST_PILLARS.items():
        parts.append('<h4>' + escape(label) + '</h4>')
        items = [item for item in reversed(state['interests']) if interest_pillar(item) == pillar]
        for item in items:
            parts.append('<p><b>' + escape(item['topic']) + '</b><br>' + escape(item['reason']) + '</p>')
        if not items:
            parts.append('<p>会話の中から、関心の理由を少しずつ見つけていくね。</p>')
    parts.append('<h3>試してみたいこと</h3>')
    for item in reversed(state.get('improvements', [])):
        parts.append('<p><b>' + escape(item['change']) + '</b> · 提案<br>'
                     + escape(item['observation']) + '<br>試作品：' + escape(item['prototype'])
                     + '<br>確かめたいこと：' + escape(item['check']) + '</p>')
        evidence = item.get('evidence', {})
        if evidence.get('sources'):
            parts.append('<p>きっかけ：' + ' / '.join(safe_link(s['url'], s['title']) for s in evidence['sources']) + '</p>')
        elif evidence.get('user'):
            parts.append('<p>きっかけになった言葉：' + escape(evidence['user'][:360]) + '</p>')
    if not state.get('improvements'):
        parts.append('<p>会話や発見から、試してみたい工夫を見つけていく。実装済みの機能とは別の提案だよ。</p>')
    parts.append('<h3>わたしの好きになったもの</h3>')
    parts.extend('<p>' + escape(item['text']) + '</p>' for item in state['preferences'])
    if not state['preferences']:
        parts.append('<p>好きになるきっかけを、ひとつずつ。</p>')
    parts.append('<h3>ふたりの記憶</h3>')
    parts.extend('<p>' + escape(item['text']) + '</p>' for item in state['memories'])
    if not state['memories']:
        parts.append('<p>会話を重ねて、覚えておきたいことが増えていく。</p>')
    parts.append('<h3>見つけたこと</h3>')
    for finding in reversed(state['findings']):
        parts.append('<p><b>' + escape(finding['topic']) + '</b> · ' + date_label(finding['at']) + '<br>'
                     + escape(finding['summary']).replace('\n', '<br>') + '</p>')
        parts.append('<p>出典：<br>' + '<br>'.join(safe_link(s['url'], s['title']) for s in finding['sources']) + '</p>')
    return ''.join(parts)


class CompanionDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle('Noah の日々')
        self.resize(560, 680)
        self.setStyleSheet('QDialog { background: #f4f6f3; } QTextBrowser { background: white; border: 1px solid #d5ded5; border-radius: 12px; padding: 12px; } QCheckBox { padding: 4px 0; }')
        layout = QVBoxLayout(self)
        note = QLabel('ふたりの会話と、わたしが見つけたもの。')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.research = QCheckBox(f'気になることを調べる（検索 API を利用・1日最大{RESEARCH_DAILY_LIMIT}回）')
        self.talk = QCheckBox(f'Noah から話しかける（1日最大{TALK_DAILY_LIMIT}回）')
        self.research.toggled.connect(lambda value: self.change_setting('research_enabled', value))
        self.talk.toggled.connect(lambda value: self.change_setting('talk_enabled', value))
        layout.addWidget(self.research)
        layout.addWidget(self.talk)
        self.content = QTextBrowser()
        self.content.setOpenExternalLinks(True)
        layout.addWidget(self.content)
        self._last_html = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(10_000)
        self.refresh()

    def change_setting(self, key, value):
        try:
            self.store.set_enabled(key, value)
        except (OSError, ValueError):
            self.content.setPlainText('設定を保存できませんでした。もう一度開いてください。')
        else:
            self.refresh()

    def refresh(self):
        try:
            state = self.store.snapshot()
            rendered = journal_html(state)
        except (OSError, ValueError, KeyError, TypeError):
            self.content.setPlainText('日々の記録を読み込めませんでした。元の記録はそのまま残しています。')
            return
        for checkbox, key in ((self.research, 'research_enabled'), (self.talk, 'talk_enabled')):
            checkbox.blockSignals(True)
            checkbox.setChecked(state[key])
            checkbox.blockSignals(False)
        if rendered != self._last_html:
            position = self.content.verticalScrollBar().value()
            self.content.setHtml(rendered)
            self.content.verticalScrollBar().setValue(position)
            self._last_html = rendered
