
from __future__ import annotations

import logging
from pathlib import Path

from .config import LOG_FILE, LOG_LEVEL


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging() -> None:
    root_logger = logging.getLogger()
    level = getattr(logging, str(LOG_LEVEL).upper(), logging.INFO)
    root_logger.setLevel(level)

    log_path = Path(LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    existing_handlers = {getattr(handler, "name", "") for handler in root_logger.handlers}

    if "premium_monitor_file" not in existing_handlers:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.name = "premium_monitor_file"
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root_logger.addHandler(file_handler)

    if "premium_monitor_console" not in existing_handlers:
        console_handler = logging.StreamHandler()
        console_handler.name = "premium_monitor_console"
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        root_logger.addHandler(console_handler)

    logging.captureWarnings(True)


configure_logging()
