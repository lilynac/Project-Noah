from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def get_logger(component: str, log_dir: Path, level: str, max_bytes: int, backup_count: int) -> logging.Logger:
    """component別にログを分ける。

    - logs/noah.log: initiative / gating / mute 等
    - logs/service.log: 起動/停止/ロック/pid 等
    - logs/ipc.log: HTTP IPC 入出力

    WARNING+ は logs/<component>.errors.log にも出す
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(component)
    logger.setLevel(getattr(logging, level, logging.INFO))
    logger.propagate = False

    # reload-safe: handler を二重に積まない
    for h in list(logger.handlers):
        logger.removeHandler(h)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    main_path = log_dir / f"{component}.log"
    fh = RotatingFileHandler(main_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.setLevel(getattr(logging, level, logging.INFO))
    logger.addHandler(fh)

    err_path = log_dir / f"{component}.errors.log"
    eh = RotatingFileHandler(err_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8")
    eh.setFormatter(fmt)
    eh.setLevel(logging.WARNING)
    logger.addHandler(eh)

    if os.getenv("NOAH_LOG_CONSOLE", "0").strip().lower() in ("1", "true", "yes", "on"):
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        sh.setLevel(getattr(logging, level, logging.INFO))
        logger.addHandler(sh)

    return logger


def ensure_pid_lock_or_exit(pid_file: Path, lock_file: Path, logger: logging.Logger) -> None:
    """二重起動・取り違え防止のための PID + LOCK。

    - lock が既にある場合は起動しない
    - pid を書く
    """
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.close(fd)
    except FileExistsError:
        try:
            holder = lock_file.read_text(encoding="utf-8").strip()
        except Exception:
            holder = "unknown"
        logger.error("SERVICE_LOCK_EXISTS lock=%s holder=%s", str(lock_file), holder)
        raise SystemExit(2)

    try:
        pid_file.write_text(str(os.getpid()), encoding="utf-8")
    except Exception as e:
        logger.error("SERVICE_PID_WRITE_FAIL pid_file=%s err=%s", str(pid_file), e)

    logger.info("SERVICE_LOCK_ACQUIRED lock=%s pid=%s pid_file=%s", str(lock_file), os.getpid(), str(pid_file))


def cleanup_pid_lock(pid_file: Path, lock_file: Path) -> None:
    try:
        pid_file.unlink(missing_ok=True)
    except Exception:
        pass
    try:
        lock_file.unlink(missing_ok=True)
    except Exception:
        pass
