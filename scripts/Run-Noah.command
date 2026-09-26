#!/bin/zsh
cd "${0:A:h:h}" || exit 1
mkdir -p logs
# Use the plugins bundled with this virtual environment's PyQt6.
noah_qt_plugins="$(.venv/bin/python -c 'from pathlib import Path; import PyQt6; print(Path(PyQt6.__path__[0]) / "Qt6" / "plugins")')" || exit 1
if [[ ! -f "$noah_qt_plugins/platforms/libqcocoa.dylib" ]]; then
  printf 'macOS 用 Qt プラグインが見つかりません: %s\n' "$noah_qt_plugins"
  read -r '?Enter で終了'
  exit 1
fi
export QT_PLUGIN_PATH="$noah_qt_plugins"
# Qt may fail to enumerate plugins in a synced Documents directory.
noah_platform_dir="$(mktemp -d "${TMPDIR:-/tmp}/noah-qt.XXXXXX")" || exit 1
trap 'rm -rf -- "$noah_platform_dir"' EXIT
cp "$noah_qt_plugins/platforms/libqcocoa.dylib" "$noah_platform_dir/" || exit 1
export QT_QPA_PLATFORM_PLUGIN_PATH="$noah_platform_dir"
export QT_QPA_PLATFORM=cocoa
.venv/bin/python -u -m src 2>&1 | tee logs/launcher.log
result=${pipestatus[1]}
if [ "$result" -ne 0 ]; then
  printf '\nNoah の起動に失敗しました。上のエラーを確認してください。\n'
  read -r '?Enter で終了'
fi
exit "$result"
