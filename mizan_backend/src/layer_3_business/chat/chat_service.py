"""Layer 3 — pure business logic for the Chat Engine.

STRICT RULE: this module must never import FastAPI, Starlette,
WebSocket, SQLAlchemy, Redis, or any other web-framework / I/O
package. It only operates on plain Python data structures so it can be
unit tested in total isolation and reused unchanged behind any
transport (REST, WebSocket, gRPC, a CLI, a batch job, ...).

Layer 2 owns fetching persisted state (rooms, message history) from
Layers 4/5 and handing it to this service as plain arguments; this
service never reaches out to a database, cache, or network itself.
"""
from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Deque, Dict, Iterable, List, Optional, Set

from .exceptions import (
    AlreadyJoinedError,
    InvalidMessageError,
    NotAParticipantError,
    RateLimitExceededError,
    RoomFullError,
)

MAX_MESSAGE_LENGTH = 4000
MIN_MESSAGE_LENGTH = 1
DEFAULT_MAX_PARTICIPANTS = 200
DEFAULT_RATE_LIMIT_MESSAGES = 10
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 10.0


class MessageType(str, Enum):
    """Kinds of events that can flow through a chat room."""

    TEXT = "text"
    SYSTEM = "system"
    JOIN = "join"
    LEAVE = "leave"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """An immutable, fully-validated chat message ready to be
    persisted (Layer 5) and broadcast (Layer 4)."""

    id: str
    room_id: str
    sender_id: str
    content: str
    type: MessageType
    created_at: datetime

    def to_dict(self) -> Dict[str, object]:
        """Plain-dict representation, safe to JSON-serialize for
        broadcasting or API responses."""
        return {
            "id": self.id,
            "room_id": self.room_id,
            "sender_id": self.sender_id,
            "content": self.content,
            "type": self.type.value,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(slots=True)
class ChatRoom:
    """In-memory representation of a chat room's current membership.

    Layer 2 loads this from persistence (Layers 4/5) before calling
    into the service, and saves the mutated result back afterwards —
    this class itself never touches storage.
    """

    id: str
    participant_ids: Set[str] = field(default_factory=set)
    max_participants: int = DEFAULT_MAX_PARTICIPANTS

    def has_participant(self, user_id: str) -> bool:
        return user_id in self.participant_ids

    @property
    def participant_count(self) -> int:
        return len(self.participant_ids)

    @property
    def is_full(self) -> bool:
        return self.participant_count >= self.max_participants


@dataclass(frozen=True, slots=True)
class ChatSession:
    """A single user's active membership window in a room, independent
    of any specific network connection/transport (a user could
    reconnect over a new WebSocket without starting a new session)."""

    room_id: str
    user_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    def close(self, *, at: Optional[datetime] = None) -> "ChatSession":
        """Returns a closed copy of this session. A no-op if the
        session is already closed."""
        if not self.is_active:
            return self
        return ChatSession(
            room_id=self.room_id,
            user_id=self.user_id,
            started_at=self.started_at,
            ended_at=at or datetime.now(timezone.utc),
        )


class MessageRateLimiter:
    """Simple in-memory sliding-window rate limiter.

    Pure Python, no external dependency — enforces a "chat rule" such
    as "at most N messages per M seconds per user" to curb spam and
    flooding. Not distributed: for multi-instance deployments, Layer 4
    may back this with a shared store (e.g. Redis), but the *rule
    itself* (the algorithm) belongs here, in Layer 3, so it stays
    100% unit-testable.
    """

    def __init__(
        self,
        *,
        max_messages: int = DEFAULT_RATE_LIMIT_MESSAGES,
        window_seconds: float = DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
    ) -> None:
        if max_messages <= 0:
            raise ValueError("max_messages must be positive.")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive.")
        self._max_messages = max_messages
        self._window_seconds = window_seconds
        self._history: Dict[str, Deque[float]] = {}

    def check(self, user_id: str, *, now: Optional[float] = None) -> None:
        """Raises `RateLimitExceededError` if `user_id` has exceeded
        the allowed message rate; otherwise records this attempt."""
        current_time = time.monotonic() if now is None else now
        timestamps = self._history.setdefault(user_id, deque())

        cutoff = current_time - self._window_seconds
        while timestamps and timestamps[0] <= cutoff:
            timestamps.popleft()

        if len(timestamps) >= self._max_messages:
            retry_after = self._window_seconds - (current_time - timestamps[0])
            raise RateLimitExceededError(user_id, max(retry_after, 0.0))

        timestamps.append(current_time)

    def reset(self, user_id: str) -> None:
        """Clears rate-limit history for a user, e.g. once they leave
        a room."""
        self._history.pop(user_id, None)


class ChatService:
    """Pure business logic for the Chat Engine: message validation,
    room/session management, and chat rules (rate limiting).

    Every method is a deterministic transformation over plain
    arguments and return values — the only internal state is the
    optional in-memory rate limiter, and even that holds no
    persistence-layer objects. No network or disk I/O of any kind.
    """

    def __init__(
        self,
        *,
        max_message_length: int = MAX_MESSAGE_LENGTH,
        min_message_length: int = MIN_MESSAGE_LENGTH,
        rate_limiter: Optional[MessageRateLimiter] = None,
    ) -> None:
        self._max_message_length = max_message_length
        self._min_message_length = min_message_length
        self._rate_limiter = rate_limiter or MessageRateLimiter()

    # -- Message validation & composition -----------------------------

    def validate_message_content(self, content: Optional[str]) -> str:
        """Normalizes and validates raw message text, returning the
        sanitized content. Raises `InvalidMessageError` on failure."""
        if content is None:
            raise InvalidMessageError("Message content is required.")

        normalized = content.strip()
        if len(normalized) < self._min_message_length:
            raise InvalidMessageError("Message content cannot be empty.")
        if len(normalized) > self._max_message_length:
            raise InvalidMessageError(
                "Message content exceeds the "
                f"{self._max_message_length}-character limit."
            )
        return normalized

    def compose_message(
        self,
        *,
        room: ChatRoom,
        sender_id: str,
        content: Optional[str],
        message_type: MessageType = MessageType.TEXT,
    ) -> ChatMessage:
        """Validates a would-be message against room membership, rate
        limits, and content rules, returning a ready-to-persist
        `ChatMessage`.

        Raises a `ChatDomainError` subclass on any rule violation:
        `NotAParticipantError`, `RateLimitExceededError`, or
        `InvalidMessageError`.
        """
        if not room.has_participant(sender_id):
            raise NotAParticipantError(room.id, sender_id)

        if message_type is MessageType.TEXT:
            self._rate_limiter.check(sender_id)

        sanitized_content = self.validate_message_content(content)

        return ChatMessage(
            id=str(uuid.uuid4()),
            room_id=room.id,
            sender_id=sender_id,
            content=sanitized_content,
            type=message_type,
            created_at=datetime.now(timezone.utc),
        )

    def build_system_message(
        self,
        *,
        room_id: str,
        content: str,
        message_type: MessageType,
    ) -> ChatMessage:
        """Builds a server-generated notice (e.g. "Alice joined") that
        bypasses membership/rate-limit checks since it does not
        originate from a participant."""
        return ChatMessage(
            id=str(uuid.uuid4()),
            room_id=room_id,
            sender_id="system",
            content=content,
            type=message_type,
            created_at=datetime.now(timezone.utc),
        )

    # -- Room / membership management ----------------------------------

    def join_room(self, room: ChatRoom, user_id: str) -> ChatRoom:
        """Adds `user_id` to `room`, enforcing the "no duplicate join"
        and "room capacity" rules. Mutates and returns `room`."""
        if room.has_participant(user_id):
            raise AlreadyJoinedError(room.id, user_id)
        if room.is_full:
            raise RoomFullError(room.id, room.max_participants)

        room.participant_ids.add(user_id)
        return room

    def leave_room(self, room: ChatRoom, user_id: str) -> ChatRoom:
        """Removes `user_id` from `room` and clears their rate-limit
        history. Mutates and returns `room`."""
        if not room.has_participant(user_id):
            raise NotAParticipantError(room.id, user_id)

        room.participant_ids.discard(user_id)
        self._rate_limiter.reset(user_id)
        return room

    # -- Session management ---------------------------------------------

    def start_session(self, *, room_id: str, user_id: str) -> ChatSession:
        """Starts a new, open-ended chat session for `user_id` in
        `room_id`."""
        return ChatSession(
            room_id=room_id,
            user_id=user_id,
            started_at=datetime.now(timezone.utc),
        )

    def end_session(self, session: ChatSession) -> ChatSession:
        """Closes `session`, returning the closed copy."""
        return session.close()

    # -- History presentation rules ---------------------------------------

    def build_history_page(
        self,
        messages: Iterable[ChatMessage],
        *,
        limit: int,
    ) -> List[ChatMessage]:
        """Applies pure ordering/pagination rules on top of whatever
        Layers 4/5 already fetched, keeping presentation-order
        decisions inside the business layer rather than duplicated
        across controllers."""
        ordered = sorted(messages, key=lambda message: message.created_at)
        if limit <= 0:
            return ordered
        return ordered[-limit:]
