"""
utils/logging_config.py — Centralized structured logging setup.

All modules log via logging.getLogger("kt_assist.<module>") so a single
call to configure_logging() controls format/level application-wide.
"""

import logging
import sys

import config


def configure_logging() -> None:
    root = logging.getLogger("kt_assist")
    if root.handlers:
        return  # already configured (avoid duplicate handlers on reload)

    root.setLevel(config.LOG_LEVEL)

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.propagate = False
