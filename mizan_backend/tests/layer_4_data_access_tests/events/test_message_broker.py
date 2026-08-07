"""Integration tests for `RedisMessageBroker` (Layer 4) against a real
local Redis instance.

These tests are skipped automatically if no Redis server is reachable
at `REDIS_URL` (default `redis://localhost:6379/0`), so the suite
still runs in environments without Redis installed.
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest
import pytest_asyncio
import redis.asyncio as redis

from src.layer_4_data_access.events.message_broker import (
    MessageBrokerError,
    RedisMessageBroker,
)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


async def _redis_available() -> bool:
    try:
        client = redis.from_url(REDIS_URL)
        await asyncio.wait_for(client.ping(), timeout=1.0)
        await client.aclose()
        return True
    except Exception:
        return False


requires_redis = pytest.mark.skipif(
    not asyncio.run(_redis_available()), reason="No Redis server reachable for integration test."
)


@pytest_asyncio.fixture
async def broker():
    instance = RedisMessageBroker(REDIS_URL, channel_prefix=f"test:{uuid.uuid4()}:")
    await instance.connect()
    yield instance
    await instance.disconnect()


@requires_redis
async def test_connect_sets_is_connected(broker: RedisMessageBroker) -> None:
    assert broker.is_connected


@requires_redis
async def test_publish_without_connect_raises() -> None:
    disconnected_broker = RedisMessageBroker(REDIS_URL)
    with pytest.raises(MessageBrokerError):
        await disconnected_broker.publish("room-1", {"hello": "world"})


@requires_redis
async def test_connect_to_unreachable_redis_raises() -> None:
    unreachable_broker = RedisMessageBroker(
        "redis://127.0.0.1:1", connect_timeout_seconds=1.0
    )
    with pytest.raises(MessageBrokerError):
        await unreachable_broker.connect()


@requires_redis
async def test_publish_then_subscribe_round_trip(broker: RedisMessageBroker) -> None:
    room_id = "room-round-trip"
    received: list[dict] = []

    async def subscriber() -> None:
        async with broker.subscribe(room_id) as messages:
            async for payload in messages:
                received.append(payload)
                break

    subscriber_task = asyncio.create_task(subscriber())
    await asyncio.sleep(0.2)  # let the subscription register before publishing

    await broker.publish(room_id, {"id": "msg-1", "content": "hello"})
    await asyncio.wait_for(subscriber_task, timeout=5.0)

    assert received == [{"id": "msg-1", "content": "hello"}]


@requires_redis
async def test_subscribers_are_isolated_per_room(broker: RedisMessageBroker) -> None:
    received_a: list[dict] = []
    received_b: list[dict] = []

    async def subscribe_and_collect(room_id: str, sink: list[dict]) -> None:
        async with broker.subscribe(room_id) as messages:
            async for payload in messages:
                sink.append(payload)
                break

    task_a = asyncio.create_task(subscribe_and_collect("room-a", received_a))
    task_b = asyncio.create_task(subscribe_and_collect("room-b", received_b))
    await asyncio.sleep(0.2)

    await broker.publish("room-a", {"content": "only for A"})
    await asyncio.wait_for(task_a, timeout=5.0)

    assert received_a == [{"content": "only for A"}]
    assert received_b == []

    task_b.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task_b


@requires_redis
async def test_publish_rejects_non_json_serializable_payload(
    broker: RedisMessageBroker,
) -> None:
    with pytest.raises(MessageBrokerError):
        await broker.publish("room-1", {"bad": object()})
