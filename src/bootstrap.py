from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

from .paths import (
    DATA_DIR,
    MEMORY_DIR,
    NOTES_DIR,
    CONSULTS_PATH,
    EMOTIONAL_MARKS_PATH,
    PREFERENCES_PATH,
    PREFERENCES_HISTORY_PATH,
    NOAH_IDENTITY_PATH,
    MODE_PATH,
    IDEAS_PATH,
    TODO_PATH,
)

def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def _touch_file(filepath: str, *, initial_text: Optional[str] = None) -> None:
    p = Path(filepath)
    _ensure_dir(p.parent)

    if p.exists():
        return

    # 空ファイル or 初期テキストで作成
    if initial_text is None:
        p.write_text("", encoding="utf-8")
    else:
        p.write_text(initial_text, encoding="utf-8")

def bootstrap_files() -> None:
    """
    初回起動時の安全対策：
    - data/ 配下の必要ディレクトリを作る
    - 必須の txt が無ければ作る（空 or 最小テンプレ）
    """
    _ensure_dir(Path(DATA_DIR))
    _ensure_dir(Path(MEMORY_DIR))
    _ensure_dir(Path(NOTES_DIR))

    # --- memory（Noahが読み書きする“記憶”系） ---
    _touch_file(CONSULTS_PATH)
    _touch_file(EMOTIONAL_MARKS_PATH)

    # preferences は最小テンプレを入れておくと後段の処理が安定しやすい
    preferences_template = (
        "# preferences.txt\n"
        "# Noah が会話から抽出した「好み・ルール・口調」などの短いメモ\n"
        "# ここは要約で、長文化させない（必要なら history に逃がす）\n"
        "\n"
    )
    _touch_file(PREFERENCES_PATH, initial_text=preferences_template)
    _touch_file(PREFERENCES_HISTORY_PATH)

    # identity / mode
    noah_identity_template = (
        "# noah_identity.txt\n"
        "# Noah の自己定義・役割・口調の基礎\n"
        "\n"
    )
    _touch_file(NOAH_IDENTITY_PATH, initial_text=noah_identity_template)

    # mode はデフォルト値を入れる（無いと分岐で困ることが多い）
    _touch_file(
        MODE_PATH,
        initial_text=(
            "mode: normal\n"
            "since:\n"
            "set_by: bootstrap\n"
            "note:\n"
        ),
    )


    # --- notes（人間が手で書くメモ） ---
    _touch_file(IDEAS_PATH)
    _touch_file(TODO_PATH)

def bootstrap_once(verbose: bool = False) -> None:
    """
    実行時に呼ぶ入口。必要なら簡単な出力もできる。
    """
    before = set()
    if verbose:
        # 生成前に存在チェックして、何を作ったか雑に見える化
        for f in [
            CONSULTS_PATH,
            EMOTIONAL_MARKS_PATH,
            PREFERENCES_PATH,
            PREFERENCES_HISTORY_PATH,
            NOAH_IDENTITY_PATH,
            MODE_PATH,
            IDEAS_PATH,
            TODO_PATH,
        ]:
            if Path(f).exists():
                before.add(f)

    bootstrap_files()

    if verbose:
        created = []
        for f in [
            CONSULTS_PATH,
            EMOTIONAL_MARKS_PATH,
            PREFERENCES_PATH,
            PREFERENCES_HISTORY_PATH,
            NOAH_IDENTITY_PATH,
            MODE_PATH,
            IDEAS_PATH,
            TODO_PATH,
        ]:
            if f not in before and Path(f).exists():
                created.append(f)

        if created:
            print("[bootstrap] created:")
            for f in created:
                print("  -", f)
        else:
            print("[bootstrap] nothing to create (already initialized)")
