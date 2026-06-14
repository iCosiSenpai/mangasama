"""Structlog + stdlib logging configuration."""

from __future__ import annotations

import logging
import logging.config
import sys
from pathlib import Path
from typing import Any

import structlog
import yaml


def configure_logging(level: str = "INFO", config_path: Path | None = None) -> None:
    """Configure stdlib logging + structlog from logging.yaml if present."""
    if config_path and config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
        logging.config.dictConfig(data)

    level_num = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=level_num,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        stream=sys.stdout,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level_num),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to the given name."""
    return structlog.get_logger(name)
