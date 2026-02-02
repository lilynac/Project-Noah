from pathlib import Path

# src/paths.py の1つ上（プロジェクトルート）
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
MEMORY_DIR = DATA_DIR / "memory"
NOTES_DIR = DATA_DIR / "notes"

# memory（Noahが読み書きする“記憶”系）
CONSULTS_PATH = str(MEMORY_DIR / "consults.txt")
EMOTIONAL_MARKS_PATH = str(MEMORY_DIR / "emotional_marks.txt")
PREFERENCES_PATH = str(MEMORY_DIR / "preferences.txt")
PREFERENCES_HISTORY_PATH = str(MEMORY_DIR / "preferences_history.txt")
NOA_IDENTITY_PATH = str(MEMORY_DIR / "noa_identity.txt")
MODE_PATH = str(MEMORY_DIR / "mode.txt")

# notes（人間が手で書くメモ）
IDEAS_PATH = str(NOTES_DIR / "ideas.txt")
TODO_PATH = str(NOTES_DIR / "todo.txt")
