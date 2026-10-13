"""Async sliding-window rate limiter so free-tier API quotas are respected, not hit."""

from __future__ import annotations

import asyncio
import time
from collections import deque


class RateLimiter:
    def __init__(self, max_calls: int, per_seconds: float):
        self.max_calls, self.per = max_calls, per_seconds
        self._stamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._stamps and now - self._stamps[0] >= self.per:
                    self._stamps.popleft()
                if len(self._stamps) < self.max_calls:
                    self._stamps.append(now)
                    return
                await asyncio.sleep(self.per - (now - self._stamps[0]) + 0.01)


# Free-tier ceilings (Twelve Data: 8/min; Finnhub: 60/min; SEC fair-access: <=10/s).
TWELVEDATA = RateLimiter(8, 60)
FINNHUB = RateLimiter(60, 60)
SEC = RateLimiter(8, 1)
