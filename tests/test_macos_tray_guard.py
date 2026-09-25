from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

from src import macos_tray_guard as guard


@pytest.mark.parametrize('system,version,backend,expected', [
    ('darwin', '27.0', 'cocoa', True),
    ('darwin', '26.0', 'cocoa', False),
    ('darwin', '27.0', 'offscreen', False),
    ('win32', '', 'windows', False),
    ('linux', '', 'xcb', False),
])
def test_platform_scope(system, version, backend, expected):
    assert guard.needs_tray_guard(system, version, backend) is expected


def test_offscreen_never_loads_native_guard(monkeypatch):
    compile_call = Mock()
    monkeypatch.setattr(guard.subprocess, 'run', compile_call)
    guard.install_tray_guard(Mock(platformName=lambda: 'offscreen'))
    compile_call.assert_not_called()


@pytest.mark.skipif(sys.platform != 'darwin', reason='Objective-C/AppKit regression test')
def test_native_callbacks_filter_system_events_and_preserve_mouse(tmp_path):
    root = Path(__file__).resolve().parents[1]
    executable = tmp_path / 'tray-guard-test'
    subprocess.run([
        '/usr/bin/xcrun', 'clang', '-fobjc-arc', '-framework', 'AppKit',
        str(root / 'src/native/macos_tray_guard.m'),
        str(root / 'tests/native_tray_guard_harness.m'), '-o', str(executable),
    ], check=True, capture_output=True, text=True, timeout=30)
    result = subprocess.run([str(executable)], check=True, capture_output=True, text=True, timeout=10)
    assert 'mouse callbacks preserved' in result.stdout
