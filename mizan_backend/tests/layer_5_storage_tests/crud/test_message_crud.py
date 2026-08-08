"""Tests for the raw CRUD helpers in `message_crud.py` (Layer 5)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.layer_5_storage.base_model import Base
from src.layer_5_storage.crud import message_crud
from src.layer_5_storage.db_config import build_engine, build_session_factory
from src.layer_5_storage.models.message_model import ChatParticipantModel, MessageType


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = build_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = build_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


async def test_create_and_get_thread(session: AsyncSession) -> None:
    thread = await message_crud.create_thread(session, "room-1", max_participants=10)
    await session.commit()

    fetched = await message_crud.get_thread(session, "room-1")
    assert fetched is not None
    assert fetched.id == thread.id
    assert fetched.max_participants == 10


async def test_get_thread_returns_none_when_missing(session: AsyncSession) -> None:
    assert await message_crud.get_thread(session, "does-not-exist") is None


async def test_add_and_list_active_participants(session: AsyncSession) -> None:
    await message_crud.create_thread(session, "room-1", max_participants=10)
    await message_crud.add_participant(session, "room-1", "alice")
    await message_crud.add_participant(session, "room-1", "bob")
    await session.commit()

    participants = await message_crud.list_active_participants(session, "room-1")
    assert {p.user_id for p in participants} == {"alice", "bob"}


async def test_mark_participant_left_excludes_from_active_list(
    session: AsyncSession,
) -> None:
    await message_crud.create_thread(session, "room-1", max_participants=10)
    await message_crud.add_participant(session, "room-1", "alice")
    await session.commit()

    await message_crud.mark_participant_left(session, "room-1", "alice")
    await session.commit()

    participants = await message_crud.list_active_participants(session, "room-1")
    assert participants == []


async def test_participant_who_left_can_rejoin(session: AsyncSession) -> None:
    """A participant must be able to rejoin a room they left.

    `mark_participant_left` soft-deletes by stamping `left_at`, and
    `(thread_id, user_id)` is unique — so a blind re-INSERT raised
    `IntegrityError`, and the WebSocket route turned that into a `1011`
    close. The effect was that a client could join a room exactly once
    per lifetime: every reconnect after the first disconnect failed.
    """
    await message_crud.create_thread(session, "room-1", max_participants=10)
    await message_crud.add_participant(session, "room-1", "alice")
    await session.commit()

    await message_crud.mark_participant_left(session, "room-1", "alice")
    await session.commit()
    assert await message_crud.list_active_participants(session, "room-1") == []

    await message_crud.add_participant(session, "room-1", "alice")
    await session.commit()

    participants = await message_crud.list_active_participants(session, "room-1")
    assert [p.user_id for p in participants] == ["alice"]
    # Revived in place rather than duplicated.
    assert participants[0].left_at is None


async def test_rejoining_does_not_duplicate_the_participant_row(
    session: AsyncSession,
) -> None:
    await message_crud.create_thread(session, "room-1", max_participants=10)

    for _ in range(3):
        await message_crud.add_participant(session, "room-1", "alice")
        await session.commit()
        await message_crud.mark_participant_left(session, "room-1", "alice")
        await session.commit()

    await message_crud.add_participant(session, "room-1", "alice")
    await session.commit()

    result = await session.execute(
        select(ChatParticipantModel).where(
            ChatParticipantModel.thread_id == "room-1",
            ChatParticipantModel.user_id == "alice",
        )
    )
    assert len(result.scalars().all()) == 1


async def test_add_participant_is_idempotent_while_still_joined(
    session: AsyncSession,
) -> None:
    # `ChatController.connect_client` relies on this for reconnects.
    await message_crud.create_thread(session, "room-1", max_participants=10)
    await message_crud.add_participant(session, "room-1", "alice")
    await message_crud.add_participant(session, "room-1", "alice")
    await session.commit()

    participants = await message_crud.list_active_participants(session, "room-1")
    assert [p.user_id for p in participants] == ["alice"]


async def test_create_message_and_get_history_in_chronological_order(
    session: AsyncSession,
) -> None:
    await message_crud.create_thread(session, "room-1", max_participants=10)
    base_time = datetime.now(timezone.utc)

    for index in range(3):
        await message_crud.create_message(
            session,
            id=f"msg-{index}",
            thread_id="room-1",
            sender_id="alice",
            content=f"message {index}",
            type=MessageType.TEXT,
            created_at=base_time + timedelta(seconds=index),
        )
    await session.commit()

    history = await message_crud.get_history(session, "room-1", limit=10)
    assert [message.id for message in history] == ["msg-0", "msg-1", "msg-2"]


async def test_get_history_respects_limit_and_returns_most_recent(
    session: AsyncSession,
) -> None:
    await message_crud.create_thread(session, "room-1", max_participants=10)
    base_time = datetime.now(timezone.utc)

    for index in range(5):
        await message_crud.create_message(
            session,
            id=f"msg-{index}",
            thread_id="room-1",
            sender_id="alice",
            content=f"message {index}",
            type=MessageType.TEXT,
            created_at=base_time + timedelta(seconds=index),
        )
    await session.commit()

    history = await message_crud.get_history(session, "room-1", limit=2)
    assert [message.id for message in history] == ["msg-3", "msg-4"]


async def test_get_history_before_created_at_paginates_backward(
    session: AsyncSession,
) -> None:
    await message_crud.create_thread(session, "room-1", max_participants=10)
    base_time = datetime.now(timezone.utc)

    for index in range(4):
        await message_crud.create_message(
            session,
            id=f"msg-{index}",
            thread_id="room-1",
            sender_id="alice",
            content=f"message {index}",
            type=MessageType.TEXT,
            created_at=base_time + timedelta(seconds=index),
        )
    await session.commit()

    older_page = await message_crud.get_history(
        session,
        "room-1",
        limit=10,
        before_created_at=base_time + timedelta(seconds=2),
    )
    assert [message.id for message in older_page] == ["msg-0", "msg-1"]
