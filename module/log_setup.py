"""
log_setup.py — Live Auto Recorder 통합 로깅 설정

RotatingFileHandler(/app/logs/live-auto-recorder.log) + stdout 이중 출력.
LOG_LEVEL 환경변수로 레벨 제어 (기본 INFO, DEBUG로 내리면 probe 로그 표시).
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")
LOG_FILE = os.path.join(LOG_DIR, "live-auto-recorder.log")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

_initialized = False


def setup_logging() -> logging.Logger:
    """최초 1회 호출. root 로거 설정 후 반환."""
    global _initialized
    root = logging.getLogger("live-auto-recorder")
    if _initialized:
        return root
    _initialized = True

    level = getattr(logging, LOG_LEVEL, logging.INFO)
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        fh = RotatingFileHandler(
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:
        pass

    return root


def get_logger(name: str) -> logging.Logger:
    """모듈별 로거."""
    return logging.getLogger(f"live-auto-recorder.{name}")
