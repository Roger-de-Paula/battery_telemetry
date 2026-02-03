import asyncio
import time
from collections import defaultdict


class RateLimiter:
    """In-memory sliding-window rate limiter per device_id."""

    __slots__ = ("_max_requests", "_window_seconds", "_store", "_lock")

    def __init__(self, max_requests: int, window_seconds: float):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._store: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_rate_limited(self, device_id: str) -> bool:
        """Return True if the request should be rejected (rate limited)."""
        now = time.monotonic()
        cutoff = now - self._window_seconds
        async with self._lock:
            timestamps = self._store[device_id]
            timestamps[:] = [t for t in timestamps if t > cutoff]
            if len(timestamps) >= self._max_requests:
                return True
            timestamps.append(now)
            return False


_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        from database import get_settings
        s = get_settings()
        _limiter = RateLimiter(s.rate_limit_requests, s.rate_limit_window_seconds)
    return _limiter
