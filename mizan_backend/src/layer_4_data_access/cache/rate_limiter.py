"""Layer 4 — request rate limiting, backed by Redis.

Redis rather than an in-process counter for the same reason the token
blocklist uses it: behind a load balancer, a per-process counter lets an
attacker get N attempts *per instance*, so the limit silently loosens
with every server added.

Layer 3 already has an in-memory `MessageRateLimiter` for chat, which is
pure and per-connection. This one is a different problem — it counts
across processes and therefore needs I/O, which is why it lives here.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)

DEFAULT_KEY_PREFIX = "ratelimit:"


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """The outcome of one rate-limit check."""

    allowed: bool
    #: Attempts still available in the current window.
    remaining: int
    #: Seconds until the caller may retry, for a `Retry-After` header.
    retry_after_seconds: int


class RateLimiter(ABC):
    """Counts attempts per key within a rolling window."""

    @abstractmethod
    async def check(
        self, key: str, *, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        """Records an attempt against `key` and reports whether it is
        allowed."""


class RedisRateLimiter(RateLimiter):
    """Sliding-window limiter using a Redis sorted set per key.

    A sliding window rather than a fixed one: with fixed windows an
    attacker gets `2 * limit` attempts across a boundary by firing at
    the end of one window and the start of the next, which for a login
    endpoint is exactly the burst the limit exists to stop.

    Each attempt is one sorted-set member scored by timestamp. Every
    check drops members older than the window, counts what remains, and
    adds the current attempt — in a single pipeline, so concurrent
    requests cannot interleave between the count and the insert and both
    be allowed through.
    """

    def __init__(
        self,
        redis_url: str,
        *,
        key_prefix: str = DEFAULT_KEY_PREFIX,
        fail_open: bool = True,
    ) -> None:
        """
        Args:
            redis_url: Connection URL, from `config.Settings.redis_url`.
            key_prefix: Namespace for this limiter's keys.
            fail_open: Whether an unreachable Redis admits the request.
                Defaults to `True`: a cache outage should not take
                logins down entirely. The trade-off is that
                brute-force protection is absent for the duration, so
                the failure is logged rather than swallowed.
        """
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._fail_open = fail_open
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        if self._client is not None:
            return
        self._client = redis.from_url(self._redis_url, decode_responses=True)

    async def disconnect(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            await client.aclose()

    async def check(
        self, key: str, *, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        try:
            await self.connect()
            assert self._client is not None

            now = time.time()
            window_start = now - window_seconds
            redis_key = f"{self._key_prefix}{key}"

            pipeline = self._client.pipeline()
            pipeline.zremrangebyscore(redis_key, 0, window_start)
            pipeline.zcard(redis_key)
            # A unique member per attempt; two requests in the same
            # microsecond must not collapse into one.
            pipeline.zadd(redis_key, {f"{now}:{id(object())}": now})
            pipeline.expire(redis_key, window_seconds)
            _, prior_attempts, _, _ = await pipeline.execute()

            allowed = prior_attempts < limit
            remaining = max(0, limit - prior_attempts - 1)
            return RateLimitDecision(
                allowed=allowed,
                remaining=remaining,
                retry_after_seconds=window_seconds if not allowed else 0,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Rate limiter unreachable; %s this request.",
                "allowing" if self._fail_open else "rejecting",
            )
            return RateLimitDecision(
                allowed=self._fail_open,
                remaining=0,
                retry_after_seconds=0 if self._fail_open else window_seconds,
            )


class InMemoryRateLimiter(RateLimiter):
    """Process-local limiter, for tests and single-process local runs.

    Enforces the same sliding window, but only for one process — behind
    a load balancer it would grant the limit per instance.
    """

    def __init__(self) -> None:
        self._attempts: Dict[str, List[float]] = {}

    async def check(
        self, key: str, *, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        now = time.monotonic()
        window_start = now - window_seconds

        recent = [at for at in self._attempts.get(key, []) if at > window_start]
        allowed = len(recent) < limit
        recent.append(now)
        self._attempts[key] = recent

        return RateLimitDecision(
            allowed=allowed,
            remaining=max(0, limit - len(recent)),
            retry_after_seconds=window_seconds if not allowed else 0,
        )
