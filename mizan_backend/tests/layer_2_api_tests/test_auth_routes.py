"""End-to-end tests for the authentication Layer 2 HTTP routes.

Uses `httpx.AsyncClient` over `ASGITransport` inside fully async test
functions — the same pattern proven for the Wallet routes — so the
app, its `AuthController`/`UnitOfWork`, and every HTTP request share
one event loop, avoiding a synchronous `TestClient`'s risk of mixing
an externally-built async engine with a separately-threaded client
loop.
"""
from __future__ import annotations

from typing import AsyncIterator

import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.layer_2_api.auth.auth_controller import AuthController
from src.layer_2_api.auth.deps import get_current_user
from src.layer_2_api.main_router import api_router
from src.layer_3_business.auth.auth_service import AuthService
from src.layer_4_data_access.repositories.user_repository import UserRecord
from src.layer_4_data_access.uow.transaction_manager import UnitOfWork
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory

TEST_SECRET_KEY = "test-secret-key-at-least-32-bytes-long-for-hmac-sha256"


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    test_engine = build_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return build_session_factory(engine)


@pytest_asyncio.fixture
async def app(session_factory: async_sessionmaker) -> FastAPI:
    def unit_of_work_factory() -> UnitOfWork:
        return UnitOfWork(session_factory)

    application = FastAPI()
    application.include_router(api_router, prefix="/api/v1")
    application.state.auth_controller = AuthController(
        auth_service=AuthService(
            secret_key=TEST_SECRET_KEY, access_token_expire_minutes=30
        ),
        unit_of_work_factory=unit_of_work_factory,
    )

    # A minimal protected "dummy" route, in addition to the real
    # GET /auth/me, purely to prove `get_current_user` works as a
    # drop-in dependency for *any* router — exactly how the Wallet and
    # Chat routes will eventually adopt it.
    @application.get("/api/v1/protected/ping")
    async def protected_ping(current_user: UserRecord = Depends(get_current_user)) -> dict:
        return {"pong": True, "user_email": current_user.email}

    return application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


VALID_REGISTRATION = {
    "email": "alice@example.com",
    "password": "correct-horse-battery-staple",
    "full_name": "Alice Example",
}


class TestRegister:
    async def test_register_returns_201_with_user_profile(
        self, client: AsyncClient
    ) -> None:
        response = await client.post("/api/v1/auth/register", json=VALID_REGISTRATION)

        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "alice@example.com"
        assert body["full_name"] == "Alice Example"
        assert body["is_active"] is True
        assert "id" in body
        assert "password" not in body
        assert "hashed_password" not in body

    async def test_register_rejects_a_duplicate_email(self, client: AsyncClient) -> None:
        first = await client.post("/api/v1/auth/register", json=VALID_REGISTRATION)
        assert first.status_code == 201

        second = await client.post("/api/v1/auth/register", json=VALID_REGISTRATION)
        assert second.status_code == 400
        assert "already registered" in second.json()["detail"]

    async def test_register_rejects_an_invalid_email_format(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={**VALID_REGISTRATION, "email": "not-an-email"},
        )
        assert response.status_code == 422

    async def test_register_rejects_a_too_short_password(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/auth/register", json={**VALID_REGISTRATION, "password": "short"}
        )
        assert response.status_code == 422

    async def test_register_never_stores_the_plaintext_password(
        self, client: AsyncClient, session_factory: async_sessionmaker
    ) -> None:
        await client.post("/api/v1/auth/register", json=VALID_REGISTRATION)

        async with UnitOfWork(session_factory) as uow:
            stored_user = await uow.users.get_user_by_email("alice@example.com")
        assert stored_user is not None
        assert stored_user.hashed_password != VALID_REGISTRATION["password"]
        assert stored_user.hashed_password.startswith("$2b$")


