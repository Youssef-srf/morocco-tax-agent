"""Sliding-window rate limits, in memory.

The demo runs as a single container on the free tier, so an in-process
limiter is enough (no Redis). Limits are (max requests, window in seconds).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limits: list[tuple[int, float]]) -> None:
        self.limits = limits
        self.longest = max(window for _, window in limits)
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def hit(self, key: str, now: float | None = None) -> float | None:
        """Record a request for `key`, or return the seconds to wait if a limit is reached."""
        now = time.monotonic() if now is None else now
        with self.lock:
            hits = self.hits[key]
            while hits and now - hits[0] >= self.longest:
                hits.popleft()
            for max_requests, window in self.limits:
                recent = [t for t in hits if now - t < window]
                if len(recent) >= max_requests:
                    return window - (now - recent[0])
            hits.append(now)
            return None
