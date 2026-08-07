"""Tests for the Chat Engine's SQLAlchemy ORM models (Layer 5)."""
from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory
from src.layer_5_storage.models.message_model import (
    ChatMessageModel,
    ChatParticipantModel,
    ChatThreadModel,
    MessageType,
)


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = build_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = build_session_factory(engine)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


async def test_creates_thread_with_generated_id(session: AsyncSession) -> None:
    thread = ChatThreadModel(title="General")
    session.add(thread)
    await session.commit()

    assert thread.id
    assert thread.max_participants == 200
    assert thread.created_at is not None


async def test_participant_belongs_to_thread(session: AsyncSession) -> None:
    thread = ChatThreadModel()
    session.add(thread)
    await session.flush()

    participant = ChatParticipantModel(thread_id=thread.id, user_id="alice")
    session.add(participant)
    await session.commit()

    result = await session.execute(
        select(ChatParticipantModel).where(ChatParticipantModel.user_id == "alice")
    )
    fetched = result.scalar_one()
    assert fetched.thread_id == thread.id
    assert fetched.left_at is None


async def test_message_persists_with_type_enum(session: AsyncSession) -> None:
    thread = ChatThreadModel()
    session.add(thread)
    await session.flush()

    message = ChatMessageModel(
        thread_id=thread.id,
        sender_id="alice",
        content="hello world",
        type=MessageType.TEXT,
    )
    session.add(message)
    await session.commit()

    result = await session.execute(
        select(ChatMessageModel).where(ChatMessageModel.thread_id == thread.id)
    )
    fetched = result.scalar_one()
    assert fetched.content == "hello world"
    assert fetched.type is MessageType.TEXT


async def test_deleting_thread_cascades_to_participants_and_messages(
    session: AsyncSession,
) -> None:
    thread = ChatThreadModel()
    session.add(thread)
    await session.flush()

    session.add(ChatParticipantModel(thread_id=thread.id, user_id="alice"))
    session.add(
        ChatMessageModel(
            thread_id=thread.id,
            sender_id="alice",
            content="hi",
            type=MessageType.TEXT,
        )
    )
    await session.commit()

    await session.delete(thread)
    await session.commit()

    remaining_participants = await session.execute(select(ChatParticipantModel))
    remaining_messages = await session.execute(select(ChatMessageModel))
    assert remaining_participants.scalars().all() == []
    assert remaining_messages.scalars().all() == []


async def test_thread_uniqueness_constraint_on_participant(
    session: AsyncSession,
) -> None:
    thread = ChatThreadModel()
    session.add(thread)
    await session.flush()

    session.add(ChatParticipantModel(thread_id=thread.id, user_id="alice"))
    await session.commit()

    session.add(ChatParticipantModel(thread_id=thread.id, user_id="alice"))
    with pytest.raises(Exception):  # sqlite IntegrityError
        await session.commit()
