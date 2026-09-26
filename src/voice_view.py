"""Qt playback and a two-voice audition panel."""
import json
import os
import tempfile
from pathlib import Path
from threading import Condition, Thread

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from .voice import NemoClient, VOICES, SAMPLE, speech_text


class VoiceController(QObject):
    ready = pyqtSignal(int, bytes)
    failed = pyqtSignal(int)
    status_changed = pyqtSignal(str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.path = Path(root) / 'data/memory/voice.json'
        self.voice, self.enabled = 'female1', True
        try:
            settings = json.loads(self.path.read_text())
            if settings.get('voice') in VOICES:
                self.voice = settings['voice']
            if type(settings.get('enabled')) is bool:
                self.enabled = settings['enabled']
        except (OSError, ValueError, AttributeError):
            pass
        executable = 'run.exe' if os.name == 'nt' else 'run'
        self.client = NemoClient(Path(root) / 'data/voice/nemo' / executable, Path(root) / 'logs/nemo.log')
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.output.setVolume(.8)
        self.player.setAudioOutput(self.output)
        self.player.errorOccurred.connect(lambda *_: self.status_changed.emit('音声を再生できませんでした。'))
        self.player.mediaStatusChanged.connect(self._media_status)
        self.ready.connect(self._play)
        self.failed.connect(self._failed)
        self.token = 0
        self.pending = None
        self.closed = False
        self.file = None
        self.condition = Condition()
        Thread(target=self._worker, name='noah-voice', daemon=True).start()

    def configure(self, voice, enabled):
        if voice not in VOICES:
            raise ValueError('Unknown voice')
        self.stop()
        self.voice, self.enabled = voice, bool(enabled)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'voice': voice, 'enabled': self.enabled}), encoding='utf-8')
        os.replace(temporary, self.path)

    def speak(self, value, *, preview=False):
        if self.closed or (not preview and not self.enabled):
            return
        value = speech_text(value)
        if not value:
            return
        self.stop()
        with self.condition:
            self.pending = (self.token, value, self.voice)
            self.condition.notify()
        self.status_changed.emit('音声を準備しています…')

    def _worker(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or self.pending is not None)
                if self.closed:
                    return
                token, value, voice = self.pending
                self.pending = None
            try:
                data = self.client.synthesize(value, voice, lambda: token != self.token or self.closed)
                if token == self.token and not self.closed and data:
                    self.ready.emit(token, data)
            except Exception:
                if not self.closed:
                    self.failed.emit(token)

    def _media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._clear_file()
            self.status_changed.emit('読み上げが終わりました。')

    def _failed(self, token):
        if token == self.token:
            self.status_changed.emit('Nemoに接続・合成できませんでした。エンジンの配置と起動ログを確認してください。')

    def _play(self, token, data):
        if self.closed or token != self.token:
            return
        self._clear_file()
        with tempfile.NamedTemporaryFile(suffix='.wav', prefix='noah-voice-', delete=False) as stream:
            stream.write(data)
            self.file = Path(stream.name)
        self.player.setSource(QUrl.fromLocalFile(str(self.file)))
        self.player.play()
        self.status_changed.emit('読み上げています。')

    def _clear_file(self):
        self.player.stop()
        self.player.setSource(QUrl())
        if self.file:
            self.file.unlink(missing_ok=True)
            self.file = None

    def stop(self):
        with self.condition:
            self.token += 1
            self.pending = None
        self._clear_file()
        self.status_changed.emit('停止しました。')

    def shutdown(self):
        if self.closed:
            return
        self.stop()
        with self.condition:
            self.closed = True
            self.condition.notify_all()
        self.client.close()


class VoiceDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle('Noah の声')
        self.resize(440, 260)
        layout = QVBoxLayout(self)
        self.choice = QComboBox()
        for key, (name, cv) in VOICES.items():
            self.choice.addItem(f'{name} · CV：{cv}', key)
        self.choice.setCurrentIndex(self.choice.findData(controller.voice))
        layout.addWidget(self.choice)
        self.enabled = QCheckBox('新しい返答とNoahからの声かけを読み上げる')
        self.enabled.setChecked(controller.enabled)
        layout.addWidget(self.enabled)
        note = QLabel('同じ台詞で声を比べられます。出典URLは読み上げません。')
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        self.preview = QPushButton('この声で試聴')
        self.stop_button = QPushButton('読み上げを停止')
        row.addWidget(self.preview)
        row.addWidget(self.stop_button)
        layout.addLayout(row)
        self.status = QLabel('声を選んで試聴できます。')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        credit = QLabel('音声：VOICEVOX Nemo\n女性1：亜咲比 凛 ／ 女性6：藤田昌代')
        layout.addWidget(credit)
        self.choice.currentIndexChanged.connect(self.save)
        self.enabled.toggled.connect(self.save)
        self.preview.clicked.connect(lambda: controller.speak(SAMPLE, preview=True))
        self.stop_button.clicked.connect(controller.stop)
        controller.status_changed.connect(self.status.setText)

    def save(self, *_):
        try:
            self.controller.configure(self.choice.currentData(), self.enabled.isChecked())
        except OSError:
            self.status.setText('音声設定を保存できませんでした。')
