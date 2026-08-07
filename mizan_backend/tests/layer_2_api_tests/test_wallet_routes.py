"""End-to-end tests for the Digital Wallet's Layer 2 HTTP routes.

Uses `httpx.AsyncClient` over `ASGITransport` inside fully async test
functions — rather than Starlette's synchronous `TestClient` — so the
app, its `WalletController`/`UnitOfWork`, the HTTP requests, and any
direct database seeding all share the *same* event loop (the one
pytest-asyncio provides for the test coroutine). Mixing an
externally-built async engine with a separately-threaded test client
loop has previously caused real "attached to a different loop" hangs
elsewhere in this codebase; this approach avoids that class of bug
entirely rather than working around it.

There is no `POST /wallet` creation endpoint in this API surface (per
the routes actually requested), so test wallets are seeded directly
through `WalletRepository`/`UnitOfWork`, exactly as some other part of
the system (e.g. account provisioning) would in production.
"""
from __future__ import annotations

from decimal import Decimal
from typing import AsyncIterator

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.layer_2_api.controllers.wallet_controller import WalletController
from src.layer_2_api.main_router import api_router
from src.layer_3_business.wallet.wallet_service import WalletService
from src.layer_4_data_access.repositories.wallet_repository import WalletRecord
from src.layer_4_data_access.uow.transaction_manager import UnitOfWork
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory


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
    return application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def _seed_wallet(
    session_factory: async_sessionmaker,
    *,
    owner_id: str = "alice",
    currency: str = "USD",
    balance: Decimal = Decimal("0"),
    is_locked: bool = False,
) -> WalletRecord:
    async with UnitOfWork(session_factory) as uow:
        wallet = await uow.wallets.create_wallet(owner_id=owner_id, currency=currency)
        if balance != Decimal("0"):
            wallet = await uow.wallets.update_wallet_balance(
                wallet.id, balance, expected_version=wallet.version
            )
        if is_locked:
            wallet = await uow.wallets.set_wallet_locked(wallet.id, is_locked=True)
        await uow.commit()
    return wallet


@pytest_asyncio.fixture
async def wallet(session_factory: async_sessionmaker) -> WalletRecord:
    return await _seed_wallet(session_factory, balance=Decimal("100.00"))


