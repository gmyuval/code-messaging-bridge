"""In-memory rate limiter for webhook endpoints."""

from __future__ import annotations

import time
from collections import defaultdict


class RateLimiter:
    """Simple sliding-window rate limiter using in-memory storage.

    Tracks request timestamps per key and rejects requests
    that exceed the configured rate within the time window.
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """Check if a request from the given key is within rate limits.

        Returns True if allowed, False if rate limit exceeded.
        """
        now = time.monotonic()
        cutoff = now - self._window_seconds

        # Remove expired timestamps
        timestamps = self._requests[key]
        self._requests[key] = [t for t in timestamps if t > cutoff]

        if len(self._requests[key]) >= self._max_requests:
            return False

        self._requests[key].append(now)
        return True
