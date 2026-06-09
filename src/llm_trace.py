# LLM trace helpers split from Noah.py.
import hashlib
import json
import os
import time
from pathlib import Path
from threading import Lock

_LOG_DIR = Path("logs")
TRACE_MAX_TURNS = 20
_TRACE_LOCK = Lock()

def configure_trace(*, log_dir=None, max_turns=None):
    global _LOG_DIR, TRACE_MAX_TURNS
    if log_dir is not None:
        _LOG_DIR = Path(log_dir)
    if max_turns is not None:
        TRACE_MAX_TURNS = int(max_turns)

def _trace_path() -> str:
    # _LOG_DIR 配下に保存
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
    except Exception:
        pass
    return str(_LOG_DIR / "llm_trace.jsonl")

def trace_llm(event: str, payload: dict) -> None:
    """
    1行JSONで LLMの入出力を記録する。
    event: "LLM_IN" / "LLM_OUT" / "LLM_ERR"
    """
    try:
        rec = {"ts": time.time(), "event": event, **payload}
        line = json.dumps(rec, ensure_ascii=False)
        with _TRACE_LOCK:
            with open(_trace_path(), "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        return

def _prune_trace_file_keep_last_turns(_current_turn_id: int) -> None:
    """
    llm_trace.jsonl を「最新TRACE_MAX_TURNSターン分」だけ残す（再起動に強い）。
    ファイル内の turn_id を見て “末尾の distinct turn_id” を基準に保持する。
    """
    try:
        path = _trace_path()
        if TRACE_MAX_TURNS <= 0:
            return
        if not os.path.exists(path):
            return

        records = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                tid = rec.get("turn_id")
                if not isinstance(tid, int):
                    continue
                records.append(rec)

        if not records:
            # 古い形式だけなら空にする（方針は好みで）
            with open(path, "w", encoding="utf-8") as f:
                f.write("")
            return

        # 末尾から distinct turn_id を集めて、残すべき turn_id 集合を作る
        keep_tids = []
        seen = set()
        for rec in reversed(records):
            tid = rec["turn_id"]
            if tid in seen:
                continue
            seen.add(tid)
            keep_tids.append(tid)
            if len(keep_tids) >= TRACE_MAX_TURNS:
                break
        keep_set = set(keep_tids)

        kept_lines = []
        for rec in records:
            if rec.get("turn_id") in keep_set:
                kept_lines.append(json.dumps(rec, ensure_ascii=False))

        with open(path, "w", encoding="utf-8") as f:
            for l in kept_lines:
                f.write(l + "\n")

    except Exception:
        return

def _role_counts(messages: list[dict]) -> dict:
    ct = {"system": 0, "developer": 0, "user": 0, "assistant": 0, "other": 0}
    for m in (messages or []):
        r = (m or {}).get("role")
        if r in ct:
            ct[r] += 1
        else:
            ct["other"] += 1
    return ct

def _compact_messages(messages: list[dict], *, max_items: int = 24, preview: int = 120) -> list[dict]:
    """
    見やすさ優先の縮約:
    - 全 messages を残さず、末尾中心で max_items 件に抑える
    - content は preview だけ
    """
    msgs = list(messages or [])
    if len(msgs) > max_items:
        # “最後の会話の流れ”が見たいので末尾を優先
        msgs = msgs[-max_items:]

    out = []
    for i, m in enumerate(msgs):
        role = (m or {}).get("role", "unknown")
        content = (m or {}).get("content", "")
        # content が list/構造体の場合もあるので str に寄せる
        if not isinstance(content, str):
            try:
                content = json.dumps(content, ensure_ascii=False)
            except Exception:
                content = str(content)
        out.append({
            "i": i,
            "role": role,
            "preview": _safe_preview(content, preview),
            "len": len(content or ""),
            "hash": _hash_text(content or ""),
        })
    return out

def _llm_in_pretty(messages: list[dict]) -> dict:
    """
    LLMに投げた input を人間が追える形に整える。
    """
    # system/developer の先頭数個は “制約の正体” なので優先的に見える化
    sys_dev = []
    for m in (messages or []):
        if (m or {}).get("role") in ("system", "developer"):
            content = (m or {}).get("content", "")
            if not isinstance(content, str):
                try:
                    content = json.dumps(content, ensure_ascii=False)
                except Exception:
                    content = str(content)
            sys_dev.append({
                "role": m.get("role"),
                "preview": _safe_preview(content, 200),
                "hash": _hash_text(content),
            })
        if len(sys_dev) >= 6:
            break

    return {
        "n_messages": len(messages or []),
        "role_counts": _role_counts(messages or []),
        "sys_dev_head": sys_dev,
        "tail": _compact_messages(messages or [], max_items=26, preview=140),
    }

def _safe_preview(text: str, n: int = 80) -> str:
    t = (text or "").replace("\n", " ").strip()
    return t[:n]

def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:12]

def _hash_short(text: str) -> str:
    try:
        t = (text or "").strip()
    except Exception:
        t = (text or "").strip()
    return _hash_text(t)

