"""Layer 3 — who is entitled to which chat room.

STRICT RULE: no FastAPI, no Pydantic, no SQLAlchemy. This is the rule
itself, expressed as pure functions of a room id and a user id, so it
can be tested exhaustively in memory and reviewed without reading a
route handler.

## Why this module exists

A security review found that every client connected to one shared room
(`general`) and that the history endpoint authorized the *caller's
identity* without ever checking the *room* they asked for. The identity
check passed, so the request looked authorized — and returned every
other user's messages. Proven before the fix: a user requesting only
her own history read 17 messages belonging to other people.

The rule below closes that by making a room's name derive from its
owner, so entitlement is decidable from the request alone with no
lookup and nothing to get out of sync.

## The MVP's deliberate limitation

`private_{user_id}` gives each user exactly one room that only they may
enter. That makes the data private, and it also means **two users
cannot converse** — nobody else is permitted into your room. This is a
containment step, not a finished messaging model.

A real conversation needs rooms with more than one legitimate member,
at which point entitlement stops being derivable from the name and
becomes a membership lookup. The `chat_participants` table already
exists for exactly that; [is_private_room] is where the successor rule
will slot in, and every caller goes through [assert_room_access], so
there is one place to change.
"""
from __future__ import annotations

from .exceptions import RoomAccessDeniedError

#: Prefix marking a room as one user's private room.
PRIVATE_ROOM_PREFIX = "private_"


def private_room_id_for(user_id: str) -> str:
    """The id of `user_id`'s own private room.

    Built from the user's **database id**, not their email: an email can
    be changed, and a room whose name tracked it would either strand
    the history under the old name or hand the new owner of a recycled
    address someone else's messages.
    """
    return f"{PRIVATE_ROOM_PREFIX}{user_id}"


def is_private_room(room_id: str, user_id: str) -> bool:
    """Whether `room_id` is `user_id`'s own private room.

    An exact comparison against the derived name, so a room merely
    *starting* with the prefix does not qualify — `private_alice_evil`
    is not Alice's room, and neither is `private_` on its own.
    """
    if not user_id:
        return False
    return room_id == private_room_id_for(user_id)


def assert_room_access(*, room_id: str, user_id: str) -> None:
    """Asserts that `user_id` is entitled to `room_id`.

    Raises:
        RoomAccessDeniedError: If they are not. Raising rather than
            returning a bool is what makes this hard to misuse: an
            ignored return value fails open, which for the vulnerability
            this exists to fix would mean silently serving another
            user's messages again.
    """
    if not is_private_room(room_id, user_id):
        raise RoomAccessDeniedError(room_id, user_id)
