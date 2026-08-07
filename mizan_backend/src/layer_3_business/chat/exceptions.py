"""Domain-level exceptions for the Chat Engine's business logic (Layer 3).

These exceptions carry no dependency on any web framework, WebSocket
library, or database driver. Layer 2 (`chat_controller.py`) is
responsible for translating them into the appropriate HTTP status code
or WebSocket close/error frame.
"""
from __future__ import annotations


class ChatDomainError(Exception):
    """Base class for every error raised by the chat business logic."""


class InvalidMessageError(ChatDomainError):
    """Raised when a message fails content validation (empty, too
    long, etc.)."""


class RoomFullError(ChatDomainError):
    """Raised when a room has reached its maximum participant
    capacity."""

    def __init__(self, room_id: str, max_participants: int) -> None:
        self.room_id = room_id
        self.max_participants = max_participants
        super().__init__(
            f'Chat room "{room_id}" is full '
            f"(max {max_participants} participants)."
        )


class NotAParticipantError(ChatDomainError):
    """Raised when a user attempts an action in a room they have not
    joined (e.g. sending a message or leaving)."""

    def __init__(self, room_id: str, user_id: str) -> None:
        self.room_id = room_id
        self.user_id = user_id
        super().__init__(
            f'User "{user_id}" is not a participant of room "{room_id}".'
        )


class AlreadyJoinedError(ChatDomainError):
    """Raised when a user attempts to join a room they are already a
    participant of."""

    def __init__(self, room_id: str, user_id: str) -> None:
        self.room_id = room_id
        self.user_id = user_id
        super().__init__(
            f'User "{user_id}" has already joined room "{room_id}".'
        )


class RateLimitExceededError(ChatDomainError):
    """Raised when a participant sends messages faster than the
    configured rate limit allows."""

    def __init__(self, user_id: str, retry_after_seconds: float) -> None:
        self.user_id = user_id
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f'User "{user_id}" is sending messages too quickly; '
            f"retry after {retry_after_seconds:.1f}s."
        )
