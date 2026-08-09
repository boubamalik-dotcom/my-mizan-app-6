"""Unit tests for the pure Layer 3 chat business logic.

No FastAPI, no database, no network — every test here runs purely in
memory, proving `chat_service.py` is fully testable in isolation.
"""
from __future__ import annotations

import pytest

from src.layer_3_business.chat.chat_service import (
    ChatRoom,
    ChatService,
    MessageRateLimiter,
    MessageType,
)
from src.layer_3_business.chat.exceptions import (
    AlreadyJoinedError,
    InvalidMessageError,
    NotAParticipantError,
    RateLimitExceededError,
    RoomFullError,
)


@pytest.fixture
def service() -> ChatService:
    return ChatService()


@pytest.fixture
def room() -> ChatRoom:
    return ChatRoom(id="room-1", participant_ids={"alice"}, max_participants=2)


class TestValidateMessageContent:
    def test_strips_and_returns_valid_content(self, service: ChatService) -> None:
        assert service.validate_message_content("  hello  ") == "hello"

    def test_rejects_none(self, service: ChatService) -> None:
        with pytest.raises(InvalidMessageError):
            service.validate_message_content(None)

    def test_rejects_empty_or_whitespace_only(self, service: ChatService) -> None:
        with pytest.raises(InvalidMessageError):
            service.validate_message_content("   ")

    def test_rejects_content_over_max_length(self) -> None:
        short_service = ChatService(max_message_length=5)
        with pytest.raises(InvalidMessageError):
            short_service.validate_message_content("too long")


class TestComposeMessage:
    def test_builds_message_for_participant(
        self, service: ChatService, room: ChatRoom
    ) -> None:
        message = service.compose_message(room=room, sender_id="alice", content="hi")

        assert message.room_id == "room-1"
        assert message.sender_id == "alice"
        assert message.content == "hi"
        assert message.type is MessageType.TEXT
        assert message.id

    def test_rejects_sender_not_in_room(
        self, service: ChatService, room: ChatRoom
    ) -> None:
        with pytest.raises(NotAParticipantError):
            service.compose_message(room=room, sender_id="mallory", content="hi")

    def test_rejects_invalid_content(self, service: ChatService, room: ChatRoom) -> None:
        with pytest.raises(InvalidMessageError):
            service.compose_message(room=room, sender_id="alice", content="   ")

    def test_enforces_rate_limit(self, room: ChatRoom) -> None:
        limited_service = ChatService(
            rate_limiter=MessageRateLimiter(max_messages=1, window_seconds=60)
        )
        limited_service.compose_message(room=room, sender_id="alice", content="first")

        with pytest.raises(RateLimitExceededError):
            limited_service.compose_message(room=room, sender_id="alice", content="second")

    def test_to_dict_is_json_ready(self, service: ChatService, room: ChatRoom) -> None:
        message = service.compose_message(room=room, sender_id="alice", content="hi")
        payload = message.to_dict()

        assert payload["id"] == message.id
        assert payload["type"] == "text"
        assert isinstance(payload["created_at"], str)


class TestRoomMembership:
    def test_join_room_adds_participant(self, service: ChatService, room: ChatRoom) -> None:
        service.join_room(room, "bob")
        assert room.has_participant("bob")
        assert room.participant_count == 2

    def test_join_room_rejects_duplicate(
        self, service: ChatService, room: ChatRoom
    ) -> None:
        with pytest.raises(AlreadyJoinedError):
            service.join_room(room, "alice")

    def test_join_room_rejects_when_full(self, service: ChatService) -> None:
        full_room = ChatRoom(id="full", participant_ids={"a", "b"}, max_participants=2)
        with pytest.raises(RoomFullError):
            service.join_room(full_room, "c")

    def test_leave_room_removes_participant(
        self, service: ChatService, room: ChatRoom
    ) -> None:
        service.leave_room(room, "alice")
        assert not room.has_participant("alice")

    def test_leave_room_rejects_non_participant(
        self, service: ChatService, room: ChatRoom
    ) -> None:
        with pytest.raises(NotAParticipantError):
            service.leave_room(room, "mallory")


class TestSessionManagement:
    def test_start_and_end_session(self, service: ChatService) -> None:
        session = service.start_session(room_id="room-1", user_id="alice")
        assert session.is_active

        closed = service.end_session(session)
        assert not closed.is_active
        assert closed.ended_at is not None

    def test_closing_twice_is_idempotent(self, service: ChatService) -> None:
        session = service.start_session(room_id="room-1", user_id="alice")
        closed_once = service.end_session(session)
        closed_twice = service.end_session(closed_once)
        assert closed_once.ended_at == closed_twice.ended_at


class TestMessageRateLimiter:
    def test_allows_up_to_max_messages_in_window(self) -> None:
        limiter = MessageRateLimiter(max_messages=3, window_seconds=10)
        for _ in range(3):
            limiter.check("alice", now=0.0)

        with pytest.raises(RateLimitExceededError):
            limiter.check("alice", now=0.0)

    def test_window_expiry_allows_more_messages(self) -> None:
        limiter = MessageRateLimiter(max_messages=1, window_seconds=10)
        limiter.check("alice", now=0.0)
        # Still within the window.
        with pytest.raises(RateLimitExceededError):
            limiter.check("alice", now=5.0)
        # Window has now elapsed.
        limiter.check("alice", now=10.1)

    def test_reset_clears_history(self) -> None:
        limiter = MessageRateLimiter(max_messages=1, window_seconds=10)
        limiter.check("alice", now=0.0)
        limiter.reset("alice")
        limiter.check("alice", now=0.1)  # would have raised without reset

    def test_rejects_non_positive_configuration(self) -> None:
        with pytest.raises(ValueError):
            MessageRateLimiter(max_messages=0)
        with pytest.raises(ValueError):
            MessageRateLimiter(window_seconds=0)


class TestHistoryPagination:
    def test_orders_and_limits_messages(self, service: ChatService, room: ChatRoom) -> None:
        unlimited_service = ChatService(rate_limiter=MessageRateLimiter(max_messages=100))
        messages = [
            unlimited_service.compose_message(room=room, sender_id="alice", content=f"m{i}")
            for i in range(5)
        ]
        # Shuffle the input order to prove the service re-sorts by time.
        shuffled = [messages[3], messages[0], messages[4], messages[1], messages[2]]

        page = service.build_history_page(shuffled, limit=2)

        assert [message.content for message in page] == ["m3", "m4"]

    def test_limit_zero_returns_everything(self, service: ChatService, room: ChatRoom) -> None:
        unlimited_service = ChatService(rate_limiter=MessageRateLimiter(max_messages=100))
        messages = [
            unlimited_service.compose_message(room=room, sender_id="alice", content=f"m{i}")
            for i in range(3)
        ]
        page = service.build_history_page(messages, limit=0)
        assert len(page) == 3
