"""End-to-end tests for token revocation and login rate limiting.

Uses the same `httpx.AsyncClient` over `ASGITransport` harness as the
other Layer 2 tests, with the in-memory blocklist and limiter so the
suite needs no Redis. Their Redis counterparts implement the same
interfaces and are covered separately in
`tests/layer_4_data_access_tests/cache/`.
"""
from __future__ import annotations

from typing import AsyncIterator, Dict

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.layer_2_api.audit.audit_controller import AuditController
from src.layer_2_api.auth.auth_controller import AuthController
from src.layer_2_api.controllers.wallet_controller import WalletController
from src.layer_2_api.main_router import api_router
from src.layer_3_business.audit.audit_service import AuditService
from src.layer_3_business.auth.auth_service import AuthService
from src.layer_3_business.wallet.wallet_service import WalletService
from src.layer_4_data_access.cache.rate_limiter import InMemoryRateLimiter
from src.layer_4_data_access.cache.token_blocklist import InMemoryTokenBlocklist
from src.layer_4_data_access.uow.transaction_manager import UnitOfWork
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory

TEST_SECRET_KEY = "test-secret-key-at-least-32-bytes-long-for-hmac-sha256"
TEST_PASSWORD = "correct-horse-battery-staple"


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


@pytest.fixture
def blocklist() -> InMemoryTokenBlocklist:
    return InMemoryTokenBlocklist()


@pytest.fixture
def limiter() -> InMemoryRateLimiter:
    return InMemoryRateLimiter()


@pytest_asyncio.fixture
async def app(
    session_factory: async_sessionmaker,
    blocklist: InMemoryTokenBlocklist,
    limiter: InMemoryRateLimiter,
) -> FastAPI:
    def unit_of_work_factory() -> UnitOfWork:
        return UnitOfWork(session_factory)

    application = FastAPI()
    application.include_router(api_router, prefix="/api/v1")
    application.state.auth_controller = AuthController(
        auth_service=AuthService(secret_key=TEST_SECRET_KEY),
        unit_of_work_factory=unit_of_work_factory,
        token_blocklist=blocklist,
    )
    # The other controllers are registered so the "enforced on every
    # protected route" test can actually call their routes rather than
    # asserting against a single endpoint.
    application.state.wallet_controller = WalletController(
        wallet_service=WalletService(),
        unit_of_work_factory=unit_of_work_factory,
    )
    application.state.audit_controller = AuditController(
        audit_service=AuditService(),
        unit_of_work_factory=unit_of_work_factory,
    )
    application.state.rate_limiter = limiter
    return application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


def _auth(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _register(client: AsyncClient, *, email: str) -> None:
    """Registers without logging in.

    Kept separate because a login consumes one of the rate-limited
    attempts, which would quietly skew any test counting them.
    """
    registered = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": TEST_PASSWORD, "full_name": "Test User"},
    )
    assert registered.status_code == 201, registered.text


async def _register_and_login(client: AsyncClient, *, email: str) -> str:
    registered = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": TEST_PASSWORD, "full_name": "Test User"},
    )
    assert registered.status_code == 201, registered.text

    logged_in = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD}
    )
    assert logged_in.status_code == 200, logged_in.text
    return logged_in.json()["access_token"]


