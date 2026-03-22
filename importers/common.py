"""
Shared utilities for calendar importers.

Provides common logging setup used by import_events and import_holidays.
"""

import logging
import sys


def setup_logging(
    module_name: str, log_file: str | None = None, level: str = "info"
) -> logging.Logger:
    """Configure logging to file and console.

    Args:
        module_name: Logger name (e.g. "import_events")
        log_file: Path to log file; defaults to "<module_name>.log"
        level: Logging level ('debug', 'info', 'warning', 'error')

    Returns:
        Configured logger instance
    """
    log = logging.getLogger(module_name)
    if log_file is None:
        log_file = f"{module_name}.log"

    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    log_level = level_map.get(level.lower(), logging.INFO)
    log.setLevel(log_level)
    log.handlers = []

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(filename)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    log.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(console_handler)

    return log


def make_log_fn(logger_ref: list) -> callable:
    """Return a log() helper that dispatches to a logger stored in a mutable container.

    The container pattern allows the importer module to replace the logger after
    calling setup_logging() while keeping the log() function reference stable.

    Args:
        logger_ref: A single-element list holding the logger (or None)

    Returns:
        A log(message, level) function
    """
    level_names = ("debug", "info", "warning", "error")

    def _log(message: str, level: str = "info") -> None:
        lg = logger_ref[0]
        if lg is None:
            print(message)
            return
        if level not in level_names:
            level = "info"
        getattr(lg, level)(message)

    return _log
