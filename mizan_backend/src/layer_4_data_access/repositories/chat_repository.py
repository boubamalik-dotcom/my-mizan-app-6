"""Layer 4 — abstract persistence contract for the Chat Engine.

This is an *interface* only: it declares the shape of chat
persistence operations in terms of Layer 3 domain objects
(`ChatRoom`, `ChatMessage`), without knowing anything about SQL,
SQLAlchemy, or any specific database. Layer 5
(`layer_5_storage/implementations/chat_repository_impl.py`) provides
the concrete implementation; Layer 2 depends only on this abstraction
(Dependency Inversion Principle), which keeps controllers trivially
testable with an in-memory fake.
"""
from __future__ import annotations

import abc
from typing import List, Optional

from ...layer_3_business.chat.chat_service import ChatMessage, ChatRoom


class ChatRepository(abc.ABC):
    """Persistence contract for chat rooms, participants, and
    messages."""

    @abc.abstractmethod
    async def get_or_create_room(self, room_id: str) -> ChatRoom:
        """Returns the room's current membership state, creating an
        empty room record on first use."""

    @abc.abstractmethod
    async def save_room(self, room: ChatRoom) -> None:
        """Persists membership changes (joins/leaves) made to
        `room`."""

    @abc.abstractmethod
    async def save_message(self, message: ChatMessage) -> None:
        """Durably persists a single chat message."""

    @abc.abstractmethod
    async def get_history(
        self,
        room_id: str,
        *,
        limit: int = 50,
        before_id: Optional[str] = None,
    ) -> List[ChatMessage]:
        """Returns up to `limit` messages for `room_id`, oldest first.

        When `before_id` is provided, only messages sent strictly
        before that message (exclusive) are returned, enabling
        backward pagination through history.
        """
