from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

import requests

T = TypeVar("T")


def sleep_with_backoff(attempt: int, base: float = 1.0, cap: float = 60.0) -> None:
    delay = min(cap, base * (2**attempt)) + random.uniform(0, 0.25 * base * (2**attempt))
    time.sleep(delay)


def request_with_graph_backoff(
    fn: Callable[[], requests.Response],
    *,
    max_retries: int = 5,
) -> requests.Response:
    attempt = 0
    while True:
        resp = fn()
        if resp.status_code != 429:
            return resp
        if attempt >= max_retries:
            return resp
        retry_after = resp.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            time.sleep(int(retry_after))
        else:
            sleep_with_backoff(attempt)
        attempt += 1
