"""Qt playback and a two-voice audition panel."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from threading import Condition, Thread

from PyQt6.QtCore import QCoreApplication, QLibraryInfo, QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
from PyQt6.QtWidgets import QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from .voice import NemoClient, VOICES, SAMPLE, speech_text


class VoiceController(QObject):
    ready = pyqtSignal(int, bytes)
    failed = pyqtSignal(int)
    status_changed = pyqtSignal(str)
    devices_changed = pyqtSignal()

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.path = Path(root) / 'data/memory/voice.json'
        self.voice, self.enabled = 'female1', True
        self.device_id = ''
        try:
            settings = json.loads(self.path.read_text())
            if settings.get('voice') in VOICES:
                self.voice = settings['voice']
            if type(settings.get('enabled')) is bool:
                self.enabled = settings['enabled']
            if isinstance(settings.get('device_id'), str):
                self.device_id = settings['device_id']
        except (OSError, ValueError, AttributeError):
            pass
        executable = 'run.exe' if os.name == 'nt' else 'run'
        self.client = NemoClient(Path(root) / 'data/voice/nemo' / executable, Path(root) / 'logs/nemo.log')
        # Qt may not enumerate plugins in a macOS synced Documents directory.
        self._plugin_directory = None
        if sys.platform == 'darwin':
            plugin = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)) / 'multimedia/libdarwinmediaplugin.dylib'
            if plugin.is_file():
                self._plugin_directory = tempfile.TemporaryDirectory(prefix='noah-media-')
                target = Path(self._plugin_directory.name) / 'multimedia'
                target.mkdir()
                shutil.copyfile(plugin, target / plugin.name)
                ffmpeg = plugin.with_name('libffmpegmediaplugin.dylib')
                if ffmpeg.is_file():
                    shutil.copyfile(ffmpeg, target / ffmpeg.name)
                QCoreApplication.addLibraryPath(self._plugin_directory.name)
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.output.setVolume(.8)
        self.devices = QMediaDevices(self)
        self.devices.audioOutputsChanged.connect(self._devices_changed)
        self._select_output()
        self.player.setAudioOutput(self.output)
        self._on_ready = None
        self.player.errorOccurred.connect(self._playback_error)
        self.player.playbackStateChanged.connect(self._playback_state)
        self.player.mediaStatusChanged.connect(self._media_status)
        self.ready.connect(self._play)
        self.failed.connect(self._failed)
        self.token = 0
        self.pending = None
        self.closed = False
        self.file = None
        self.condition = Condition()
        Thread(target=self._worker, name='noah-voice', daemon=True).start()

    def configure(self, voice, enabled, device_id=None):
        if voice not in VOICES:
            raise ValueError('Unknown voice')
        self.stop()
        self.voice, self.enabled = voice, bool(enabled)
        if device_id is not None:
            self.device_id = device_id
        self._select_output()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'voice': voice, 'enabled': self.enabled, 'device_id': self.device_id}), encoding='utf-8')
        os.replace(temporary, self.path)

    def _select_output(self):
        device = QMediaDevices.defaultAudioOutput()
        if self.device_id:
            device = next((d for d in QMediaDevices.audioOutputs()
                           if bytes(d.id()).hex() == self.device_id), None)
            if device is None:
                return False
        self.output.setDevice(device)
        return not device.isNull()

    def _devices_changed(self):
        self.stop()
        self._select_output()
        self.devices_changed.emit()

    def speak(self, value, *, preview=False, on_ready=None):
        if self.closed or (not preview and not self.enabled):
            if on_ready:
                on_ready()
            return
        value = speech_text(value)
        if not value:
            if on_ready:
                on_ready()
            return
        self.stop()
        self._on_ready = on_ready
        token = self.token
        if on_ready:
            QTimer.singleShot(8000, lambda: self._presentation_timeout(token))
        with self.condition:
            self.pending = (self.token, value, self.voice)
            self.condition.notify()
        self.status_changed.emit('音声を準備しています…')

    def _reveal(self):
        callback, self._on_ready = self._on_ready, None
        if callback:
            callback()

    def _presentation_timeout(self, token):
        if token == self.token and self._on_ready:
            self.stop()
            self.status_changed.emit('音声の準備に時間がかかるため、文字で届けました。')

    def _playback_state(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._reveal()

    def _playback_error(self, *_):
        self._reveal()
        self.status_changed.emit('音声を再生できませんでした。')

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
            self._reveal()
            self.status_changed.emit('Nemoに接続・合成できませんでした。エンジンの配置と起動ログを確認してください。')

    def _play(self, token, data):
        if self.closed or token != self.token:
            return
        if not self._select_output():
            self._reveal()
            self.status_changed.emit('選択した出力先が見つかりません。接続または出力先を確認してください。')
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
        self._reveal()
        self.status_changed.emit('停止しました。')

    def shutdown(self):
        if self.closed:
            return
        self.stop()
        with self.condition:
            self.closed = True
            self.condition.notify_all()
        self.client.close()
        if self._plugin_directory:
            QCoreApplication.removeLibraryPath(self._plugin_directory.name)
            self._plugin_directory.cleanup()


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
        layout.addWidget(QLabel('音声の出力先（Noahの音量：80%）'))
        self.output_choice = QComboBox()
        layout.addWidget(self.output_choice)
        self.refresh_outputs()
        controller.devices_changed.connect(self.refresh_outputs)
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
        self.output_choice.currentIndexChanged.connect(self.save)
        self.preview.clicked.connect(lambda: controller.speak(SAMPLE, preview=True))
        self.stop_button.clicked.connect(controller.stop)
        controller.status_changed.connect(self.status.setText)

    def save(self, *_):
        try:
            self.controller.configure(self.choice.currentData(), self.enabled.isChecked(), self.output_choice.currentData())
        except OSError:
            self.status.setText('音声設定を保存できませんでした。')

    def refresh_outputs(self):
        self.output_choice.blockSignals(True)
        self.output_choice.clear()
        default = QMediaDevices.defaultAudioOutput().description() or 'なし'
        self.output_choice.addItem(f'Mac/OSの設定に従う：{default}', '')
        for device in QMediaDevices.audioOutputs():
            self.output_choice.addItem(device.description(), bytes(device.id()).hex())
        index = self.output_choice.findData(self.controller.device_id)
        if index < 0:
            self.output_choice.addItem('保存した出力先（未接続）', self.controller.device_id)
            index = self.output_choice.count() - 1
        self.output_choice.setCurrentIndex(index)
        self.output_choice.blockSignals(False)
