"""Tiny in-process sliding-window rate limiter (stdlib only).

Per-process state — fine for the single prod uvicorn worker. If the app is ever
scaled to multiple workers this must move to a shared store (Redis etc.).
"""
from __future__ import annotations

import threading
import time

_LOCK = threading.Lock()
_hits: dict[str, list[float]] = {}


def check_and_record(key: str, max_attempts: int, window_seconds: int) -> bool:
    """True if under the limit (and records this attempt); False if over."""
    now = time.time()
    with _LOCK:
        bucket = [t for t in _hits.get(key, ()) if now - t < window_seconds]
        if len(bucket) >= max_attempts:
            _hits[key] = bucket
            return False
        bucket.append(now)
        _hits[key] = bucket
        return True


def reset(key: str) -> None:
    with _LOCK:
        _hits.pop(key, None)


def clear() -> None:
    with _LOCK:
        _hits.clear()
