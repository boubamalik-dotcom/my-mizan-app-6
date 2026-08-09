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
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from src.layer_2_api.audit.audit_controller import AuditController
from src.layer_2_api.auth.auth_controller import AuthController
from src.layer_2_api.controllers.chat_controller import ChatController
from src.layer_2_api.controllers.queue_controller import QueueController
from src.layer_2_api.controllers.wallet_controller import WalletController
from src.layer_2_api.main_router import api_router
from src.layer_2_api.realtime.queue_broadcaster import QueueBroadcaster
from src.layer_3_business.audit.audit_service import AuditService
from src.layer_3_business.auth.auth_service import AuthService
from src.layer_3_business.chat.chat_service import ChatService, MessageRateLimiter
from src.layer_3_business.wallet.wallet_service import WalletService
from src.layer_4_data_access.cache.rate_limiter import RedisRateLimiter
from src.layer_4_data_access.cache.token_blocklist import RedisTokenBlocklist
from src.layer_4_data_access.events.message_broker import RedisMessageBroker
from src.layer_4_data_access.uow.transaction_manager import UnitOfWork
from src.layer_5_storage.db_config import init_models
from src.layer_5_storage.implementations.chat_repository_impl import (
    SqlAlchemyChatRepository,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    # Deliberately not unconditional: `create_all` cannot alter an
    # existing table, so running it against a database on an older
    # schema succeeds while changing nothing, and the missing column
    # only surfaces later as a failing query. Schema changes are
    # applied by `alembic upgrade head`; see `alembic.ini`.
    if settings.auto_create_schema:
        logger.warning(
            "auto_create_schema is enabled: creating any missing tables with "
            "create_all. This cannot apply schema changes to existing "
            "tables — run 'alembic upgrade head' for that."
        )
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

    wallet_controller = WalletController(
        wallet_service=WalletService(),
        unit_of_work_factory=UnitOfWork,
    )

    token_blocklist = RedisTokenBlocklist(settings.redis_url)
    await token_blocklist.connect()

    rate_limiter = RedisRateLimiter(settings.redis_url)
    await rate_limiter.connect()

    auth_service = AuthService(
        # Resolved rather than read: raises in production when unset or
        # too short, so the process never serves forgeable tokens.
        secret_key=settings.resolved_jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        access_token_expire_minutes=settings.access_token_expire_minutes,
    )
    auth_controller = AuthController(
        auth_service=auth_service,
        unit_of_work_factory=UnitOfWork,
        bootstrap_admin_emails=[
            email.strip()
            for email in settings.bootstrap_admin_emails.split(",")
            if email.strip()
        ],
        token_blocklist=token_blocklist,
    )

    audit_controller = AuditController(
        audit_service=AuditService(),
        unit_of_work_factory=UnitOfWork,
    )

    # Shares the chat engine's Redis broker rather than opening a
    # second one: both features need the same cross-process fan-out,
    # and channel names are namespaced (`queue:{clinic_id}`) so their
    # traffic cannot collide.
    queue_broadcaster = QueueBroadcaster(broker=message_broker)

    # No Layer 3 service injected, unlike the wallet: the queue's rules
    # all have to run inside the clinic row lock, so they are consulted
    # from `QueueRepository.join_queue` instead.
    queue_controller = QueueController(
        unit_of_work_factory=UnitOfWork, broadcaster=queue_broadcaster
    )

    app.state.message_broker = message_broker
    app.state.chat_controller = chat_controller
    app.state.wallet_controller = wallet_controller
    app.state.auth_controller = auth_controller
    app.state.audit_controller = audit_controller
    app.state.queue_controller = queue_controller
    app.state.queue_broadcaster = queue_broadcaster
    # Exposed separately (not just via `auth_controller`) so the Chat
    # WebSocket route can validate a `?token=` query parameter without
    # a database round trip — see
    # `layer_2_api/routes/chat_routes.py::get_auth_service_ws`.
    app.state.auth_service = auth_service
    app.state.token_blocklist = token_blocklist
    # Resolved per request by the `rate_limited` dependency.
    app.state.rate_limiter = rate_limiter

    logger.info("%s started (environment=%s)", settings.app_name, settings.environment)
    try:
        yield
    finally:
        await chat_controller.shutdown()
        # Before the broker it subscribes through is disconnected.
        await queue_broadcaster.shutdown()
        await message_broker.disconnect()
        await token_blocklist.disconnect()
        await rate_limiter.disconnect()
        logger.info("%s shut down cleanly.", settings.app_name)


def create_app() -> FastAPI:
    settings = get_settings()

    # Before anything is wired: a deployment missing a signing key, or
    # allowing every origin to make credentialed requests, must fail
    # here with a specific message rather than start and be quietly
    # insecure.
    settings.validate_for_startup()

    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

    # Browsers refuse cross-origin requests unless the server opts in,
    # so without this the Flutter *web* build cannot reach the API at
    # all — every call surfaces to the client as a generic network
    # error with nothing in the server log to explain it.
    #
    # `allow_credentials=True` is what lets the browser send the
    # `Authorization` header cross-origin. It is also why
    # `validate_for_startup` refuses a wildcard in production: the pair
    # together would invite any site to act as a signed-in user.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # So a browser can read the throttling headers the auth routes
        # set; they are useless to a client that cannot see them.
        expose_headers=["Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
