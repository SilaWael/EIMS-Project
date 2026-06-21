# -*- coding: utf-8 -*-
"""
EIMS Logging Module
===================
Replaces silent `except: pass` with proper logging to file + console.

Log files rotate automatically to prevent unbounded growth.
Located in: ./logs/eims.log
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime


LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "eims.log")
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 5 MB per file, 5 backup files (~25 MB max)
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5

_initialized = False
_loggers = {}


def _ensure_log_dir():
    if not os.path.isdir(LOG_DIR):
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
        except FileExistsError:
            pass


def _init_root_logger():
    global _initialized
    if _initialized:
        return
    _ensure_log_dir()

    root = logging.getLogger("eims")
    root.setLevel(logging.DEBUG)

    # Avoid duplicate handlers on re-init
    if root.handlers:
        _initialized = True
        return

    # File handler (rotating)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

    root.addHandler(file_handler)
    root.addHandler(console_handler)

    _initialized = True
    root.info("=" * 60)
    root.info(f"EIMS logging initialized at {datetime.now().isoformat()}")
    root.info("=" * 60)


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the 'eims' namespace.

    Usage:
        from core.logger import get_logger
        log = get_logger(__name__)
        log.info("...")
        log.error("...", exc_info=True)
    """
    _init_root_logger()
    if name not in _loggers:
        # All loggers are children of 'eims' so they share handlers
        full_name = f"eims.{name}" if not name.startswith("eims") else name
        _loggers[name] = logging.getLogger(full_name)
    return _loggers[name]


def log_exception(logger, message: str, exc: Exception = None):
    """Convenience wrapper for logging exceptions with full traceback.

    Usage:
        try:
            risky_op()
        except Exception as e:
            log_exception(log, "Failed to save record", e)
    """
    logger.error(message, exc_info=exc if exc else True)


if __name__ == "__main__":
    log = get_logger("test")
    log.debug("Debug message")
    log.info("Info message")
    log.warning("Warning message")
    try:
        1 / 0
    except Exception as e:
        log_exception(log, "Test exception", e)
    print(f"\nLog file written to: {os.path.abspath(LOG_FILE)}")
