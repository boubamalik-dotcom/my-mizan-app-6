"""Layer 4 — the store behind token revocation.

## Why this is Layer 4 and not Layer 3

Revocation is naturally described as an `AuthService` concern, but the
*store* is Redis, and Layer 3 may not import a driver — it is pure
Python by rule, and `tests/test_layer_isolation.py` enforces it. So the
work is split where the layering already puts it:

* **Layer 3** decides the pure parts: minting a `jti` per token and
  computing how long a revocation needs to last
  (`TokenPayload.seconds_until_expiry`).
* **Layer 4** (here) stores it.
* **Layer 2** (`AuthController`) joins the two, exactly as it already
  joins `AuthService` to `UserRepository`.

## What is stored

Only the token's `jti` — never the token. A blocklist holding whole
tokens would be a database of live credentials, so anyone who read it
could impersonate every user who had merely *logged out*.

Each entry expires with the token it blocks. A revoked token is refused
on its own `exp` claim once expired, so keeping the entry beyond that
would spend memory forever to block something already dead. This is
what keeps the blocklist bounded by the number of *active* sessions
rather than by every logout that ever happened.
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)

#: Key prefix, so the blocklist is distinguishable from anything else
#: sharing the Redis instance.
DEFAULT_KEY_PREFIX = "auth:revoked:"


class TokenBlocklist(ABC):
    """Records which access tokens have been revoked."""

    @abstractmethod
    async def revoke(self, token_id: str, *, ttl_seconds: int) -> None:
        """Blocks `token_id` for `ttl_seconds`.

        A `ttl_seconds` of zero or less is a no-op: the token has
        already expired and is refused on its `exp` claim anyway.
        """

    @abstractmethod
    async def is_revoked(self, token_id: str) -> bool:
        """Whether `token_id` has been revoked and not yet expired."""


class RedisTokenBlocklist(TokenBlocklist):
    """Redis-backed blocklist, shared across every server instance.

    Cross-instance is the point: an in-process set would let a logged-out
    token keep working on whichever instance did not handle the logout,
    which is indistinguishable from no revocation at all under a load
    balancer.
    """

    def __init__(
        self,
        redis_url: str,
        *,
        key_prefix: str = DEFAULT_KEY_PREFIX,
        fail_closed: bool = False,
    ) -> None:
        """
        Args:
            redis_url: Connection URL, from `config.Settings.redis_url`.
            key_prefix: Namespace for this blocklist's keys.
            fail_closed: What to do when Redis is unreachable during a
                revocation check. `False` (the default) admits the
                request and logs loudly; `True` rejects it.

                Neither answer is comfortable, which is why it is a
                decision the deployment makes rather than one hidden
                here. Failing open means a logged-out token works during
                an outage; failing closed means a Redis outage logs out
                every user at once. The default favours availability,
                on the grounds that the window is small and the token
                still expires on its own.
        """
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._fail_closed = fail_closed
        self._client: Optional[redis.Redis] = None

    async def connect(self) -> None:
        """Opens the connection. Idempotent."""
        if self._client is not None:
            return
        self._client = redis.from_url(self._redis_url, decode_responses=True)

    async def disconnect(self) -> None:
        """Closes the connection, if one is open."""
        client = self._client
        self._client = None
        if client is not None:
            await client.aclose()

    def _key(self, token_id: str) -> str:
        return f"{self._key_prefix}{token_id}"

    async def revoke(self, token_id: str, *, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        await self.connect()
        assert self._client is not None
        # SET with an expiry rather than SET + EXPIRE: one round trip,
        # and no window in which a key exists without a TTL and would
        # outlive the token forever if the process died between them.
        await self._client.set(self._key(token_id), "1", ex=ttl_seconds)

    async def is_revoked(self, token_id: str) -> bool:
        try:
            await self.connect()
            assert self._client is not None
            return await self._client.exists(self._key(token_id)) > 0
        except Exception:  # noqa: BLE001 - an outage must not 500 every request
            logger.exception(
                "Token blocklist unreachable; %s this request.",
                "rejecting" if self._fail_closed else "allowing",
            )
            return self._fail_closed


class InMemoryTokenBlocklist(TokenBlocklist):
    """Process-local blocklist, for tests and single-process local runs.

    Correct only for one process. Deliberately not the production
    default: under more than one instance it silently stops revoking
    anything that was logged out elsewhere.
    """

    def __init__(self) -> None:
        self._expiries: Dict[str, float] = {}

    async def revoke(self, token_id: str, *, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        self._expiries[token_id] = time.monotonic() + ttl_seconds

    async def is_revoked(self, token_id: str) -> bool:
        expires_at = self._expiries.get(token_id)
        if expires_at is None:
            return False
        if expires_at <= time.monotonic():
            # Expired entries are dropped lazily; nothing here runs on a
            # timer.
            del self._expiries[token_id]
            return False
        return True