class TestTokenRevocation:
    async def test_a_token_works_until_it_is_revoked(
        self, client: AsyncClient
    ) -> None:
        token = await _register_and_login(client, email="user@example.com")

        assert (
            await client.get("/api/v1/auth/me", headers=_auth(token))
        ).status_code == 200

    async def test_logout_stops_the_token_working_immediately(
        self, client: AsyncClient
    ) -> None:
        """The point of the whole feature.

        A JWT is accepted because it verifies, not because a server
        remembers issuing it, so without a blocklist "logging out" only
        deletes the client's copy and leaves a working credential
        behind in every log and cache it passed through.
        """
        token = await _register_and_login(client, email="user@example.com")

        logout = await client.post("/api/v1/auth/logout", headers=_auth(token))
        assert logout.status_code == 204

        refused = await client.get("/api/v1/auth/me", headers=_auth(token))
        assert refused.status_code == 401
        assert "revoked" in refused.json()["detail"].lower()

    async def test_revoking_one_session_leaves_the_others_working(
        self, client: AsyncClient
    ) -> None:
        # Each token carries its own `jti`, so signing out on a phone
        # must not sign the user out on their laptop.
        email = "multi@example.com"
        first = await _register_and_login(client, email=email)
        second_login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD}
        )
        second = second_login.json()["access_token"]
        assert first != second

        await client.post("/api/v1/auth/logout", headers=_auth(first))

        assert (
            await client.get("/api/v1/auth/me", headers=_auth(first))
        ).status_code == 401
        assert (
            await client.get("/api/v1/auth/me", headers=_auth(second))
        ).status_code == 200

    async def test_logout_is_idempotent(self, client: AsyncClient) -> None:
        # A client that cannot reliably log out will retry, and the
        # retry must not fail.
        token = await _register_and_login(client, email="user@example.com")

        assert (
            await client.post("/api/v1/auth/logout", headers=_auth(token))
        ).status_code == 204
        assert (
            await client.post("/api/v1/auth/logout", headers=_auth(token))
        ).status_code == 204

    async def test_logout_requires_a_token(self, client: AsyncClient) -> None:
        assert (await client.post("/api/v1/auth/logout")).status_code == 401

    async def test_logout_rejects_a_malformed_token(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/v1/auth/logout", headers=_auth("not-a-real-jwt")
        )
        assert response.status_code == 401

    async def test_the_blocklist_stores_the_token_id_not_the_token(
        self, client: AsyncClient, blocklist: InMemoryTokenBlocklist
    ) -> None:
        """A blocklist holding whole tokens would be a store of live
        credentials — readable by anyone with access to it, and usable
        to impersonate every user who had merely logged out."""
        token = await _register_and_login(client, email="user@example.com")
        await client.post("/api/v1/auth/logout", headers=_auth(token))

        stored = list(blocklist._expiries)  # noqa: SLF001 - asserting the shape
        assert stored, "nothing was revoked"
        assert all(entry not in token for entry in stored)
        assert all(len(entry) < len(token) for entry in stored)

    async def test_a_revoked_token_expires_out_of_the_blocklist(
        self, client: AsyncClient, blocklist: InMemoryTokenBlocklist
    ) -> None:
        # The entry lives exactly as long as the token does, so the
        # store stays bounded by active sessions rather than growing
        # with every logout ever performed.
        token = await _register_and_login(client, email="user@example.com")
        await client.post("/api/v1/auth/logout", headers=_auth(token))

        token_id = next(iter(blocklist._expiries))  # noqa: SLF001
        assert await blocklist.is_revoked(token_id)

        blocklist._expiries[token_id] = 0.0  # noqa: SLF001 - simulate expiry
        assert not await blocklist.is_revoked(token_id)

    async def test_revocation_is_enforced_on_every_protected_route(
        self, client: AsyncClient
    ) -> None:
        # Enforced in `get_current_user`, so it covers every route that
        # depends on it rather than only the one it was tested against.
        token = await _register_and_login(client, email="user@example.com")
        await client.post("/api/v1/auth/logout", headers=_auth(token))

        for path in ("/api/v1/auth/me", "/api/v1/wallet", "/api/v1/audit/ledger"):
            response = await client.get(path, headers=_auth(token))
            assert response.status_code == 401, path


class TestLoginRateLimiting:
    async def test_repeated_failures_are_eventually_refused(
        self, client: AsyncClient
    ) -> None:
        # Registered but not logged in: a login would spend one of the
        # five attempts being counted here.
        await _register(client, email="victim@example.com")

        statuses = []
        for _ in range(8):
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": "victim@example.com", "password": "wrong-password"},
            )
            statuses.append(response.status_code)

        # The default allows 5 attempts per window; the rest are refused
        # without the password even being checked.
        assert statuses[:5] == [401] * 5
        assert statuses[5:] == [429] * 3

    async def test_the_refusal_says_when_to_retry(
        self, client: AsyncClient
    ) -> None:
        for _ in range(6):
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": "nobody@example.com", "password": "wrong"},
            )

        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"
        assert response.headers["X-RateLimit-Limit"] == "5"

    async def test_the_limit_applies_to_correct_passwords_too(
        self, client: AsyncClient
    ) -> None:
        # Otherwise an attacker who found the password on attempt 200
        # would sail past the limit at the moment it matters most.
        email = "throttled@example.com"
        await _register(client, email=email)

        statuses = []
        for _ in range(8):
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": TEST_PASSWORD},
            )
            statuses.append(response.status_code)

        assert 429 in statuses

    async def test_registration_has_its_own_budget(
        self, client: AsyncClient
    ) -> None:
        # Scoped separately, so exhausting the login limit does not also
        # lock the caller out of registering.
        for index in range(6):
            await client.post(
                "/api/v1/auth/login",
                json={"email": f"x{index}@example.com", "password": "wrong"},
            )

        registered = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "fresh@example.com",
                "password": TEST_PASSWORD,
                "full_name": "Fresh",
            },
        )
        assert registered.status_code == 201

    async def test_an_authenticated_route_is_not_throttled(
        self, client: AsyncClient
    ) -> None:
        # The limit targets the unauthenticated attack surface; a
        # signed-in user reading their profile repeatedly is not an
        # attack.
        token = await _register_and_login(client, email="busy@example.com")

        for _ in range(20):
            response = await client.get("/api/v1/auth/me", headers=_auth(token))

        assert response.status_code == 200
