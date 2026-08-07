"""Tests for the abstract `ChatRepository` contract (Layer 4)."""
from __future__ import annotations

import pytest

from src.layer_4_data_access.repositories.chat_repository import ChatRepository


def test_cannot_instantiate_abstract_repository() -> None:
    with pytest.raises(TypeError):
        ChatRepository()  # type: ignore[abstract]


def test_subclass_missing_methods_cannot_be_instantiated() -> None:
    class IncompleteRepository(ChatRepository):
        async def get_or_create_room(self, room_id: str):  # type: ignore[override]
            raise NotImplementedError

    with pytest.raises(TypeError):
        IncompleteRepository()  # type: ignore[abstract]


def test_full_implementation_can_be_instantiated() -> None:
    class FakeChatRepository(ChatRepository):
        async def get_or_create_room(self, room_id: str):  # type: ignore[override]
            raise NotImplementedError

        async def save_room(self, room) -> None:  # type: ignore[override]
            raise NotImplementedError

        async def save_message(self, message) -> None:  # type: ignore[override]
            raise NotImplementedError

        async def get_history(self, room_id: str, *, limit: int = 50, before_id=None):  # type: ignore[override]
            raise NotImplementedError

    # Should not raise.
    FakeChatRepository()
