"""End-to-end tests for the Digital Wallet's Layer 2 HTTP routes,
including JWT-based authentication and per-wallet ownership
enforcement.

Uses `httpx.AsyncClient` over `ASGITransport` inside fully async test
functions — avoiding the event-loop-mismatch pitfalls a synchronous
`TestClient` with externally-built async resources can hit — so the
app, its controllers/`UnitOfWork`, and every HTTP request share one
event loop.
"""
from __future__ import annotations

from decimal import Decimal
from typing import AsyncIterator, Dict, Tuple

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.layer_2_api.auth.auth_controller import AuthController
from src.layer_2_api.controllers.wallet_controller import WalletController
from src.layer_2_api.main_router import api_router
from src.layer_3_business.auth.auth_service import AuthService
from src.layer_3_business.wallet.wallet_service import WalletService
from src.layer_4_data_access.repositories.wallet_repository import WalletRecord
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


@pytest_asyncio.fixture
async def app(session_factory: async_sessionmaker) -> FastAPI:
    def unit_of_work_factory() -> UnitOfWork:
        return UnitOfWork(session_factory)

    application = FastAPI()
    application.include_router(api_router, prefix="/api/v1")
    application.state.wallet_controller = WalletController(
        wallet_service=WalletService(),
        unit_of_work_factory=unit_of_work_factory,
    )
    application.state.auth_controller = AuthController(
        auth_service=AuthService(secret_key=TEST_SECRET_KEY),
        unit_of_work_factory=unit_of_work_factory,
    )
    return application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def _register_and_login(client: AsyncClient, *, email: str) -> Tuple[str, str]:
    """Registers a new user and logs in, returning `(user_id, access_token)`."""
    register_response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": TEST_PASSWORD, "full_name": "Test User"},
    )
    assert register_response.status_code == 201, register_response.text
    user_id = register_response.json()["id"]

    login_response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD}
    )
    assert login_response.status_code == 200, login_response.text
    token = login_response.json()["access_token"]

    return user_id, token


def _auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_wallet(
    session_factory: async_sessionmaker,
    *,
    user_id: str,
    balance: Decimal = Decimal("0"),
    is_locked: bool = False,
) -> WalletRecord:
    async with UnitOfWork(session_factory) as uow:
        wallet = await uow.wallets.create_wallet(user_id=user_id, currency="USD")
        if balance != Decimal("0"):
            wallet = await uow.wallets.update_wallet_balance(
                wallet.id, balance, expected_version=wallet.version
            )
        if is_locked:
            wallet = await uow.wallets.set_wallet_locked(wallet.id, is_locked=True)
        await uow.commit()
    return wallet


@pytest_asyncio.fixture
async def alice(client: AsyncClient) -> Tuple[str, str]:
    """Registers and logs in Alice. Returns `(user_id, access_token)`."""
    return await _register_and_login(client, email="alice@example.com")


@pytest_asyncio.fixture
async def bob(client: AsyncClient) -> Tuple[str, str]:
    """Registers and logs in Bob. Returns `(user_id, access_token)`."""
    return await _register_and_login(client, email="bob@example.com")


@pytest_asyncio.fixture
async def wallet(
    session_factory: async_sessionmaker, alice: Tuple[str, str]
) -> WalletRecord:
    """A wallet owned by Alice, pre-funded with 100.00."""
    alice_id, _alice_token = alice
    return await _create_wallet(session_factory, user_id=alice_id, balance=Decimal("100.00"))


