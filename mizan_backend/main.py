"""Composition root: builds the FastAPI application and wires together
every layer of the Mizan Logic architecture.

This is the *only* module allowed to know about every layer at once —
it constructs Layer 3 services, Layer 4 adapters (message broker,
repositories), and hands them to Layer 2 controllers, storing the
result on `app.state` for routes to resolve via `Depends`.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from config import get_settings
from src.layer_2_api.controllers.chat_controller import ChatController
from src.layer_2_api.main_router import api_router
from src.layer_3_business.chat.chat_service import ChatService, MessageRateLimiter
from src.layer_4_data_access.events.message_broker import RedisMessageBroker
from src.layer_5_storage.db_config import init_models
from src.layer_5_storage.implementations.chat_repository_impl import (
    SqlAlchemyChatRepository,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    await init_models()

    message_broker = RedisMessageBroker(settings.redis_url)
    await message_broker.connect()

    chat_service = ChatService(
        max_message_length=settings.chat_message_max_length,
        rate_limiter=MessageRateLimiter(
            max_messages=settings.chat_rate_limit_messages,
            window_seconds=settings.chat_rate_limit_window_seconds,
        ),
    )
    chat_repository = SqlAlchemyChatRepository(
        default_max_participants=settings.chat_room_max_participants
    )
    chat_controller = ChatController(
        chat_service=chat_service,
        repository=chat_repository,
        broker=message_broker,
    )

    app.state.message_broker = message_broker
    app.state.chat_controller = chat_controller

    logger.info("%s started (environment=%s)", settings.app_name, settings.environment)
    try:
        yield
    finally:
        await chat_controller.shutdown()
        await message_broker.disconnect()
        logger.info("%s shut down cleanly.", settings.app_name)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