class TestLogin:
    async def test_login_with_correct_credentials_returns_a_token(
        self, client: AsyncClient
    ) -> None:
        await client.post("/api/v1/auth/register", json=VALID_REGISTRATION)

        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": VALID_REGISTRATION["email"],
                "password": VALID_REGISTRATION["password"],
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert isinstance(body["access_token"], str) and body["access_token"]

    async def test_login_rejects_wrong_password(self, client: AsyncClient) -> None:
        await client.post("/api/v1/auth/register", json=VALID_REGISTRATION)

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": VALID_REGISTRATION["email"], "password": "wrong-password"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password."

    async def test_login_rejects_an_unregistered_email(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "anything123"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password."

    async def test_wrong_password_and_unregistered_email_are_indistinguishable(
        self, client: AsyncClient
    ) -> None:
        await client.post("/api/v1/auth/register", json=VALID_REGISTRATION)

        wrong_password_response = await client.post(
            "/api/v1/auth/login",
            json={"email": VALID_REGISTRATION["email"], "password": "wrong-password"},
        )
        unregistered_response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "anything123"},
        )

        assert wrong_password_response.status_code == unregistered_response.status_code
        assert wrong_password_response.json() == unregistered_response.json()


class TestProtectedRoutes:
    async def test_me_returns_the_authenticated_users_profile(
        self, client: AsyncClient
    ) -> None:
        await client.post("/api/v1/auth/register", json=VALID_REGISTRATION)
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": VALID_REGISTRATION["email"],
                "password": VALID_REGISTRATION["password"],
            },
        )
        token = login_response.json()["access_token"]

        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        assert response.json()["email"] == VALID_REGISTRATION["email"]

    async def test_me_rejects_a_missing_token(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401 or response.status_code == 403

    async def test_me_rejects_a_malformed_token(self, client: AsyncClient) -> None:
        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"}
        )
        assert response.status_code == 401

    async def test_me_rejects_a_token_signed_with_a_different_secret(
        self, client: AsyncClient
    ) -> None:
        await client.post("/api/v1/auth/register", json=VALID_REGISTRATION)
        forged_service = AuthService(secret_key="a-totally-different-secret-key!!!")
        forged_token = forged_service.create_access_token(
            subject=VALID_REGISTRATION["email"]
        )

        response = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {forged_token}"}
        )
        assert response.status_code == 401

    async def test_dummy_protected_route_accepts_a_valid_token(
        self, client: AsyncClient
    ) -> None:
        """The exact scenario Wallet/Chat routes will exercise once
        they adopt `get_current_user`: an arbitrary route outside
        `auth_routes.py` protected by the same dependency."""
        await client.post("/api/v1/auth/register", json=VALID_REGISTRATION)
        login_response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": VALID_REGISTRATION["email"],
                "password": VALID_REGISTRATION["password"],
            },
        )
        token = login_response.json()["access_token"]

        response = await client.get(
            "/api/v1/protected/ping", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        assert response.json() == {"pong": True, "user_email": VALID_REGISTRATION["email"]}

    async def test_dummy_protected_route_rejects_no_token(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/v1/protected/ping")
        assert response.status_code in (401, 403)


class TestOpenApiDocumentation:
    async def test_every_auth_endpoint_has_a_summary_and_description(
        self, app: FastAPI
    ) -> None:
        schema = app.openapi()
        auth_paths = {
            path: methods
            for path, methods in schema["paths"].items()
            if path.startswith("/api/v1/auth")
        }
        # Named rather than counted: a bare count tells you the number
        # changed, not which endpoint appeared or vanished, and an
        # endpoint silently disappearing from the auth surface is worth
        # a specific failure.
        assert set(auth_paths) == {
            "/api/v1/auth/register",
            "/api/v1/auth/login",
            "/api/v1/auth/logout",
            "/api/v1/auth/me",
        }

        for path, methods in auth_paths.items():
            for method, operation in methods.items():
                assert operation.get("summary"), f"{method.upper()} {path} has no summary"
                assert operation.get(
                    "description"
                ), f"{method.upper()} {path} has no description"
