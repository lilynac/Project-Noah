"""Narrow native compatibility guard for Qt tray activation on macOS 27."""
import ctypes
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

_library = None
_directory = None


def needs_tray_guard(system, mac_version, platform_name):
    if system != 'darwin' or platform_name != 'cocoa':
        return False
    try:
        return int(mac_version.split('.')[0]) >= 27
    except (ValueError, AttributeError):
        return False


def install_tray_guard(app):
    """Install before creating any tray icons. Never attempt Cocoa in offscreen tests."""
    global _library, _directory
    if _library is not None:
        return
    if not needs_tray_guard(sys.platform, platform.mac_ver()[0], app.platformName()):
        return
    source = Path(__file__).with_name('native') / 'macos_tray_guard.m'
    directory = tempfile.TemporaryDirectory(prefix='noah-tray-guard-')
    target = Path(directory.name) / 'libnoah_tray_guard.dylib'
    try:
        subprocess.run(
            ['/usr/bin/xcrun', 'clang', '-dynamiclib', '-fobjc-arc', '-framework', 'AppKit',
             str(source), '-o', str(target)],
            check=True, capture_output=True, text=True, timeout=30,
        )
        library = ctypes.CDLL(str(target))
        library.noah_install_macos_tray_guard.argtypes = []
        library.noah_install_macos_tray_guard.restype = ctypes.c_int
        if library.noah_install_macos_tray_guard() != 1:
            raise RuntimeError('Qt status-item callbacks were not found')
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        directory.cleanup()
        raise RuntimeError('macOS のメニューバー互換処理を準備できませんでした。Command Line Tools と Qt の構成を確認してください。') from exc
    # Keep native code and its backing directory alive as long as Qt callbacks.
    _library, _directory = library, directory
