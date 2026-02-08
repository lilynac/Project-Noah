from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_str(key: str, default: str) -> str:
    raw = os.getenv(key)
    return default if raw is None or raw == "" else raw


@dataclass(frozen=True)
class RuntimeConfig:
    # initiative knobs
    initiative_per_hour: int
    initiative_jitter_seconds: int
    initiative_min_gap_seconds: int
    initiative_recent_user_silence_seconds: int
    initiative_mute_seconds: int
    initiative_conversation_block_seconds: int

    # logging
    log_dir: Path
    log_level: str
    log_max_bytes: int
    log_backup_count: int

    # process safety
    pid_file: Path
    lock_file: Path


def load_runtime_config(base_dir: Path | None = None) -> RuntimeConfig:
    """環境変数（+ .env）から運用設定を読み込む。

    Noah.py 側で load_dotenv() を実行している前提。
    base_dir は既定値（logs/run の置き場）を決めるために使う。
    """
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent

    default_log_dir = base_dir / "logs"
    default_run_dir = base_dir / "run"

    log_dir = Path(_env_str("NOAH_LOG_DIR", str(default_log_dir)))
    pid_file = Path(_env_str("NOAH_PID_FILE", str(default_run_dir / "noah.pid")))
    lock_file = Path(_env_str("NOAH_LOCK_FILE", str(default_run_dir / "noah.lock")))

    return RuntimeConfig(
        initiative_per_hour=_env_int("NOAH_INITIATIVE_PER_HOUR", 5),
        initiative_jitter_seconds=_env_int("NOAH_INITIATIVE_JITTER_SECONDS", 180),
        initiative_min_gap_seconds=_env_int("NOAH_INITIATIVE_MIN_GAP_SECONDS", 120),
        initiative_recent_user_silence_seconds=_env_int("NOAH_INITIATIVE_RECENT_USER_SILENCE_SECONDS", 30),
        initiative_mute_seconds=_env_int("NOAH_INITIATIVE_MUTE_SECONDS", 1800),
        initiative_conversation_block_seconds=_env_int("NOAH_INITIATIVE_CONVERSATION_BLOCK_SECONDS", 300),

        log_dir=log_dir,
        log_level=_env_str("NOAH_LOG_LEVEL", "INFO").upper(),
        log_max_bytes=_env_int("NOAH_LOG_MAX_BYTES", 5 * 1024 * 1024),
        log_backup_count=_env_int("NOAH_LOG_BACKUP_COUNT", 5),

        pid_file=pid_file,
        lock_file=lock_file,
    )
