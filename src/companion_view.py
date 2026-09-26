"""A small window onto Noah's interests, discoveries and chosen plans."""
from .companion import RESEARCH_DAILY_LIMIT, TALK_DAILY_LIMIT, INTEREST_PILLARS, interest_pillar

from .initiative.quality import QUALITY_LABELS
from .conversation_trials import TECHNIQUES, STATUS_LABELS, TRIAL_TURNS

from datetime import datetime
from html import escape
from urllib.parse import urlsplit

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QCheckBox, QDialog, QLabel, QTextBrowser, QVBoxLayout, QHBoxLayout, QPushButton


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
    parts.append('<h3>動画の会話から学ぶ</h3>')
    when = date_label(state.get('next_video_at', 0)) if state.get('video_learning_enabled') else 'お休み中'
    parts.append('<p>次の字幕リサーチ：' + when + '<br>' + escape(state.get('video_status', '')) + '</p>')
    parts.append('<p>字幕の抜粋を読む段階。映像・声色・表情はまだ見聞きしていないよ。</p>')
    for note in reversed(state.get('video_observations', [])[-6:]):
        url = note['url'] + '&t=' + str(int(note['at_seconds']))
        parts.append('<p><b>' + safe_link(url, note['title']) + '</b><br>' + escape(note['observation'])
                     + '<br>合いそうな理由（仮説）：' + escape(note['fit_reason'])
                     + '<br>試作品：' + escape(note['prototype'])
                     + '<br>試す場面：' + escape(note['use_when']) + '<br>避ける場面：' + escape(note['avoid_when'])
                     + '<br>' + escape(note['access']) + '</p>')
        if not note.get('preference'):
            parts.append('<p>あなたの好みとのつながりは未確認。観察のみ保存。</p>')
    for candidate in reversed(state.get('video_candidates', [])[-6:]):
        parts.append('<p>' + safe_link(candidate['url'], candidate['title']) + ' · ' + escape(candidate['status']) + '</p>')
    quality = state.get('last_quality', {})
    if quality.get('reason') in QUALITY_LABELS and quality['reason'] != 'approved':
        parts.append('<p>' + escape(QUALITY_LABELS[quality['reason']]) + ' · ' + date_label(quality['at']) + '</p>')
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
    parts.append('<h3>会話の小さなお試し</h3>')
    adopted = state.get('adopted_style', '')
    if adopted in TECHNIQUES:
        parts.append('<p>続けている工夫：' + escape(TECHNIQUES[adopted]['label']) + '</p>')
    for trial in reversed(state.get('conversation_trials', [])[-3:]):
        proposal = trial['proposal']
        parts.append('<p><b>' + escape(TECHNIQUES[trial['technique']]['label']) + '</b> · '
                     + escape(STATUS_LABELS[trial['status']]) + ' · '
                     + str(len(trial['samples'])) + '/' + str(TRIAL_TURNS) + '返信<br>'
                     + escape(proposal['observation']) + '<br>確かめたいこと：' + escape(proposal['check']) + '</p>')
        before = trial.get('before')
        if before:
            parts.append('<p>開始前の返答（比較の参考）：<br>' + escape(before['noah']) + '</p>')
        for sample in trial['samples']:
            parts.append('<p>あなた：' + escape(sample['user']) + '<br>Noah：' + escape(sample['reply']) + '</p>')
    parts.append('<p>会話の工夫は一度に一つ、成功した返信3回まで。返答がないことを評価にはしないよ。'
                 '表示される前後の返答は話題が違うこともあり、効果を証明する比較ではないよ。</p>')
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
    parts.append('<h3>探究の続き</h3>')
    for trail in reversed(state.get('research_threads', [])):
        parts.append('<h4>' + escape(trail['topic']) + '</h4>')
        for step in trail['steps'][-3:]:
            parts.append('<p><b>' + date_label(step['at']) + '</b><br>')
            if not step.get('learned'):
                parts.append('調査結果を保存したよ。次の振り返りで続きを考える。</p>')
                continue
            for key, label in (('learned', 'わかったこと'), ('open_question', 'まだ気になること'),
                               ('next_reading', '次に読むもの・調べる観点'), ('changed_view', '考えが変わったところ')):
                if step.get(key):
                    parts.append(escape(label) + '：' + escape(step[key]) + '<br>')
            parts.append('出典：' + ' / '.join(safe_link(s['url'], s['title']) for s in step['sources']) + '</p>')
    if not state.get('research_threads'):
        parts.append('<p>調べたことから次の問いを見つけ、ここに続きを残していくね。</p>')
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
        self.video = QCheckBox('VTuberの会話を字幕から学ぶ（1日最大2回・各3本まで）')
        self.video.toggled.connect(lambda value: self.change_setting('video_learning_enabled', value))
        layout.addWidget(self.video)
        self.video_now = QPushButton('字幕リサーチを次の確認で行う')
        self.video_now.clicked.connect(self.request_video_research)
        layout.addWidget(self.video_now)
        self.content = QTextBrowser()
        self.content.setOpenExternalLinks(True)
        layout.addWidget(self.content)
        self.trial_note = QLabel()
        self.trial_note.setWordWrap(True)
        layout.addWidget(self.trial_note)
        controls = QHBoxLayout()
        self.trial_buttons = {}
        for verdict, label in (('adopted', 'この返し方を続ける'), ('stopped', '元に戻す'),
                               ('inconclusive', 'まだ判断できない')):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, v=verdict: self.evaluate_trial(v))
            self.trial_buttons[verdict] = button
            controls.addWidget(button)
        layout.addLayout(controls)
        self.reset_style = QPushButton('採用した返し方を解除する')
        self.reset_style.clicked.connect(self.clear_style)
        layout.addWidget(self.reset_style)
        self._trial_id = None
        self._last_html = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(10_000)
        self.refresh()

    def evaluate_trial(self, verdict):
        if not self._trial_id:
            return
        try:
            self.store.evaluate_trial(self._trial_id, verdict)
        except (OSError, ValueError):
            self.trial_note.setText('評価を保存できませんでした。日々の画面を開き直してください。')
        else:
            self.refresh()

    def request_video_research(self):
        try:
            self.store.change(lambda state: state.update(next_video_at=0,
                video_status='実行待ち。会話中・静穏時間・日次上限では待つよ。'))
            self.refresh()
        except (OSError, ValueError):
            self.content.setPlainText('調査予定を保存できませんでした。')

    def clear_style(self):
        try:
            self.store.reset_adopted_style()
        except (OSError, ValueError):
            self.trial_note.setText('変更を保存できませんでした。')
        else:
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
        trial = next((t for t in reversed(state.get('conversation_trials', []))
                      if t['status'] in ('active', 'awaiting_feedback')), None)
        self._trial_id = trial['id'] if trial else None
        self.trial_note.setText((TECHNIQUES[trial['technique']]['label'] + '：'
                                + STATUS_LABELS[trial['status']] + '。下のボタンで評価できます。')
                               if trial else '次の振り返りで、根拠のある会話の工夫が見つかったら試すね。')
        for verdict, button in self.trial_buttons.items():
            button.setEnabled(trial is not None and (verdict != 'adopted' or bool(trial['samples'])))
        self.reset_style.setVisible(state.get('adopted_style') in TECHNIQUES)
        self.video_now.setEnabled(state.get('video_learning_enabled', False))
        for checkbox, key in ((self.research, 'research_enabled'), (self.talk, 'talk_enabled'), (self.video, 'video_learning_enabled')):
            checkbox.blockSignals(True)
            checkbox.setChecked(state[key])
            checkbox.blockSignals(False)
        if rendered != self._last_html:
            position = self.content.verticalScrollBar().value()
            self.content.setHtml(rendered)
            self.content.verticalScrollBar().setValue(position)
            self._last_html = rendered
