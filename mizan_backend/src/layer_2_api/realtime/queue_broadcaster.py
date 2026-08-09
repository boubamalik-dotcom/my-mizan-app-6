"""Layer 2 — real-time fan-out for Mizan Door's clinic queues.

Bridges the same two pieces the Chat Engine uses, for a different
subject:

* `ConnectionManager` holds the WebSockets *this* process has open, one
  registry keyed by clinic.
* `MessageBroker` (Layer 4, Redis pub/sub) carries an update to every
  other process, so a patient connected to worker A still sees a queue
  advanced by a receptionist whose request landed on worker B. Without
  it the feature would appear to work in development — one worker — and
  silently half-fail in production.

**What is broadcast, and what is deliberately not.** The payload carries
a clinic's *aggregate* state only: how many are waiting, which ticket is
being served, whether the clinic is admitting. No names, no user ids, no
reservation ids — nothing that identifies a patient. This is exactly the
information `GET /api/v1/queues` already serves, so subscribing reveals
nothing a client could not already read.

That restraint is the whole design. A queue update is tempting to send
as "here is the full queue with everyone in it", and an earlier
standalone implementation of this feature did precisely that — it
streamed patient names and phone numbers, live, to anyone who opened the
socket, at a clinic whose specialty implied why they were attending. A
client that needs its *own* position asks for it over authenticated
REST; the socket only ever says "this clinic's queue moved".
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Mapping, Optional

from fastapi import WebSocket

from ...layer_4_data_access.events.message_broker import (
    MessageBroker,
    MessageBrokerError,
)
from ...layer_4_data_access.repositories.queue_repository import ClinicQueueRecord
from .connection_manager import ConnectionManager

logger = logging.getLogger(__name__)

#: Prefix for the broker channel a clinic's updates travel on. Keeps
#: queue traffic in its own namespace so it can never collide with a
#: chat room id, which shares the same broker.
CHANNEL_PREFIX = "queue"

#: The single event this feature publishes. Named in the payload rather
#: than implied, so a client can ignore anything it does not recognise
#: and a second event type can be added later without ambiguity.
EVENT_QUEUE_UPDATED = "queue_updated"


def channel_for(clinic_id: str) -> str:
    """The broker channel carrying `clinic_id`'s queue updates."""
    return f"{CHANNEL_PREFIX}:{clinic_id}"


def queue_state_payload(queue: ClinicQueueRecord) -> Dict[str, Any]:
    """Builds the wire payload for a clinic's queue state.

    Mirrors `ClinicQueueResponse` field for field, so a client can
    apply a socket update to a card it originally rendered from
    `GET /queues` without a second mapping that could drift from the
    first.

    Contains no patient-identifying information; see the module
    docstring for why that is a rule rather than an oversight.
    """
    return {
        "event": EVENT_QUEUE_UPDATED,
        "clinic_id": queue.id,
        "waiting_count": queue.waiting_count,
        "now_serving_ticket": queue.now_serving_ticket,
        "is_accepting_patients": queue.is_accepting_patients,
        "average_service_minutes": queue.service_rate_minutes,
        "estimated_wait_minutes": queue.waiting_count * queue.service_rate_minutes,
    }


class QueueBroadcaster:
    """Publishes clinic queue updates and delivers them to subscribed
    WebSockets."""

    def __init__(
        self,
        *,
        broker: MessageBroker,
        connection_manager: Optional[ConnectionManager] = None,
    ) -> None:
        """
        Args:
            broker: The Layer 4 pub/sub broker used to reach other
                processes.
            connection_manager: Registry of this process's open
                sockets. Its own by default; injectable for tests.
        """
        self._broker = broker
        self._connections = connection_manager or ConnectionManager()
        self._relay_tasks: Dict[str, asyncio.Task[None]] = {}
        self._relay_lock = asyncio.Lock()

    # -- Publishing ------------------------------------------------------

    async def publish_queue_state(self, queue: ClinicQueueRecord) -> None:
        """Announces `queue`'s current state to every subscriber, in
        this process and every other.

        **Never raises.** A broadcast is a courtesy on top of a write
        that has already been committed: if Redis is down, the patient
        who just joined must still get their ticket and a 201, and
        everyone else finds out on their next refresh. Letting a
        messaging failure surface as a failed reservation would trade a
        degraded feature for a broken one.
        """
        try:
            await self._broker.publish(channel_for(queue.id), queue_state_payload(queue))
        except MessageBrokerError:
            logger.warning(
                "Could not broadcast the queue update for clinic %s; "
                "subscribers will see it on their next refresh.",
                queue.id,
                exc_info=True,
            )
        except Exception:  # noqa: BLE001 - a broadcast must never fail a write
            logger.exception(
                "Unexpected failure broadcasting the queue update for clinic %s",
                queue.id,
            )

    # -- Subscribing -----------------------------------------------------

    async def connect(
        self, *, clinic_id: str, client_id: str, websocket: WebSocket
    ) -> None:
        """Accepts `websocket` and subscribes it to `clinic_id`'s
        updates, starting this process's relay for that clinic if it is
        the first connection to it."""
        await self._connections.connect(clinic_id, client_id, websocket)
        await self._ensure_relay_task(clinic_id)

    async def disconnect(self, *, clinic_id: str, client_id: str) -> None:
        """Unregisters a socket, and stops the clinic's relay once the
        last local subscriber for it has gone.

        Stopping matters: a relay left running holds a Redis
        subscription open forever, so a server that had briefly seen a
        connection for every clinic would keep subscriptions for all of
        them for the rest of its life.
        """
        await self._connections.disconnect(clinic_id, client_id)
        if self._connections.has_local_connections(clinic_id):
            return

        async with self._relay_lock:
            task = self._relay_tasks.pop(clinic_id, None)
        if task is not None:
            task.cancel()

    async def _ensure_relay_task(self, clinic_id: str) -> None:
        """Starts the Redis→WebSocket relay for `clinic_id` unless one
        is already running, so N connections to one clinic share a
        single subscription."""
        async with self._relay_lock:
            existing = self._relay_tasks.get(clinic_id)
            if existing is not None and not existing.done():
                return
            self._relay_tasks[clinic_id] = asyncio.create_task(
                self._relay_loop(clinic_id), name=f"queue-relay-{clinic_id}"
            )

    async def _relay_loop(self, clinic_id: str) -> None:
        """Forwards everything published for `clinic_id` to the sockets
        this process holds for it."""
        try:
            async with self._broker.subscribe(channel_for(clinic_id)) as updates:
                async for payload in updates:
                    await self._connections.broadcast_local(
                        clinic_id, dict(payload)
                    )
        except asyncio.CancelledError:
            raise
        except MessageBrokerError:
            logger.exception(
                "Queue relay for clinic %s stopped unexpectedly", clinic_id
            )

    async def broadcast_local(
        self, clinic_id: str, payload: Mapping[str, Any]
    ) -> None:
        """Sends `payload` straight to this process's sockets, skipping
        the broker. For tests; production always goes through
        `publish_queue_state` so other processes see it too."""
        await self._connections.broadcast_local(clinic_id, dict(payload))

    async def shutdown(self) -> None:
        """Cancels every relay task. Call during application shutdown,
        before the broker itself is disconnected."""
        tasks = list(self._relay_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._relay_tasks.clear()
