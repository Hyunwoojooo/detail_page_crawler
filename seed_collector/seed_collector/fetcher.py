import asyncio
import random
from typing import Dict, Optional
from urllib.parse import urlparse

import httpx

from .rate_limit import RateLimiter


RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    pass


class Fetcher:
    def __init__(
        self,
        concurrency: int,
        rate_limit_rps: float,
        timeout_sec: int,
        retry_count: int,
        user_agent: str,
    ) -> None:
        self._sem = asyncio.Semaphore(max(1, concurrency))
        self._rate_limit_rps = float(rate_limit_rps)
        self._retry_count = max(0, retry_count)
        self._limiters: Dict[str, RateLimiter] = {}
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_sec),
            follow_redirects=True,
            headers={"User-Agent": user_agent},
        )

    async def __aenter__(self) -> "Fetcher":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch(self, url: str) -> httpx.Response:
        limiter = self._get_limiter(url)
        attempt = 0

        while True:
            async with self._sem:
                await limiter.acquire()
                try:
                    response = await self._client.get(url)
                except httpx.RequestError as exc:
                    if attempt >= self._retry_count:
                        raise FetchError(str(exc)) from exc
                    await asyncio.sleep(self._backoff_delay(attempt))
                    attempt += 1
                    continue

            if response.status_code in RETRY_STATUS_CODES and attempt < self._retry_count:
                retry_after = self._parse_retry_after(response)
                await asyncio.sleep(retry_after or self._backoff_delay(attempt))
                attempt += 1
                continue

            return response

    def _get_limiter(self, url: str) -> RateLimiter:
        host = urlparse(url).netloc.lower()
        if host not in self._limiters:
            self._limiters[host] = RateLimiter(self._rate_limit_rps)
        return self._limiters[host]

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        base = 0.5 * (2 ** attempt)
        jitter = random.uniform(0, 0.25)
        return min(base + jitter, 10.0)

    @staticmethod
    def _parse_retry_after(response: httpx.Response) -> Optional[float]:
        retry_after = response.headers.get("Retry-After")
        if not retry_after:
            return None
        try:
            return float(retry_after)
        except ValueError:
            return None
