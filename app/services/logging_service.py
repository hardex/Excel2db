import logging
import os
from pathlib import Path

LOG_PATH = Path("logs/app.log")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
_handler.setFormatter(
    logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)

logger = logging.getLogger("excel2db")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    logger.addHandler(_handler)

# Also log to console for development
_console = logging.StreamHandler()
_console.setFormatter(
    logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)
if len(logger.handlers) < 2:
    logger.addHandler(_console)


def get_logger() -> logging.Logger:
    return logger


def get_log_lines(n: int = 200) -> list[str]:
    """Return last n lines from the log file."""
    if not LOG_PATH.exists():
        return []
    with open(LOG_PATH, encoding="utf-8") as f:
        lines = f.readlines()
    return lines[-n:]
