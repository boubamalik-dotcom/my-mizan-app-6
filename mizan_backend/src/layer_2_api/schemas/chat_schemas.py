"""Layer 2 — Pydantic request/response contracts for the Chat Engine's
REST and WebSocket APIs.

These schemas are the API's public contract: strictly typed, versioned
independently of the internal domain (`layer_3_business.chat`) and
persistence (`layer_5_storage.models.message_model`) representations
so either can evolve without breaking API consumers.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChatMessageResponse(BaseModel):
    """A single chat message as returned by the REST history endpoint
    and delivered over the WebSocket."""

    id: str
    room_id: str
    sender_id: str
    content: str
    type: Literal["text", "system", "join", "leave"]
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    """Response body for `GET /chat/history/{client_id}`."""

    room_id: str
    messages: list[ChatMessageResponse]
    has_more: bool


class WebSocketIncomingMessage(BaseModel):
    """Envelope for client -> server WebSocket frames.

    Clients send `{"type": "message", "content": "..."}` to post a
    chat message, or `{"type": "ping"}` as a lightweight keep-alive
    that the server answers with `{"type": "pong"}`.
    """

    type: Literal["message", "ping"] = "message"
    content: Optional[str] = Field(default=None, max_length=8000)


class WebSocketOutgoingMessage(BaseModel):
    """Envelope for server -> client WebSocket frames."""

    type: Literal["message", "system", "error", "pong"]
    data: Optional[ChatMessageResponse] = None
    detail: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error body for REST endpoints."""

    detail: str
