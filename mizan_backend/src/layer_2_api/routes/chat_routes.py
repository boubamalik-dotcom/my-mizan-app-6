"""Layer 2 — Chat Engine HTTP + WebSocket routes.

Routes are intentionally thin: they parse/validate transport-level
input, delegate to `ChatController`, and translate results/errors back
into HTTP responses or WebSocket frames. All actual behaviour lives in
`ChatController` (orchestration) plus Layers 3-5 (logic/persistence) —
this module must never contain business rules of its own.

WebSocket authentication: standard browser `WebSocket` APIs cannot
send custom HTTP headers, so `Authorization: Bearer <token>` is not an
option for the chat connection the way it is for the Wallet's plain
HTTP endpoints. The token is instead passed as a `?token=` query
parameter and validated with `AuthService.decode_access_token` before
the connection is ever accepted.
"""
from __future__ import annotations

import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import ValidationError

from ...layer_3_business.chat.exceptions import (
    ChatDomainError,
    RoomAccessDeniedError,
)
from ...layer_3_business.chat.room_access import assert_room_access
from ...layer_4_data_access.repositories.user_repository import UserRecord
from ..auth.auth_controller import AuthController
from ..auth.deps import get_current_user
from ..controllers.chat_controller import ChatController
from ..schemas.chat_schemas import ChatHistoryResponse, ErrorResponse, WebSocketIncomingMessage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


def get_chat_controller(request: Request) -> ChatController:
    """Resolves the app-wide `ChatController` singleton for HTTP
    routes. Constructed once at startup in `main.py` and stored on
    `app.state` (composition root), so it is never re-instantiated per
    request."""
    return request.app.state.chat_controller


def get_chat_controller_ws(websocket: WebSocket) -> ChatController:
    """Same resolution as `get_chat_controller`, for WebSocket routes
    (which receive a `WebSocket`, not a `Request`)."""
    return websocket.app.state.chat_controller


def get_auth_controller_ws(websocket: WebSocket) -> AuthController:
    """Resolves the app-wide `AuthController` for WebSocket routes.

    The socket handshake needs the caller's account, not just a valid
    signature: the room rule is defined in terms of the user's database
    id, and loading the account is also what makes deactivation take
    effect. `AuthController.resolve_user_or_none` exists for exactly
    this caller — it returns `None` instead of raising an
    `HTTPException`, which would be meaningless for a connection that
    was never accepted."""
    return websocket.app.state.auth_controller


@router.get(
    "/history/{client_id}",
    response_model=ChatHistoryResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {
            "model": ErrorResponse,
            "description": "Missing or invalid access token.",
        },
        403: {
            "model": ErrorResponse,
            "description": "The authenticated caller's identity does not "
            "match the requested client id.",
        },
    },
    summary="Retrieve chat history for a room, scoped to the calling client",
)
async def get_chat_history(
    client_id: str,
    room_id: str = Query(..., description="Room whose history to fetch."),
    limit: int = Query(default=50, ge=1, le=200),
    controller: ChatController = Depends(get_chat_controller),
    current_user: UserRecord = Depends(get_current_user),
) -> ChatHistoryResponse:
    """Returns up to `limit` most recent messages for `room_id`,
    oldest first, plus whether older messages exist beyond this page.

    Two independent checks, both before any history is read:

    1. `client_id` must be the caller's own identity (their account
       email, the JWT's subject), so a caller cannot pose as another
       client.
    2. **`room_id` must be the caller's own room** —
       `private_{current_user.id}`, enforced by Layer 3's
       `assert_room_access`.

    The second check is the fix for a real vulnerability: this endpoint
    used to validate only the first. Since every client also happened to
    use one shared room, a caller asking for *their own* `client_id`
    passed the check and was handed every other user's messages. An
    identity check alone authorizes *who is asking*, never *what they
    asked for*.

    Both failures answer a bare `403 Forbidden` with no detail about
    whether the room exists, so the endpoint cannot be used to
    enumerate other users' rooms.
    """
    if current_user.email != client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
        )

    try:
        assert_room_access(room_id=room_id, user_id=current_user.id)
    except RoomAccessDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
        ) from exc

    try:
        return await controller.get_history(room_id=room_id, limit=limit)
    except ChatDomainError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.websocket("/ws/chat/{client_id}")
