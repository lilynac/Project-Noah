import os
import time
import sys
import shutil
import tempfile
from pathlib import Path
from threading import Event

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import pytest
PyQt6 = pytest.importorskip('PyQt6')
from PyQt6.QtCore import Qt, QDir
from PyQt6.QtGui import QIcon
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from src.chat_window import ChatWindow
from src.tray import TrayController, TrayDeps


@pytest.fixture(scope='module')
def app():
    # On macOS, Qt may not enumerate plugins in a synced Documents folder.
    # Use a local temporary copy, just as the desktop launcher does.
    with tempfile.TemporaryDirectory(prefix='noah-qt-test-', dir='/tmp' if sys.platform == 'darwin' else None) as directory:
        previous = os.environ.get('QT_QPA_PLATFORM_PLUGIN_PATH')
        if sys.platform == 'darwin':
            plugin = Path(PyQt6.__path__[0]) / 'Qt6/plugins/platforms/libqoffscreen.dylib'
            shutil.copyfile(plugin, Path(directory) / plugin.name)
            if plugin.name not in QDir(directory).entryList():
                pytest.fail('Qt cannot enumerate its test plugin; GUI initialization was not attempted')
            os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = directory
        try:
            instance = QApplication.instance() or QApplication(['noah-test', '-platformpluginpath', directory] if sys.platform == 'darwin' else [])
            instance.setQuitOnLastWindowClosed(False)
            yield instance
        finally:
            if previous is None:
                os.environ.pop('QT_QPA_PLATFORM_PLUGIN_PATH', None)
            else:
                os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = previous


def wait_until(app, condition):
    deadline = time.monotonic() + 3
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert condition()


def test_enter_reply_and_close_reopen(app):
    calls = []
    def reply(text):
        calls.append(text)
        return 'こんにちは <Noah>'
    window = ChatWindow(reply, [{'role': 'assistant', 'content': '前の会話'}])
    window.show_chat()
    window.message_input.setText('やあ')
    QTest.keyClick(window.message_input, Qt.Key.Key_Return)
    wait_until(app, lambda: not window._pending)
    assert calls == ['やあ']
    assert 'こんにちは <Noah>' in window.transcript.toPlainText()
    assert '前の会話' in window.transcript.toPlainText()
    window.close()
    assert not window.isVisible()
    window.show_chat()
    assert window.isVisible()
    assert 'こんにちは <Noah>' in window.transcript.toPlainText()
    window.hide()


def test_pending_blocks_duplicate_and_keeps_next_draft(app):
    release = Event()
    calls = []
    def reply(text):
        calls.append(text)
        release.wait(2)
        return '返事'
    window = ChatWindow(reply)
    try:
        window.message_input.setText('最初')
        window.send()
        window.message_input.setText('次の話')
        window.send()
        assert not window.send_button.isEnabled()
        window.close()
        release.set()
        wait_until(app, lambda: not window._pending)
        assert calls == ['最初']
        assert window.message_input.text() == '次の話'
        assert window.send_button.isEnabled()
        assert '返事' in window.transcript.toPlainText()
    finally:
        release.set()
        window.hide()


@pytest.mark.parametrize('draft', ['', '新しい下書き'])
def test_failure_restores_input_without_overwriting_draft(app, draft):
    release = Event()
    def fail(text):
        release.wait(2)
        raise OSError('test connection failure')
    window = ChatWindow(fail)
    window.message_input.setText('再送する文')
    window.send()
    window.message_input.setText(draft)
    release.set()
    wait_until(app, lambda: not window._pending)
    assert window.message_input.text() == (draft or '再送する文')
    assert '返事を受け取れませんでした' in window.status.text()
    assert window.send_button.isEnabled()


def test_empty_message_and_tray_open(app):
    calls = []
    window = ChatWindow(lambda text: calls.append(text))
    window.message_input.setText('   ')
    window.send()
    assert not calls
    tray = TrayController(TrayDeps(window.show_chat, lambda mode: None, lambda: None, QIcon()))
    tray.act_talk.trigger()
    assert window.isVisible()
    window.hide()
