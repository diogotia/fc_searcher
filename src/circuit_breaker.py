"""Circuit breaker for external calls (Graph, Claude, SMTP, etc.)."""

from __future__ import annotations

from enum import Enum
from threading import Lock
from time import time
from typing import Any, Callable, TypeVar

from src.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(RuntimeError):
    """Raised when the circuit is open and recovery timeout has not elapsed."""


class CircuitBreaker:
    """Simple thread-safe circuit breaker for blocking callables."""

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
    ) -> None:
        self.name = name
        self.failure_threshold = max(1, failure_threshold)
        self.recovery_timeout = max(1, recovery_timeout)
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._state = CircuitState.CLOSED
        self._lock = Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    def reset(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._last_failure_time = None
            self._state = CircuitState.CLOSED

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset_unlocked():
                    self._state = CircuitState.HALF_OPEN
                    logger.info("circuit_half_open", circuit=self.name)
                else:
                    raise CircuitBreakerOpenError(f"Circuit {self.name} is OPEN")

        try:
            result = func(*args, **kwargs)
        except Exception:
            self._on_failure()
            raise

        self._on_success()
        return result

    def _should_attempt_reset_unlocked(self) -> bool:
        if self._last_failure_time is None:
            return True
        return time() - self._last_failure_time >= self.recovery_timeout

    def _on_success(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0

    def _on_failure(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._last_failure_time = time()
                self._failure_count = self.failure_threshold
                logger.warning("circuit_open_from_half_open", circuit=self.name)
                return
            self._failure_count += 1
            self._last_failure_time = time()
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning("circuit_open", circuit=self.name, failures=self._failure_count)


# Shared instances for optional use by services (not wired by default).
facebook_graph_circuit = CircuitBreaker("facebook_graph", failure_threshold=5, recovery_timeout=60)
claude_circuit = CircuitBreaker("claude", failure_threshold=3, recovery_timeout=120)
