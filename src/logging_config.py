"""Centralized logging via structlog with stdlib compatibility."""

from __future__ import annotations

import logging
import sys
from typing import Literal

import structlog


def configure_logging(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO",
    use_json: bool = False,
) -> None:
    """Configure structlog + stdlib logging (Flask and %-formatted messages keep working)."""
    lvl = getattr(logging, level, logging.INFO)

    timestamper = structlog.processors.TimeStamper(fmt="iso")

    shared_pre_chain = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer = structlog.processors.JSONRenderer() if use_json else structlog.dev.ConsoleRenderer()
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_pre_chain,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(lvl)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog BoundLogger (stdlib-backed)."""
    return structlog.get_logger(name)