class TestCreateWallet:
    async def test_creates_wallet_bound_to_the_authenticated_user(
        self, client: AsyncClient, alice: Tuple[str, str]
    ) -> None:
        alice_id, alice_token = alice
        response = await client.post(
            "/api/v1/wallet", json={}, headers=_auth_headers(alice_token)
        )

        assert response.status_code == 201
        body = response.json()
        assert body["user_id"] == alice_id
        assert body["currency"] == "USD"
        assert Decimal(body["balance"]) == Decimal("0")
        assert body["is_locked"] is False

        # And the caller can immediately read it back as its owner.
        balance_response = await client.get(
            f"/api/v1/wallet/{body['wallet_id']}/balance",
            headers=_auth_headers(alice_token),
        )
        assert balance_response.status_code == 200
        assert balance_response.json()["user_id"] == alice_id

    async def test_defaults_to_usd_when_no_body_is_sent(
        self, client: AsyncClient, alice: Tuple[str, str]
    ) -> None:
        _alice_id, alice_token = alice
        response = await client.post(
            "/api/v1/wallet", headers=_auth_headers(alice_token)
        )
        assert response.status_code == 201
        assert response.json()["currency"] == "USD"

    async def test_creates_wallet_in_a_requested_currency(
        self, client: AsyncClient, alice: Tuple[str, str]
    ) -> None:
        _alice_id, alice_token = alice
        response = await client.post(
            "/api/v1/wallet",
            json={"currency": "EUR"},
            headers=_auth_headers(alice_token),
        )
        assert response.status_code == 201
        assert response.json()["currency"] == "EUR"

    async def test_returns_409_for_a_duplicate_currency(
        self, client: AsyncClient, alice: Tuple[str, str]
    ) -> None:
        _alice_id, alice_token = alice
        first = await client.post(
            "/api/v1/wallet", json={"currency": "GBP"}, headers=_auth_headers(alice_token)
        )
        assert first.status_code == 201

        second = await client.post(
            "/api/v1/wallet", json={"currency": "GBP"}, headers=_auth_headers(alice_token)
        )
        assert second.status_code == 409

    async def test_two_users_may_each_hold_their_own_wallet_in_the_same_currency(
        self, client: AsyncClient, alice: Tuple[str, str], bob: Tuple[str, str]
    ) -> None:
        _alice_id, alice_token = alice
        _bob_id, bob_token = bob

        alice_response = await client.post(
            "/api/v1/wallet", json={"currency": "USD"}, headers=_auth_headers(alice_token)
        )
        bob_response = await client.post(
            "/api/v1/wallet", json={"currency": "USD"}, headers=_auth_headers(bob_token)
        )
        assert alice_response.status_code == 201
        assert bob_response.status_code == 201
        assert alice_response.json()["wallet_id"] != bob_response.json()["wallet_id"]

    async def test_returns_401_without_a_token(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/wallet", json={})
        assert response.status_code in (401, 403)


class TestGetMyWallet:
    async def test_returns_404_when_the_caller_has_not_provisioned_a_wallet_yet(
        self, client: AsyncClient, alice: Tuple[str, str]
    ) -> None:
        _alice_id, alice_token = alice
        response = await client.get(
            "/api/v1/wallet", headers=_auth_headers(alice_token)
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Wallet not found"

    async def test_returns_the_callers_own_wallet_when_one_exists(
        self, client: AsyncClient, wallet: WalletRecord, alice: Tuple[str, str]
    ) -> None:
        alice_id, alice_token = alice
        response = await client.get(
            "/api/v1/wallet", headers=_auth_headers(alice_token)
        )

        assert response.status_code == 200
        body = response.json()
        assert body["wallet_id"] == wallet.id
        assert body["user_id"] == alice_id
        assert body["currency"] == "USD"
        assert Decimal(body["balance"]) == Decimal("100.00")
        assert body["is_locked"] is False

    async def test_never_returns_another_users_wallet(
        self, client: AsyncClient, wallet: WalletRecord, bob: Tuple[str, str]
    ) -> None:
        """Alice has a wallet; Bob does not. Bob's own `GET /wallet`
        must 404 — never fall back to someone else's wallet — since
        the lookup is keyed by the caller's own id, not an arbitrary
        wallet id."""
        _bob_id, bob_token = bob
        response = await client.get(
            "/api/v1/wallet", headers=_auth_headers(bob_token)
        )
        assert response.status_code == 404

    async def test_returns_401_without_a_token(
        self, client: AsyncClient, wallet: WalletRecord
    ) -> None:
        response = await client.get("/api/v1/wallet")
        assert response.status_code in (401, 403)

    async def test_returns_401_with_a_malformed_token(
        self, client: AsyncClient, wallet: WalletRecord
    ) -> None:
        response = await client.get(
            "/api/v1/wallet", headers=_auth_headers("not-a-real-jwt")
        )
        assert response.status_code == 401


class TestGetBalance:
    async def test_returns_wallet_balance(
        self, client: AsyncClient, wallet: WalletRecord, alice: Tuple[str, str]
    ) -> None:
        _alice_id, alice_token = alice
        response = await client.get(
            f"/api/v1/wallet/{wallet.id}/balance", headers=_auth_headers(alice_token)
        )

        assert response.status_code == 200
        body = response.json()
        assert body["wallet_id"] == wallet.id
        assert body["user_id"] == wallet.user_id
        assert body["currency"] == "USD"
        assert Decimal(body["balance"]) == Decimal("100.00")
        assert body["is_locked"] is False

    async def test_returns_404_for_missing_wallet(
        self, client: AsyncClient, alice: Tuple[str, str]
    ) -> None:
        _alice_id, alice_token = alice
        response = await client.get(
            "/api/v1/wallet/does-not-exist/balance", headers=_auth_headers(alice_token)
        )
        assert response.status_code == 404

    async def test_returns_401_without_a_token(
        self, client: AsyncClient, wallet: WalletRecord
    ) -> None:
        response = await client.get(f"/api/v1/wallet/{wallet.id}/balance")
        assert response.status_code in (401, 403)

    async def test_returns_401_with_a_malformed_token(
        self, client: AsyncClient, wallet: WalletRecord
    ) -> None:
        response = await client.get(
            f"/api/v1/wallet/{wallet.id}/balance",
            headers=_auth_headers("not-a-real-jwt"),
        )
        assert response.status_code == 401

    async def test_returns_403_when_wallet_belongs_to_another_user(
        self, client: AsyncClient, wallet: WalletRecord, bob: Tuple[str, str]
    ) -> None:
        """The core cross-user security guarantee: Bob can never read
        Alice's wallet, no matter how valid his own token is."""
        _bob_id, bob_token = bob
        response = await client.get(
            f"/api/v1/wallet/{wallet.id}/balance", headers=_auth_headers(bob_token)
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Forbidden"


class TestDeposit:
    async def test_credits_wallet_and_returns_new_balance(
        self, client: AsyncClient, wallet: WalletRecord, alice: Tuple[str, str]
    ) -> None:
        _alice_id, alice_token = alice
        response = await client.post(
            "/api/v1/wallet/deposit",
            json={"wallet_id": wallet.id, "amount": "25.50"},
            headers=_auth_headers(alice_token),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["transaction_type"] == "deposit"
        assert Decimal(body["new_balance"]) == Decimal("125.50")

    async def test_rejects_zero_amount_with_422(
        self, client: AsyncClient, wallet: WalletRecord, alice: Tuple[str, str]
    ) -> None:
        _alice_id, alice_token = alice
        response = await client.post(
            "/api/v1/wallet/deposit",
            json={"wallet_id": wallet.id, "amount": "0"},
            headers=_auth_headers(alice_token),
        )
        assert response.status_code == 422

    async def test_returns_404_for_missing_wallet(
        self, client: AsyncClient, alice: Tuple[str, str]
    ) -> None:
        _alice_id, alice_token = alice
        response = await client.post(
            "/api/v1/wallet/deposit",
            json={"wallet_id": "does-not-exist", "amount": "10"},
            headers=_auth_headers(alice_token),
        )
        assert response.status_code == 404

    async def test_returns_401_without_a_token(
        self, client: AsyncClient, wallet: WalletRecord
    ) -> None:
        response = await client.post(
            "/api/v1/wallet/deposit", json={"wallet_id": wallet.id, "amount": "10"}
        )
        assert response.status_code in (401, 403)

    async def test_returns_403_when_wallet_belongs_to_another_user(
        self, client: AsyncClient, wallet: WalletRecord, bob: Tuple[str, str]
    ) -> None:
        """Bob must never be able to deposit into — or otherwise
        discover the existence of — Alice's wallet."""
        _bob_id, bob_token = bob
        response = await client.post(
            "/api/v1/wallet/deposit",
            json={"wallet_id": wallet.id, "amount": "10"},
            headers=_auth_headers(bob_token),
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Forbidden"

    async def test_returns_423_for_locked_wallet(
        self, client: AsyncClient, session_factory: async_sessionmaker, alice: Tuple[str, str]
    ) -> None:
        alice_id, alice_token = alice
        locked_wallet = await _create_wallet(session_factory, user_id=alice_id, is_locked=True)

        response = await client.post(
            "/api/v1/wallet/deposit",
            json={"wallet_id": locked_wallet.id, "amount": "10"},
            headers=_auth_headers(alice_token),
        )
        assert response.status_code == 423


class TestWithdraw:
    async def test_debits_wallet_and_returns_new_balance(
        self, client: AsyncClient, wallet: WalletRecord, alice: Tuple[str, str]
    ) -> None:
        _alice_id, alice_token = alice
        response = await client.post(
            "/api/v1/wallet/withdraw",
            json={"wallet_id": wallet.id, "amount": "40.00"},
            headers=_auth_headers(alice_token),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["transaction_type"] == "withdrawal"
        assert Decimal(body["new_balance"]) == Decimal("60.00")

    async def test_returns_400_for_insufficient_funds(
        self, client: AsyncClient, wallet: WalletRecord, alice: Tuple[str, str]
    ) -> None:
        _alice_id, alice_token = alice
        response = await client.post(
            "/api/v1/wallet/withdraw",
            json={"wallet_id": wallet.id, "amount": "1000.00"},
            headers=_auth_headers(alice_token),
        )
        assert response.status_code == 400

        balance_response = await client.get(
            f"/api/v1/wallet/{wallet.id}/balance", headers=_auth_headers(alice_token)
        )
        assert Decimal(balance_response.json()["balance"]) == Decimal("100.00")

    async def test_rejects_non_positive_amount_with_422(
        self, client: AsyncClient, wallet: WalletRecord, alice: Tuple[str, str]
    ) -> None:
        _alice_id, alice_token = alice
        response = await client.post(
            "/api/v1/wallet/withdraw",
            json={"wallet_id": wallet.id, "amount": "0"},
            headers=_auth_headers(alice_token),
        )
        assert response.status_code == 422

    async def test_returns_403_when_wallet_belongs_to_another_user(
        self,
        client: AsyncClient,
        wallet: WalletRecord,
        bob: Tuple[str, str],
        session_factory: async_sessionmaker,
    ) -> None:
        """Bob must never be able to withdraw from Alice's wallet."""
        _bob_id, bob_token = bob
        response = await client.post(
            "/api/v1/wallet/withdraw",
            json={"wallet_id": wallet.id, "amount": "10"},
            headers=_auth_headers(bob_token),
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Forbidden"

        # And the balance must be completely unaffected by the
        # rejected attempt (confirmed directly via the repository,
        # since fetching it over the API here would itself require
        # Alice's own token, which is out of scope for this test).
        async with UnitOfWork(session_factory) as uow:
            reloaded = await uow.wallets.get_wallet_by_id(wallet.id)
        assert reloaded is not None
        assert reloaded.balance == Decimal("100.00")

    async def test_returns_423_for_locked_wallet(
        self, client: AsyncClient, session_factory: async_sessionmaker, alice: Tuple[str, str]
    ) -> None:
        alice_id, alice_token = alice
        locked_wallet = await _create_wallet(
            session_factory, user_id=alice_id, balance=Decimal("50"), is_locked=True
        )

        response = await client.post(
            "/api/v1/wallet/withdraw",
            json={"wallet_id": locked_wallet.id, "amount": "10"},
            headers=_auth_headers(alice_token),
        )
        assert response.status_code == 423


class TestTransfer:
    async def test_moves_funds_between_wallets(
        self,
        client: AsyncClient,
        wallet: WalletRecord,
        alice: Tuple[str, str],
        bob: Tuple[str, str],
        session_factory: async_sessionmaker,
    ) -> None:
        alice_id, alice_token = alice
        bob_id, _bob_token = bob
        destination = await _create_wallet(session_factory, user_id=bob_id)

        response = await client.post(
            "/api/v1/wallet/transfer",
            json={
                "source_wallet_id": wallet.id,
                "destination_wallet_id": destination.id,
                "amount": "30.00",
            },
            headers=_auth_headers(alice_token),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert Decimal(body["new_source_balance"]) == Decimal("70.00")
        assert Decimal(body["new_destination_balance"]) == Decimal("30.00")

    async def test_destination_wallet_ownership_is_not_required(
        self,
        client: AsyncClient,
        wallet: WalletRecord,
        alice: Tuple[str, str],
        bob: Tuple[str, str],
        session_factory: async_sessionmaker,
    ) -> None:
        """Explicitly documents the one deliberate exception to
        "you may only act on your own wallet": Alice may transfer
        funds *to* Bob's wallet, even though she does not own it —
        that asymmetry is the entire point of a transfer."""
        alice_id, alice_token = alice
        bob_id, _bob_token = bob
        bobs_wallet = await _create_wallet(session_factory, user_id=bob_id)

        response = await client.post(
            "/api/v1/wallet/transfer",
            json={
                "source_wallet_id": wallet.id,
                "destination_wallet_id": bobs_wallet.id,
                "amount": "15.00",
            },
            headers=_auth_headers(alice_token),
        )
        assert response.status_code == 200

    async def test_returns_403_when_source_wallet_belongs_to_another_user(
        self,
        client: AsyncClient,
        wallet: WalletRecord,
        alice: Tuple[str, str],
        bob: Tuple[str, str],
        session_factory: async_sessionmaker,
    ) -> None:
        """The critical transfer-specific security guarantee: Bob
        cannot initiate a transfer *out of* Alice's wallet just by
        naming it as the source — even though he could legitimately
        name it as a *destination*."""
        _alice_id, _alice_token = alice
        bob_id, bob_token = bob
        bobs_wallet = await _create_wallet(session_factory, user_id=bob_id, balance=Decimal("50"))

        response = await client.post(
            "/api/v1/wallet/transfer",
            json={
                "source_wallet_id": wallet.id,  # Alice's wallet
                "destination_wallet_id": bobs_wallet.id,
                "amount": "10.00",
            },
            headers=_auth_headers(bob_token),
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Forbidden"

    async def test_returns_400_for_insufficient_funds(
        self,
        client: AsyncClient,
        wallet: WalletRecord,
        alice: Tuple[str, str],
        bob: Tuple[str, str],
        session_factory: async_sessionmaker,
    ) -> None:
        _alice_id, alice_token = alice
        bob_id, _bob_token = bob
        destination = await _create_wallet(session_factory, user_id=bob_id)

        response = await client.post(
            "/api/v1/wallet/transfer",
            json={
                "source_wallet_id": wallet.id,
                "destination_wallet_id": destination.id,
                "amount": "1000.00",
            },
            headers=_auth_headers(alice_token),
        )
        assert response.status_code == 400

    async def test_returns_404_when_destination_missing(
        self, client: AsyncClient, wallet: WalletRecord, alice: Tuple[str, str]
    ) -> None:
        _alice_id, alice_token = alice
        response = await client.post(
            "/api/v1/wallet/transfer",
            json={
                "source_wallet_id": wallet.id,
                "destination_wallet_id": "does-not-exist",
                "amount": "10.00",
            },
            headers=_auth_headers(alice_token),
        )
        assert response.status_code == 404

    async def test_returns_401_without_a_token(
        self, client: AsyncClient, wallet: WalletRecord, bob: Tuple[str, str], session_factory: async_sessionmaker
    ) -> None:
        bob_id, _bob_token = bob
        destination = await _create_wallet(session_factory, user_id=bob_id)

        response = await client.post(
            "/api/v1/wallet/transfer",
            json={
                "source_wallet_id": wallet.id,
                "destination_wallet_id": destination.id,
                "amount": "10.00",
            },
        )
        assert response.status_code in (401, 403)


class TestOpenApiDocumentation:
    async def test_every_wallet_endpoint_has_a_summary_and_description(
        self, app: FastAPI
    ) -> None:
        schema = app.openapi()
        wallet_paths = {
            path: methods
            for path, methods in schema["paths"].items()
            if path.startswith("/api/v1/wallet")
        }
        assert len(wallet_paths) == 5

        for path, methods in wallet_paths.items():
            for method, operation in methods.items():
                assert operation.get("summary"), f"{method.upper()} {path} has no summary"
                assert operation.get(
                    "description"
                ), f"{method.upper()} {path} has no description"
                assert "responses" in operation
                # Every wallet endpoint requires authentication.
                assert operation.get("security"), f"{method.upper()} {path} has no security requirement"
