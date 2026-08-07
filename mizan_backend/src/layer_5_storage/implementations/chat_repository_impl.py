"""Layer 5 — concrete SQLAlchemy-backed implementation of the Layer 4
`ChatRepository` interface.

This is the only place in the codebase that translates between Layer
3's plain-Python domain objects (`ChatRoom`, `ChatMessage`) and Layer
5's ORM rows (`ChatThreadModel`, `ChatParticipantModel`,
`ChatMessageModel`) — Layer 2 and Layer 3 never see a SQLAlchemy
object.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...layer_3_business.chat.chat_service import ChatMessage, ChatRoom, MessageType
from ...layer_4_data_access.repositories.chat_repository import ChatRepository
from ..crud import message_crud
from ..db_config import async_session_factory
from ..models.message_model import ChatMessageModel
from ..models.message_model import MessageType as DbMessageType


class SqlAlchemyChatRepository(ChatRepository):
    """Async SQLAlchemy implementation of `ChatRepository`.

    Accepts its session factory via constructor injection (defaulting
    to the process-wide one from `db_config`) so tests can point it at
    an isolated in-memory database.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
        *,
        default_max_participants: int = 200,
    ) -> None:
        self._session_factory = session_factory
        self._default_max_participants = default_max_participants

    async def get_or_create_room(self, room_id: str) -> ChatRoom:
        async with self._session_factory() as session:
            thread = await message_crud.get_thread(session, room_id)
            if thread is None:
                thread = await message_crud.create_thread(
                    session,
                    room_id,
                    max_participants=self._default_max_participants,
                )
                await session.commit()

            participants = await message_crud.list_active_participants(
                session, room_id
            )
            return ChatRoom(
                id=thread.id,
                participant_ids={participant.user_id for participant in participants},
                max_participants=thread.max_participants,
            )

    async def save_room(self, room: ChatRoom) -> None:
        async with self._session_factory() as session:
            existing = await message_crud.list_active_participants(session, room.id)
            existing_ids = {participant.user_id for participant in existing}

            joined_ids = room.participant_ids - existing_ids
            left_ids = existing_ids - room.participant_ids

            for user_id in joined_ids:
                await message_crud.add_participant(session, room.id, user_id)
            for user_id in left_ids:
                await message_crud.mark_participant_left(session, room.id, user_id)

            await session.commit()

    async def save_message(self, message: ChatMessage) -> None:
        async with self._session_factory() as session:
            await message_crud.create_message(
                session,
                id=message.id,
                thread_id=message.room_id,
                sender_id=message.sender_id,
                content=message.content,
                type=DbMessageType(message.type.value),
                created_at=message.created_at,
            )
            await session.commit()

    async def get_history(
        self,
        room_id: str,
        *,
        limit: int = 50,
        before_id: Optional[str] = None,
    ) -> List[ChatMessage]:
        async with self._session_factory() as session:
            before_created_at = None
            if before_id is not None:
                anchor = await session.get(ChatMessageModel, before_id)
                if anchor is not None:
                    before_created_at = anchor.created_at

            rows = await message_crud.get_history(
                session,
                room_id,
                limit=limit,
                before_created_at=before_created_at,
            )
            return [self._to_domain(row) for row in rows]

    @staticmethod
    def _to_domain(row: ChatMessageModel) -> ChatMessage:
        return ChatMessage(
            id=row.id,
            room_id=row.thread_id,
            sender_id=row.sender_id,
            content=row.content,
            type=MessageType(row.type.value),
            created_at=row.created_at,
        )
