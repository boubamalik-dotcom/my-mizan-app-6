"""Unit tests for the pure Layer 3 chat room entitlement rule.

No FastAPI, no SQLAlchemy, no database — `room_access.py` is plain
functions of a room id and a user id, and these run entirely in memory.

This rule is the fix for a real data leak (every client shared one room
and the history endpoint never checked which room was asked for), so the
tests are written to be paranoid: the interesting cases are all the ways
a room id might *look* like it belongs to someone without belonging to
them.
"""
from __future__ import annotations

import pytest

from src.layer_3_business.chat.exceptions import (
    ChatDomainError,
    RoomAccessDeniedError,
)
from src.layer_3_business.chat.room_access import (
    PRIVATE_ROOM_PREFIX,
    assert_room_access,
    is_private_room,
    private_room_id_for,
)


class TestPrivateRoomId:
    def test_derives_a_room_from_a_user_id(self) -> None:
        assert private_room_id_for("u1") == "private_u1"

    def test_uses_the_documented_prefix(self) -> None:
        assert private_room_id_for("u1").startswith(PRIVATE_ROOM_PREFIX)

    def test_different_users_never_share_a_room(self) -> None:
        assert private_room_id_for("u1") != private_room_id_for("u2")

    def test_is_stable_for_the_same_user(self) -> None:
        # The room name is how history is located, so it must not drift
        # between calls.
        assert private_room_id_for("u1") == private_room_id_for("u1")


class TestIsPrivateRoom:
    def test_accepts_a_user_s_own_room(self) -> None:
        assert is_private_room("private_u1", "u1")

    def test_rejects_another_user_s_room(self) -> None:
        # The whole point: this is what a leaked history request looked
        # like.
        assert not is_private_room("private_u2", "u1")

    def test_rejects_the_old_shared_room(self) -> None:
        # `general` is what every client used to connect to.
        assert not is_private_room("general", "u1")

    @pytest.mark.parametrize(
        "room_id",
        [
            "private_u1_evil",  # own id as a prefix of a longer name
            "private_u11",  # own id as a prefix of another id
            "Private_u1",  # different case
            "private_u1 ",  # trailing whitespace
            " private_u1",  # leading whitespace
            "private_",  # prefix alone
            "private_u1/../private_u2",  # traversal-flavoured
            "u1",  # bare id, no prefix
            "",  # nothing
        ],
    )
    def test_requires_an_exact_match(self, room_id: str) -> None:
        # Comparing against the derived name — rather than checking a
        # prefix or a substring — is what makes all of these fail.
        assert not is_private_room(room_id, "u1")

    def test_an_empty_user_id_owns_nothing(self) -> None:
        # Otherwise a caller with no id would own `private_`.
        assert not is_private_room("private_", "")
        assert not is_private_room("", "")


class TestAssertRoomAccess:
    def test_returns_silently_for_a_user_s_own_room(self) -> None:
        assert_room_access(room_id="private_u1", user_id="u1")

    def test_raises_for_another_user_s_room(self) -> None:
        with pytest.raises(RoomAccessDeniedError) as exc_info:
            assert_room_access(room_id="private_u2", user_id="u1")

        assert exc_info.value.room_id == "private_u2"
        assert exc_info.value.user_id == "u1"

    def test_raises_for_the_old_shared_room(self) -> None:
        with pytest.raises(RoomAccessDeniedError):
            assert_room_access(room_id="general", user_id="u1")

    def test_is_a_chat_domain_error(self) -> None:
        # So Layer 2's existing `ChatDomainError` handling still catches
        # it if a new call site forgets the specific type.
        assert issubclass(RoomAccessDeniedError, ChatDomainError)

    def test_raising_rather_than_returning_is_the_point(self) -> None:
        # A bool return that a caller forgets to check fails open, and
        # for this rule failing open means serving someone else's
        # messages again.
        assert assert_room_access(room_id="private_u1", user_id="u1") is None
