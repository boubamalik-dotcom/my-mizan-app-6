"""Tests for `SqlAlchemyChatRepository` (Layer 5), verifying it
correctly maps between ORM rows and Layer 3 domain objects."""
from __future__ import annotations

from typing import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.layer_3_business.chat.chat_service import ChatMessage, ChatRoom, MessageType
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory
from src.layer_5_storage.implementations.chat_repository_impl import (
    SqlAlchemyChatRepository,
)


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker]:
    engine = build_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield build_session_factory(engine)

    await engine.dispose()


@pytest_asyncio.fixture
async def repository(session_factory: async_sessionmaker) -> SqlAlchemyChatRepository:
    return SqlAlchemyChatRepository(session_factory, default_max_participants=5)


async def test_get_or_create_room_creates_empty_room_on_first_use(
    repository: SqlAlchemyChatRepository,
) -> None:
    room = await repository.get_or_create_room("room-1")

    assert isinstance(room, ChatRoom)
    assert room.id == "room-1"
    assert room.participant_ids == set()
    assert room.max_participants == 5


async def test_get_or_create_room_is_idempotent(
    repository: SqlAlchemyChatRepository,
) -> None:
    first = await repository.get_or_create_room("room-1")
    second = await repository.get_or_create_room("room-1")
    assert first.id == second.id


async def test_save_room_persists_joins_and_leaves(
    repository: SqlAlchemyChatRepository,
) -> None:
    room = await repository.get_or_create_room("room-1")
    room.participant_ids.add("alice")
    room.participant_ids.add("bob")
    await repository.save_room(room)

    reloaded = await repository.get_or_create_room("room-1")
    assert reloaded.participant_ids == {"alice", "bob"}

    reloaded.participant_ids.discard("bob")
    await repository.save_room(reloaded)

    final = await repository.get_or_create_room("room-1")
    assert final.participant_ids == {"alice"}


async def test_save_and_retrieve_message_round_trip(
    repository: SqlAlchemyChatRepository,
) -> None:
    from datetime import datetime, timezone

    message = ChatMessage(
        id="msg-1",
        room_id="room-1",
        sender_id="alice",
        content="hello",
        type=MessageType.TEXT,
        created_at=datetime.now(timezone.utc),
    )
    await repository.get_or_create_room("room-1")
    await repository.save_message(message)

    history = await repository.get_history("room-1", limit=10)

    assert len(history) == 1
    assert history[0].id == "msg-1"
    assert history[0].content == "hello"
    assert history[0].type is MessageType.TEXT


async def test_get_history_supports_before_id_pagination(
    repository: SqlAlchemyChatRepository,
) -> None:
    from datetime import datetime, timedelta, timezone

    await repository.get_or_create_room("room-1")
    base_time = datetime.now(timezone.utc)

    for index in range(3):
        await repository.save_message(
            ChatMessage(
                id=f"msg-{index}",
                room_id="room-1",
                sender_id="alice",
                content=f"message {index}",
                type=MessageType.TEXT,
                created_at=base_time + timedelta(seconds=index),
            )
        )

    older_page = await repository.get_history("room-1", limit=10, before_id="msg-2")
    assert [message.id for message in older_page] == ["msg-0", "msg-1"]
