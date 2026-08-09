"""Tests for the Layer 4 rate limiter.

The in-memory implementation is tested unconditionally; the Redis one
runs only when a server is reachable.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
import redis.asyncio as redis

from src.layer_4_data_access.cache.rate_limiter import (
    InMemoryRateLimiter,
    RateLimiter,
    RedisRateLimiter,
)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


async def _redis_available() -> bool:
    try:
        client = redis.from_url(REDIS_URL)
        await asyncio.wait_for(client.ping(), timeout=1.0)
        await client.aclose()
        return True
    except Exception:  # noqa: BLE001
        return False


requires_redis = pytest.mark.skipif(
    not asyncio.run(_redis_available()),
    reason="No Redis server reachable.",
)


@pytest.fixture
def in_memory() -> InMemoryRateLimiter:
    return InMemoryRateLimiter()


@pytest_asyncio.fixture
async def redis_backed() -> AsyncIterator[RedisRateLimiter]:
    limiter = RedisRateLimiter(REDIS_URL, key_prefix=f"test:rl:{uuid.uuid4()}:")
    yield limiter
    await limiter.disconnect()


async def _exhaust(limiter: RateLimiter, key: str, *, limit: int, window: int):
    return [
        await limiter.check(key, limit=limit, window_seconds=window)
        for _ in range(limit + 2)
    ]


class TestInMemoryLimiter:
    async def test_allows_up_to_the_limit_then_refuses(
        self, in_memory: RateLimiter
    ) -> None:
        decisions = await _exhaust(in_memory, "ip-1", limit=3, window=60)

        assert [d.allowed for d in decisions] == [True, True, True, False, False]

    async def test_reports_what_is_left(self, in_memory: RateLimiter) -> None:
        first = await in_memory.check("ip-1", limit=3, window_seconds=60)

        assert first.remaining == 2

    async def test_a_refusal_says_when_to_retry(
        self, in_memory: RateLimiter
    ) -> None:
        decisions = await _exhaust(in_memory, "ip-1", limit=1, window=45)

        assert decisions[-1].retry_after_seconds == 45

    async def test_keys_are_counted_independently(
        self, in_memory: RateLimiter
    ) -> None:
        # One caller exhausting their budget must not refuse everyone
        # else.
        await _exhaust(in_memory, "ip-1", limit=2, window=60)

        other = await in_memory.check("ip-2", limit=2, window_seconds=60)

        assert other.allowed

    async def test_the_window_slides(self, in_memory: RateLimiter) -> None:
        # A fixed window would let an attacker fire `2 * limit` attempts
        # across a boundary; attempts must age out individually.
        await _exhaust(in_memory, "ip-1", limit=2, window=1)
        assert not (await in_memory.check("ip-1", limit=2, window_seconds=1)).allowed

        await asyncio.sleep(1.1)

        assert (await in_memory.check("ip-1", limit=2, window_seconds=1)).allowed


@requires_redis
class TestRedisLimiter:
    async def test_allows_up_to_the_limit_then_refuses(
        self, redis_backed: RateLimiter
    ) -> None:
        decisions = await _exhaust(redis_backed, "ip-1", limit=3, window=60)

        assert [d.allowed for d in decisions] == [True, True, True, False, False]

    async def test_keys_are_counted_independently(
        self, redis_backed: RateLimiter
    ) -> None:
        await _exhaust(redis_backed, "ip-1", limit=2, window=60)

        assert (await redis_backed.check("ip-2", limit=2, window_seconds=60)).allowed

    async def test_the_window_slides(self, redis_backed: RateLimiter) -> None:
        await _exhaust(redis_backed, "ip-slide", limit=2, window=1)
        assert not (
            await redis_backed.check("ip-slide", limit=2, window_seconds=1)
        ).allowed

        await asyncio.sleep(1.2)

        assert (await redis_backed.check("ip-slide", limit=2, window_seconds=1)).allowed

    async def test_a_second_instance_shares_the_budget(
        self, redis_backed: RedisRateLimiter
    ) -> None:
        """The reason this is Redis and not a per-process counter.

        With one counter per process, an attacker gets the full limit
        against every instance, so adding servers quietly loosens the
        limit.
        """
        await _exhaust(redis_backed, "ip-shared", limit=2, window=60)

        other_instance = RedisRateLimiter(
            REDIS_URL, key_prefix=redis_backed._key_prefix  # noqa: SLF001
        )
        try:
            decision = await other_instance.check(
                "ip-shared", limit=2, window_seconds=60
            )
            assert not decision.allowed
        finally:
            await other_instance.disconnect()

    async def test_concurrent_attempts_cannot_all_slip_through(
        self, redis_backed: RateLimiter
    ) -> None:
        # Count and insert happen in one pipeline, so requests racing
        # each other cannot each read the pre-insert count and all be
        # admitted.
        decisions = await asyncio.gather(
            *[
                redis_backed.check("ip-race", limit=3, window_seconds=60)
                for _ in range(10)
            ]
        )

        assert sum(1 for d in decisions if d.allowed) <= 3

    async def test_an_unreachable_redis_fails_open_by_default(self) -> None:
        # A cache outage should not take logins down entirely; the
        # failure is logged rather than swallowed.
        broken = RedisRateLimiter("redis://127.0.0.1:6390/0")
        try:
            assert (await broken.check("ip-1", limit=1, window_seconds=60)).allowed
        finally:
            await broken.disconnect()
