"""Reusable context managers (timing, consistent error logging)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter
from typing import Literal

from src.logging_config import get_logger

logger = get_logger(__name__)

OnErrorMode = Literal["log", "suppress"]


@contextmanager
def timing_context(operation_name: str) -> Iterator[None]:
    """Log wall-clock duration for a block (debug level)."""
    start = perf_counter()
    try:
        yield
    finally:
        duration = perf_counter() - start
        logger.debug("operation_timing", operation=operation_name, duration_seconds=round(duration, 4))


@contextmanager
def error_handling(operation_name: str, *, on_error: OnErrorMode = "log") -> Iterator[None]:
    """Log failures with structured fields; optionally swallow exceptions."""
    try:
        yield
    except Exception as exc:
        logger.error(
            "operation_failed",
            operation=operation_name,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        if on_error == "log":
            raise
        # suppress: swallow
        return
