"""Layer 5 — raw CRUD operations for chat persistence.

No business rules live here; `chat_repository_impl.py` maps between
these rows and Layer 3 domain objects. Every function takes an
already-open `AsyncSession` and leaves committing/rolling back the
transaction to its caller, keeping transaction-boundary decisions in
one place (the repository implementation).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.message_model import (
    ChatMessageModel,
    ChatParticipantModel,
    ChatThreadModel,
    MessageType,
)


async def get_thread(
    session: AsyncSession, thread_id: str
) -> Optional[ChatThreadModel]:
    return await session.get(ChatThreadModel, thread_id)


async def create_thread(
    session: AsyncSession, thread_id: str, *, max_participants: int
) -> ChatThreadModel:
    thread = ChatThreadModel(id=thread_id, max_participants=max_participants)
    session.add(thread)
    await session.flush()
    return thread


async def list_active_participants(
    session: AsyncSession, thread_id: str
) -> Sequence[ChatParticipantModel]:
    statement = select(ChatParticipantModel).where(
        ChatParticipantModel.thread_id == thread_id,
        ChatParticipantModel.left_at.is_(None),
    )
    result = await session.execute(statement)
    return result.scalars().all()


async def add_participant(
    session: AsyncSession, thread_id: str, user_id: str
) -> ChatParticipantModel:
    participant = ChatParticipantModel(thread_id=thread_id, user_id=user_id)
    session.add(participant)
    await session.flush()
    return participant


async def mark_participant_left(
    session: AsyncSession, thread_id: str, user_id: str
) -> None:
    statement = select(ChatParticipantModel).where(
        ChatParticipantModel.thread_id == thread_id,
        ChatParticipantModel.user_id == user_id,
        ChatParticipantModel.left_at.is_(None),
    )
    result = await session.execute(statement)
    participant = result.scalar_one_or_none()
    if participant is not None:
        participant.left_at = datetime.now(timezone.utc)


async def create_message(
    session: AsyncSession,
    *,
    id: str,
    thread_id: str,
    sender_id: str,
    content: str,
    type: MessageType,
    created_at: Optional[datetime] = None,
) -> ChatMessageModel:
    message = ChatMessageModel(
        id=id,
        thread_id=thread_id,
        sender_id=sender_id,
        content=content,
        type=type,
        **({"created_at": created_at} if created_at is not None else {}),
    )
    session.add(message)
    await session.flush()
    return message


async def get_history(
    session: AsyncSession,
    thread_id: str,
    *,
    limit: int,
    before_created_at: Optional[datetime] = None,
) -> Sequence[ChatMessageModel]:
    """Returns up to `limit` messages for `thread_id`, oldest first.

    Fetches the most recent `limit` rows (optionally older than
    `before_created_at`, for backward pagination) and reverses them
    into chronological order.
    """
    statement = (
        select(ChatMessageModel)
        .where(ChatMessageModel.thread_id == thread_id)
        .order_by(ChatMessageModel.created_at.desc())
        .limit(limit)
    )
    if before_created_at is not None:
        statement = statement.where(ChatMessageModel.created_at < before_created_at)

    result = await session.execute(statement)
    return list(reversed(result.scalars().all()))
