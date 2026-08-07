"""Layer 5 — SQLAlchemy ORM models for the Chat Engine: threads
(rooms), participants, and messages.

STRICT RULE: this module contains ORM models only — no business
rules, no FastAPI/Pydantic imports, and no imports from Layers 2-4.
Mapping between these rows and Layer 3 domain objects
(`ChatRoom`/`ChatMessage`) is the job of
`layer_5_storage/implementations/chat_repository_impl.py`, never of
the models themselves.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base_model import Base, TimestampMixin, generate_uuid

DEFAULT_MAX_PARTICIPANTS = 200


class MessageType(str, enum.Enum):
    """Mirrors `layer_3_business.chat.chat_service.MessageType` at the
    persistence boundary. Kept as a separate enum (rather than
    importing the Layer 3 one) so this layer has zero compile-time
    dependency on business-logic code."""

    TEXT = "text"
    SYSTEM = "system"
    JOIN = "join"
    LEAVE = "leave"


class ChatThreadModel(Base, TimestampMixin):
    """A chat room/thread — the persistent counterpart of Layer 3's
    `ChatRoom` domain object."""

    __tablename__ = "chat_threads"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    max_participants: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_MAX_PARTICIPANTS
    )

    participants: Mapped[List["ChatParticipantModel"]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
    )
    messages: Mapped[List["ChatMessageModel"]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ChatMessageModel.created_at",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"ChatThreadModel(id={self.id!r}, title={self.title!r})"


class ChatParticipantModel(Base, TimestampMixin):
    """A user's membership record in a chat thread. `left_at` is null
    while the membership is active."""

    __tablename__ = "chat_participants"
    __table_args__ = (
        UniqueConstraint(
            "thread_id", "user_id", name="uq_chat_participant_thread_user"
        ),
        Index("ix_chat_participants_thread_id", "thread_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    left_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    thread: Mapped["ChatThreadModel"] = relationship(back_populates="participants")

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return (
            f"ChatParticipantModel(thread_id={self.thread_id!r}, "
            f"user_id={self.user_id!r}, left_at={self.left_at!r})"
        )


class ChatMessageModel(Base, TimestampMixin):
    """A single persisted chat message belonging to a thread."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        Index(
            "ix_chat_messages_thread_id_created_at", "thread_id", "created_at"
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[MessageType] = mapped_column(
        SqlEnum(MessageType, name="chat_message_type", native_enum=False),
        nullable=False,
        default=MessageType.TEXT,
    )

    thread: Mapped["ChatThreadModel"] = relationship(back_populates="messages")

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return (
            f"ChatMessageModel(id={self.id!r}, thread_id={self.thread_id!r}, "
            f"sender_id={self.sender_id!r}, type={self.type!r})"
        )
