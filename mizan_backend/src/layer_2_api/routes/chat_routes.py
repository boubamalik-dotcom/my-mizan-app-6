"""Layer 2 — Chat Engine HTTP + WebSocket routes.

Routes are intentionally thin: they parse/validate transport-level
input, delegate to `ChatController`, and translate results/errors back
into HTTP responses or WebSocket frames. All actual behaviour lives in
`ChatController` (orchestration) plus Layers 3-5 (logic/persistence) —
this module must never contain business rules of its own.
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

from ...layer_3_business.chat.exceptions import ChatDomainError
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


@router.get(
    "/rooms/{room_id}/messages",
    response_model=ChatHistoryResponse,
    responses={400: {"model": ErrorResponse}},
    summary="Retrieve chat history for a room",
)
async def get_chat_history(
    room_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    controller: ChatController = Depends(get_chat_controller),
) -> ChatHistoryResponse:
    """Returns up to `limit` most recent messages for `room_id`,
    oldest first, plus whether older messages exist beyond this page.

    Raises `HTTPException(400)` if the room/business rules reject the
    request (translated from a Layer 3 `ChatDomainError`).
    """
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
    controller: ChatController = Depends(get_chat_controller_ws),
) -> None:
    """Real-time chat connection.

    Protocol (JSON text frames):

    * client -> server: `{"type": "message", "content": "..."}` or
      `{"type": "ping"}`
    * server -> client: `{"type": "message", "data": {...}}`,
      `{"type": "system", "data": {...}}`, `{"type": "pong"}`, or
      `{"type": "error", "detail": "..."}`
    """
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
