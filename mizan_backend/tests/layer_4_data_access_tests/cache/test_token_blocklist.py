"""Tests for the Layer 4 token blocklist.

The in-memory implementation is tested unconditionally; the Redis one
runs only when a server is reachable. Both satisfy the same
`TokenBlocklist` interface, and the shared cases below run against
each, because the whole point of the abstraction is that Layer 2 cannot
tell them apart.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
import redis.asyncio as redis

from src.layer_4_data_access.cache.token_blocklist import (
    InMemoryTokenBlocklist,
    RedisTokenBlocklist,
    TokenBlocklist,
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


@pytest_asyncio.fixture
async def in_memory() -> InMemoryTokenBlocklist:
    return InMemoryTokenBlocklist()


@pytest_asyncio.fixture
async def redis_backed() -> AsyncIterator[RedisTokenBlocklist]:
    blocklist = RedisTokenBlocklist(
        REDIS_URL, key_prefix=f"test:blocklist:{uuid.uuid4()}:"
    )
    yield blocklist
    await blocklist.disconnect()


class TestInMemoryBlocklist:
    async def test_an_unknown_token_is_not_revoked(
        self, in_memory: TokenBlocklist
    ) -> None:
        assert not await in_memory.is_revoked("never-seen")

    async def test_a_revoked_token_is_reported_as_revoked(
        self, in_memory: TokenBlocklist
    ) -> None:
        await in_memory.revoke("jti-1", ttl_seconds=60)

        assert await in_memory.is_revoked("jti-1")

    async def test_revoking_one_token_leaves_others_alone(
        self, in_memory: TokenBlocklist
    ) -> None:
        await in_memory.revoke("jti-1", ttl_seconds=60)

        assert not await in_memory.is_revoked("jti-2")

    async def test_a_zero_ttl_is_a_no_op(self, in_memory: TokenBlocklist) -> None:
        # The token has already expired, so it is refused on its own
        # `exp` claim; storing it would waste space blocking something
        # already dead.
        await in_memory.revoke("jti-expired", ttl_seconds=0)

        assert not await in_memory.is_revoked("jti-expired")

    async def test_a_negative_ttl_is_a_no_op(
        self, in_memory: TokenBlocklist
    ) -> None:
        await in_memory.revoke("jti-past", ttl_seconds=-30)

        assert not await in_memory.is_revoked("jti-past")

    async def test_an_entry_stops_blocking_once_it_expires(
        self, in_memory: TokenBlocklist
    ) -> None:
        await in_memory.revoke("jti-brief", ttl_seconds=1)
        assert await in_memory.is_revoked("jti-brief")

        await asyncio.sleep(1.1)

        assert not await in_memory.is_revoked("jti-brief")

    async def test_revoking_twice_is_harmless(
        self, in_memory: TokenBlocklist
    ) -> None:
        # Logout is idempotent, so this is reachable.
        await in_memory.revoke("jti-1", ttl_seconds=60)
        await in_memory.revoke("jti-1", ttl_seconds=60)

        assert await in_memory.is_revoked("jti-1")


@requires_redis
class TestRedisBlocklist:
    async def test_a_revoked_token_is_reported_as_revoked(
        self, redis_backed: RedisTokenBlocklist
    ) -> None:
        await redis_backed.revoke("jti-1", ttl_seconds=60)

        assert await redis_backed.is_revoked("jti-1")

    async def test_an_unknown_token_is_not_revoked(
        self, redis_backed: RedisTokenBlocklist
    ) -> None:
        assert not await redis_backed.is_revoked("never-seen")

    async def test_the_entry_carries_the_requested_ttl(
        self, redis_backed: RedisTokenBlocklist
    ) -> None:
        # Set atomically with the value rather than by a follow-up
        # EXPIRE: a crash between the two would leave a key with no TTL,
        # blocking a token forever after it had already expired.
        await redis_backed.revoke("jti-ttl", ttl_seconds=120)
        await redis_backed.connect()

        ttl = await redis_backed._client.ttl(  # noqa: SLF001 - asserting storage
            redis_backed._key("jti-ttl")  # noqa: SLF001
        )

        assert 0 < ttl <= 120

    async def test_an_entry_disappears_when_it_expires(
        self, redis_backed: RedisTokenBlocklist
    ) -> None:
        await redis_backed.revoke("jti-brief", ttl_seconds=1)
        assert await redis_backed.is_revoked("jti-brief")

        await asyncio.sleep(1.2)

        assert not await redis_backed.is_revoked("jti-brief")

    async def test_a_second_instance_sees_the_same_revocation(
        self, redis_backed: RedisTokenBlocklist
    ) -> None:
        """The reason this is Redis and not a set in memory.

        Behind a load balancer, a logout handled by one instance has to
        be visible to the others — otherwise the token keeps working on
        every server that did not handle it, which is indistinguishable
        from no revocation at all.
        """
        await redis_backed.revoke("jti-shared", ttl_seconds=60)

        other_instance = RedisTokenBlocklist(
            REDIS_URL, key_prefix=redis_backed._key_prefix  # noqa: SLF001
        )
        try:
            assert await other_instance.is_revoked("jti-shared")
        finally:
            await other_instance.disconnect()

    async def test_an_unreachable_redis_fails_open_by_default(self) -> None:
        # A cache outage must not lock every user out. The window is
        # small, the token still expires on its own, and the failure is
        # logged rather than swallowed.
        broken = RedisTokenBlocklist("redis://127.0.0.1:6390/0")
        try:
            assert not await broken.is_revoked("jti-1")
        finally:
            await broken.disconnect()

    async def test_it_can_be_configured_to_fail_closed(self) -> None:
        # For a deployment that would rather sign everyone out than
        # honour a revoked token during an outage.
        broken = RedisTokenBlocklist("redis://127.0.0.1:6390/0", fail_closed=True)
        try:
            assert await broken.is_revoked("jti-1")
        finally:
            await broken.disconnect()