async def chat_websocket(
    websocket: WebSocket,
    client_id: str,
    room_id: str = Query(..., description="Room to join for this connection."),
    token: str | None = Query(
        default=None,
        description=(
            "JWT access token issued by POST /auth/login, e.g. "
            "ws://.../ws/chat/{client_id}?room_id=...&token=.... Required — "
            "standard WebSocket APIs cannot send an Authorization header."
        ),
    ),
    controller: ChatController = Depends(get_chat_controller_ws),
    auth_controller: AuthController = Depends(get_auth_controller_ws),
) -> None:
    """Real-time chat connection.

    Protocol (JSON text frames):

    * client -> server: `{"type": "message", "content": "..."}` or
      `{"type": "ping"}`
    * server -> client: `{"type": "message", "data": {...}}`,
      `{"type": "system", "data": {...}}`, `{"type": "pong"}`, or
      `{"type": "error", "detail": "..."}`

    Everything is checked *before* the connection is accepted, so a
    rejected client never receives an ASGI "accept" and cannot tell our
    refusal apart from a server that never saw the request:

    1. `token` must be a valid, unexpired access token belonging to an
       account that still exists and is still active.
    2. Its subject (email) must match `client_id`.
    3. **`room_id` must be the caller's own room** —
       `private_{user.id}`, enforced by Layer 3's `assert_room_access`.

    The third check mirrors the REST history endpoint. Without it, a
    client could join any room by name and receive every message
    broadcast into it — which is what made a single shared `general`
    room a data leak rather than merely a design shortcut.

    Every rejection closes with `WS_1008_POLICY_VIOLATION` and a reason
    that never reveals whether the requested room exists.
    """
    if not token:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Missing access token."
        )
        return

    # Resolves the account rather than just decoding the token: the room
    # rule needs the user's database id, and going through the same
    # lookup as the REST path means a deactivated account's unexpired
    # token no longer opens a socket.
    user = await auth_controller.resolve_user_or_none(token)
    if user is None:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid or expired access token.",
        )
        return

    if user.email != client_id:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Access token does not authorize this client id.",
        )
        return

    try:
        assert_room_access(room_id=room_id, user_id=user.id)
    except RoomAccessDeniedError:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Not authorized for this room.",
        )
        return

    try:
        await controller.connect_client(websocket, room_id=room_id, client_id=client_id)
    except ChatDomainError as exc:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(exc))
        return
    except Exception:  # noqa: BLE001 - never let an unexpected error hang the socket
        logger.exception(
            "Unexpected error connecting client %s to room %s", client_id, room_id
        )
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    try:
        while True:
            raw_frame = await websocket.receive_json()
            try:
                incoming = WebSocketIncomingMessage.model_validate(raw_frame)
            except ValidationError as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
                continue

            if incoming.type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            try:
                await controller.handle_client_message(
                    room_id=room_id, client_id=client_id, content=incoming.content or ""
                )
            except ChatDomainError as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 - log but still guarantee cleanup below
        logger.exception("Unexpected error in chat websocket for client %s", client_id)
    finally:
        # Scheduled rather than awaited directly: this `finally` block
        # may itself be in the process of being cancelled as the ASGI
        # server tears down the connection's task, and a plain `await`
        # here could be cut off mid database-write. `schedule_disconnect`
        # runs the leave-notice/persistence work as an independent
        # background task that `ChatController.shutdown()` still waits
        # on during application shutdown.
        controller.schedule_disconnect(room_id=room_id, client_id=client_id)
