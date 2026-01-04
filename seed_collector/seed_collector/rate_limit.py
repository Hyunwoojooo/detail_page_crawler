import asyncio
import time


class RateLimiter:
    def __init__(self, requests_per_second: float) -> None:
        self._rps = float(requests_per_second)
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def acquire(self) -> None:
        if self._rps <= 0:
            return

        interval = 1.0 / self._rps
        async with self._lock:
            now = time.monotonic()
            if now < self._next_allowed:
                await asyncio.sleep(self._next_allowed - now)
            self._next_allowed = max(self._next_allowed, now) + interval
