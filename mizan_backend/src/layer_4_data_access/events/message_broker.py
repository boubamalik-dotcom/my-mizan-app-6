"""Layer 4 — asynchronous Redis Pub/Sub interface for real-time chat
broadcasting.

Lets multiple FastAPI server instances (processes/pods) share chat
events: whichever instance holds a given user's WebSocket connection
subscribes to that room's Redis channel, while any instance that
receives a message from one of its own clients publishes it exactly
once — every subscribed instance (including the publisher) then
rebroadcasts it locally to its own connected WebSocket clients.

STRICT RULE: this module abstracts Layer 5 storage details away from
Layer 2 — the controller only ever talks to the `MessageBroker`
interface, never to `redis.asyncio` directly, so the transport could
be swapped for another pub/sub backend (or an in-memory fake for
tests) without touching Layer 2 or Layer 3.
"""
from __future__ import annotations

import abc
import asyncio
import contextlib
import json
import logging
from typing import Any, AsyncIterator, Mapping

import redis.asyncio as redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

DEFAULT_CHANNEL_PREFIX = "mizan:chat:room:"
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0


class MessageBrokerError(Exception):
    """Raised when the broker cannot publish/subscribe due to an
    underlying transport failure (connection loss, serialization
    error, etc.). Layer 2 is responsible for deciding how to surface
    this to the client."""


class MessageBroker(abc.ABC):
    """Abstract Pub/Sub contract that Layer 2 depends on, so it never
    needs to know it is talking to Redis specifically (Dependency
    Inversion Principle — a fake/in-memory broker can be substituted
    in unit tests without any Redis server running)."""

    @abc.abstractmethod
    async def connect(self) -> None:
        """Establishes the underlying connection. Safe to call more
        than once; subsequent calls are no-ops while connected."""

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Releases the underlying connection. Safe to call even if
        never connected."""

    @abc.abstractmethod
    async def publish(self, room_id: str, payload: Mapping[str, Any]) -> None:
        """Publishes `payload` to every subscriber of `room_id`,
        across every connected server instance."""

    @abc.abstractmethod
    def subscribe(
        self, room_id: str
    ) -> contextlib.AbstractAsyncContextManager[AsyncIterator[Mapping[str, Any]]]:
        """Returns an async context manager yielding an async iterator
        of decoded payloads published to `room_id`.

        Usage::

            async with broker.subscribe(room_id) as messages:
                async for payload in messages:
                    ...
        """


class RedisMessageBroker(MessageBroker):
    """`redis.asyncio`-backed implementation of `MessageBroker`."""

    def __init__(
        self,
        redis_url: str,
        *,
        channel_prefix: str = DEFAULT_CHANNEL_PREFIX,
        connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    ) -> None:
        self._redis_url = redis_url
        self._channel_prefix = channel_prefix
        self._connect_timeout_seconds = connect_timeout_seconds
        self._client: "redis.Redis | None" = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    async def connect(self) -> None:
        if self._client is not None:
            return

        client = redis.from_url(self._redis_url, decode_responses=True)
        try:
            await asyncio.wait_for(
                client.ping(), timeout=self._connect_timeout_seconds
            )
        except (RedisError, asyncio.TimeoutError, OSError) as exc:
            await client.aclose()
            raise MessageBrokerError(
                f'Could not connect to Redis at "{self._redis_url}": {exc}'
            ) from exc

        self._client = client
        logger.info("Connected to Redis message broker at %s", self._redis_url)

    async def disconnect(self) -> None:
        if self._client is None:
            return
        with contextlib.suppress(RedisError):
            await self._client.aclose()
        self._client = None
        logger.info("Disconnected from Redis message broker.")

    async def publish(self, room_id: str, payload: Mapping[str, Any]) -> None:
        client = self._require_client()
        channel = self._channel_name(room_id)
        try:
            serialized = json.dumps(payload)
        except (TypeError, ValueError) as exc:
            raise MessageBrokerError(
                f"Message payload is not JSON-serializable: {exc}"
            ) from exc

        try:
            await client.publish(channel, serialized)
        except RedisError as exc:
            raise MessageBrokerError(
                f'Failed to publish to channel "{channel}": {exc}'
            ) from exc

    @contextlib.asynccontextmanager
    async def subscribe(
        self, room_id: str
    ) -> AsyncIterator[AsyncIterator[Mapping[str, Any]]]:
        client = self._require_client()
        channel = self._channel_name(room_id)
        pubsub = client.pubsub()

        try:
            await pubsub.subscribe(channel)
        except RedisError as exc:
            with contextlib.suppress(RedisError):
                await pubsub.aclose()
            raise MessageBrokerError(
                f'Failed to subscribe to channel "{channel}": {exc}'
            ) from exc

        try:
            yield self._listen(pubsub, channel)
        finally:
            with contextlib.suppress(RedisError):
                await pubsub.unsubscribe(channel)
            with contextlib.suppress(RedisError):
                await pubsub.aclose()

    async def _listen(
        self, pubsub: "redis.client.PubSub", channel: str
    ) -> AsyncIterator[Mapping[str, Any]]:
        try:
            async for raw_message in pubsub.listen():
                if raw_message is None or raw_message.get("type") != "message":
                    continue

                data = raw_message.get("data")
                try:
                    yield json.loads(data)
                except (TypeError, ValueError):
                    logger.warning(
                        "Discarding malformed payload on channel %s", channel
                    )
        except RedisError as exc:
            raise MessageBrokerError(
                f'Lost connection while listening on channel "{channel}": {exc}'
            ) from exc

    def _channel_name(self, room_id: str) -> str:
        return f"{self._channel_prefix}{room_id}"

    def _require_client(self) -> "redis.Redis":
        if self._client is None:
            raise MessageBrokerError(
                "RedisMessageBroker.connect() must be awaited before use."
            )
        return self._client