class TestGetBalance:
    async def test_returns_wallet_balance(
        self, client: AsyncClient, wallet: WalletRecord
    ) -> None:
        response = await client.get(f"/api/v1/wallet/{wallet.id}/balance")

        assert response.status_code == 200
        body = response.json()
        assert body["wallet_id"] == wallet.id
        assert body["owner_id"] == "alice"
        assert body["currency"] == "USD"
        assert Decimal(body["balance"]) == Decimal("100.00")
        assert body["is_locked"] is False

    async def test_returns_404_for_missing_wallet(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/wallet/does-not-exist/balance")
        assert response.status_code == 404
        assert "does-not-exist" in response.json()["detail"]


class TestDeposit:
    async def test_credits_wallet_and_returns_new_balance(
        self, client: AsyncClient, wallet: WalletRecord
    ) -> None:
        response = await client.post(
            "/api/v1/wallet/deposit",
            json={"wallet_id": wallet.id, "amount": "25.50"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["transaction_type"] == "deposit"
        assert Decimal(body["new_balance"]) == Decimal("125.50")

        balance_response = await client.get(f"/api/v1/wallet/{wallet.id}/balance")
        assert Decimal(balance_response.json()["balance"]) == Decimal("125.50")

    async def test_rejects_zero_amount_with_422(
        self, client: AsyncClient, wallet: WalletRecord
    ) -> None:
        response = await client.post(
            "/api/v1/wallet/deposit", json={"wallet_id": wallet.id, "amount": "0"}
        )
        assert response.status_code == 422

    async def test_rejects_negative_amount_with_422(
        self, client: AsyncClient, wallet: WalletRecord
    ) -> None:
        response = await client.post(
            "/api/v1/wallet/deposit", json={"wallet_id": wallet.id, "amount": "-5"}
        )
        assert response.status_code == 422

    async def test_returns_404_for_missing_wallet(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/wallet/deposit",
            json={"wallet_id": "does-not-exist", "amount": "10"},
        )
        assert response.status_code == 404

    async def test_returns_423_for_locked_wallet(
        self, client: AsyncClient, session_factory: async_sessionmaker
    ) -> None:
        locked_wallet = await _seed_wallet(
            session_factory, owner_id="bob", is_locked=True
        )
        response = await client.post(
            "/api/v1/wallet/deposit",
            json={"wallet_id": locked_wallet.id, "amount": "10"},
        )
        assert response.status_code == 423


class TestWithdraw:
    async def test_debits_wallet_and_returns_new_balance(
        self, client: AsyncClient, wallet: WalletRecord
    ) -> None:
        response = await client.post(
            "/api/v1/wallet/withdraw",
            json={"wallet_id": wallet.id, "amount": "40.00"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["transaction_type"] == "withdrawal"
        assert Decimal(body["new_balance"]) == Decimal("60.00")

    async def test_returns_400_for_insufficient_funds(
        self, client: AsyncClient, wallet: WalletRecord
    ) -> None:
        response = await client.post(
            "/api/v1/wallet/withdraw",
            json={"wallet_id": wallet.id, "amount": "1000.00"},
        )
        assert response.status_code == 400

        balance_response = await client.get(f"/api/v1/wallet/{wallet.id}/balance")
        assert Decimal(balance_response.json()["balance"]) == Decimal("100.00")

    async def test_rejects_non_positive_amount_with_422(
        self, client: AsyncClient, wallet: WalletRecord
    ) -> None:
        response = await client.post(
            "/api/v1/wallet/withdraw", json={"wallet_id": wallet.id, "amount": "0"}
        )
        assert response.status_code == 422

    async def test_returns_423_for_locked_wallet(
        self, client: AsyncClient, session_factory: async_sessionmaker
    ) -> None:
        locked_wallet = await _seed_wallet(
            session_factory, owner_id="bob", balance=Decimal("50"), is_locked=True
        )
        response = await client.post(
            "/api/v1/wallet/withdraw",
            json={"wallet_id": locked_wallet.id, "amount": "10"},
        )
        assert response.status_code == 423


class TestTransfer:
    async def test_moves_funds_between_wallets(
        self, client: AsyncClient, wallet: WalletRecord, session_factory: async_sessionmaker
    ) -> None:
        destination = await _seed_wallet(session_factory, owner_id="bob")

        response = await client.post(
            "/api/v1/wallet/transfer",
            json={
                "source_wallet_id": wallet.id,
                "destination_wallet_id": destination.id,
                "amount": "30.00",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert Decimal(body["new_source_balance"]) == Decimal("70.00")
        assert Decimal(body["new_destination_balance"]) == Decimal("30.00")

    async def test_returns_400_for_insufficient_funds(
        self, client: AsyncClient, wallet: WalletRecord, session_factory: async_sessionmaker
    ) -> None:
        destination = await _seed_wallet(session_factory, owner_id="bob")

        response = await client.post(
            "/api/v1/wallet/transfer",
            json={
                "source_wallet_id": wallet.id,
                "destination_wallet_id": destination.id,
                "amount": "1000.00",
            },
        )
        assert response.status_code == 400

    async def test_returns_404_when_destination_missing(
        self, client: AsyncClient, wallet: WalletRecord
    ) -> None:
        response = await client.post(
            "/api/v1/wallet/transfer",
            json={
                "source_wallet_id": wallet.id,
                "destination_wallet_id": "does-not-exist",
                "amount": "10.00",
            },
        )
        assert response.status_code == 404

    async def test_rejects_non_positive_amount_with_422(
        self, client: AsyncClient, wallet: WalletRecord, session_factory: async_sessionmaker
    ) -> None:
        destination = await _seed_wallet(session_factory, owner_id="bob")

        response = await client.post(
            "/api/v1/wallet/transfer",
            json={
                "source_wallet_id": wallet.id,
                "destination_wallet_id": destination.id,
                "amount": "0",
            },
        )
        assert response.status_code == 422

    async def test_returns_423_when_source_is_locked(
        self, client: AsyncClient, session_factory: async_sessionmaker
    ) -> None:
        source = await _seed_wallet(
            session_factory, owner_id="alice", balance=Decimal("100"), is_locked=True
        )
        destination = await _seed_wallet(session_factory, owner_id="bob")

        response = await client.post(
            "/api/v1/wallet/transfer",
            json={
                "source_wallet_id": source.id,
                "destination_wallet_id": destination.id,
                "amount": "10.00",
            },
        )
        assert response.status_code == 423


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
        assert len(wallet_paths) == 4

        for path, methods in wallet_paths.items():
            for method, operation in methods.items():
                assert operation.get("summary"), f"{method.upper()} {path} has no summary"
                assert operation.get(
                    "description"
                ), f"{method.upper()} {path} has no description"
                assert "responses" in operation
