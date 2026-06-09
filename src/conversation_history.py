# Conversation history storage split from Noah.py.
import json
import os
from threading import Lock

MEMORY_DIR = None
CONVERSATION_HISTORY = []
CONVERSATION_MAX_TURNS = 30
CONVERSATION_PERSIST_FILENAME = "conversation_history.json"
_conversation_lock = Lock()
_persist_lock = Lock()
_error_logger = None

def configure_conversation_history(*, memory_dir=None, error_logger=None, max_turns=None):
    global MEMORY_DIR, _error_logger, CONVERSATION_MAX_TURNS
    if memory_dir is not None:
        MEMORY_DIR = memory_dir
    if error_logger is not None:
        _error_logger = error_logger
    if max_turns is not None:
        CONVERSATION_MAX_TURNS = int(max_turns)

def log_error(code, exc, extra=None):
    if _error_logger is None:
        return
    try:
        _error_logger(code, exc, extra or {})
    except Exception:
        return

def _conversation_persist_path() -> str:
    # MEMORY_DIR 配下に置く（既存の設計に合わせる）
    try:
        os.makedirs(MEMORY_DIR, exist_ok=True)
    except Exception as e:
        log_error("D3_PERSIST_DIR", e, {"path": MEMORY_DIR})
    return os.path.join(MEMORY_DIR, CONVERSATION_PERSIST_FILENAME)

def _sanitize_history(items) -> list[dict]:
    out = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        role = it.get("role")
        content = it.get("content")
        if role not in ("user", "assistant"):
            continue
        if not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        out.append({"role": role, "content": content})
    # 上限を超えたら後ろだけ残す
    max_items = CONVERSATION_MAX_TURNS * 2
    if len(out) > max_items:
        out = out[-max_items:]
    return out

def load_conversation_history() -> None:
    path = _conversation_persist_path()
    try:
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return
        import json
        data = json.loads(raw)
        cleaned = _sanitize_history(data)
        if not cleaned:
            return
        with _conversation_lock:
            CONVERSATION_HISTORY[:] = cleaned
    except Exception as e:
        log_error("D3_LOAD_HISTORY", e, {"path": path})

def persist_conversation_history() -> None:
    path = _conversation_persist_path()
    try:
        import json
        with _conversation_lock:
            payload = list(CONVERSATION_HISTORY)

        tmp = path + ".tmp"
        with _persist_lock:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp, path)  # atomic-ish
    except Exception as e:
        log_error("D3_SAVE_HISTORY", e, {"path": path})

def _recent_turn_texts(max_items: int = 6):
    try:
        with _conversation_lock:
            hist = list(CONVERSATION_HISTORY)
    except Exception:
        hist = []

    out = []
    for m in reversed(hist):
        role = (m or {}).get("role")
        if role not in ("user", "assistant"):
            continue
        txt = (m or {}).get("content") or ""
        txt = txt.strip()
        if not txt:
            continue
        out.append(txt)
        if len(out) >= max_items:
            break
    return list(reversed(out))

