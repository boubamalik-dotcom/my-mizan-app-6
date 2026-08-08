"""End-to-end tests for the Audit API's Layer 2 routes and the RBAC
guard protecting them.

Follows `test_wallet_routes.py`'s harness: `httpx.AsyncClient` over
`ASGITransport` inside async tests, so the app, its controllers, and
every request share one event loop.

The negative cases carry most of the weight here. An audit endpoint
exposes every user's financial history, so "an ordinary user is
refused" matters more than "an auditor succeeds", and "an auditor
cannot escalate their own role" matters most of all.
"""
from __future__ import annotations

from decimal import Decimal
from typing import AsyncIterator, Dict, Tuple

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.layer_2_api.audit.audit_controller import AuditController
from src.layer_2_api.auth.auth_controller import AuthController
from src.layer_2_api.controllers.wallet_controller import WalletController
from src.layer_2_api.main_router import api_router
from src.layer_3_business.audit.audit_service import MAX_PAGE_SIZE, AuditService
from src.layer_3_business.auth.auth_service import AuthService
from src.layer_3_business.authz.roles import Role
from src.layer_3_business.wallet.wallet_service import WalletService
from src.layer_4_data_access.uow.transaction_manager import UnitOfWork
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory

TEST_SECRET_KEY = "test-secret-key-at-least-32-bytes-long-for-hmac-sha256"
TEST_PASSWORD = "correct-horse-battery-staple"
BOOTSTRAP_ADMIN = "compliance@example.com"


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
        bootstrap_admin_emails=[BOOTSTRAP_ADMIN],
    )
    application.state.audit_controller = AuditController(
        audit_service=AuditService(),
        unit_of_work_factory=unit_of_work_factory,
    )
    return application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


def _auth(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _register_and_login(
    client: AsyncClient, *, email: str
) -> Tuple[str, str, str]:
    """Registers and logs in, returning `(user_id, token, role)`."""
    registered = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": TEST_PASSWORD, "full_name": "Test User"},
    )
    assert registered.status_code == 201, registered.text

    logged_in = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD}
    )
    assert logged_in.status_code == 200, logged_in.text

    body = registered.json()
    return body["id"], logged_in.json()["access_token"], body["role"]


async def _admin(client: AsyncClient) -> str:
    """The bootstrap admin's token."""
    _, token, role = await _register_and_login(client, email=BOOTSTRAP_ADMIN)
    assert role == Role.ADMIN.value
    return token


async def _auditor(client: AsyncClient, *, email: str = "auditor@example.com") -> str:
    """Registers a user and has the admin promote them to auditor."""
    user_id, token, _ = await _register_and_login(client, email=email)
    admin_token = await _admin(client)

    promoted = await client.patch(
        f"/api/v1/audit/users/{user_id}/role",
        json={"role": "auditor"},
        headers=_auth(admin_token),
    )
    assert promoted.status_code == 200, promoted.text
    return token


async def _wallet_with_history(
    client: AsyncClient, *, email: str
) -> Tuple[str, str, str]:
    """Creates a wallet, deposits 1000 and withdraws 250.

    Returns `(user_id, wallet_id, token)`.
    """
    user_id, token, _ = await _register_and_login(client, email=email)

    created = await client.post(
        "/api/v1/wallet", json={"currency": "DZD"}, headers=_auth(token)
    )
    assert created.status_code == 201, created.text
    wallet_id = created.json()["wallet_id"]

    deposited = await client.post(
        "/api/v1/wallet/deposit",
        json={"wallet_id": wallet_id, "amount": "1000"},
        headers=_auth(token),
    )
    assert deposited.status_code == 200, deposited.text

    withdrawn = await client.post(
        "/api/v1/wallet/withdraw",
        json={"wallet_id": wallet_id, "amount": "250"},
        headers=_auth(token),
    )
    assert withdrawn.status_code == 200, withdrawn.text

    return user_id, wallet_id, token


class TestRegistrationAssignsRoles:
    async def test_an_ordinary_registration_is_a_plain_user(
        self, client: AsyncClient
    ) -> None:
        _, _, role = await _register_and_login(client, email="someone@example.com")
        assert role == Role.USER.value

    async def test_a_bootstrap_address_becomes_an_admin(
        self, client: AsyncClient
    ) -> None:
        # Without this the first admin could never exist, since
        # granting a role needs a permission only an admin holds.
        _, _, role = await _register_and_login(client, email=BOOTSTRAP_ADMIN)
        assert role == Role.ADMIN.value

    async def test_the_role_is_reported_on_the_profile_endpoint(
        self, client: AsyncClient
    ) -> None:
        _, token, _ = await _register_and_login(client, email="someone@example.com")

        response = await client.get("/api/v1/auth/me", headers=_auth(token))

        assert response.status_code == 200
        assert response.json()["role"] == Role.USER.value


class TestLedgerAccessIsRoleGated:
    async def test_an_unauthenticated_request_is_rejected(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/v1/audit/ledger")

        # 401, not 403: nobody has identified themselves yet, so
        # re-authenticating is exactly what would help. The 403s below
        # are the opposite case — a known caller who may not do this.
        assert response.status_code == 401

    async def test_an_ordinary_user_is_forbidden(self, client: AsyncClient) -> None:
        # Even for their own wallet: the ledger endpoint spans every
        # user, and their own history is available via the Wallet API.
        _, token, _ = await _register_and_login(client, email="user@example.com")

        response = await client.get("/api/v1/audit/ledger", headers=_auth(token))

        assert response.status_code == 403
        assert "audit:read_ledger" in response.json()["detail"]

    async def test_an_auditor_is_allowed(self, client: AsyncClient) -> None:
        token = await _auditor(client)

        response = await client.get("/api/v1/audit/ledger", headers=_auth(token))

        assert response.status_code == 200

    async def test_an_admin_is_allowed(self, client: AsyncClient) -> None:
        token = await _admin(client)

        response = await client.get("/api/v1/audit/ledger", headers=_auth(token))

        assert response.status_code == 200

    async def test_every_audit_route_refuses_an_ordinary_user(
        self, client: AsyncClient
    ) -> None:
        # Written as a sweep so a newly added audit route that forgets
        # its guard fails here rather than shipping wide open.
        _, token, _ = await _register_and_login(client, email="user@example.com")
        headers = _auth(token)

        responses = [
            await client.get("/api/v1/audit/ledger", headers=headers),
            await client.get("/api/v1/audit/roles", headers=headers),
            await client.get("/api/v1/audit/wallets/any/integrity", headers=headers),
            await client.get("/api/v1/audit/transfers/any", headers=headers),
            await client.get("/api/v1/audit/users/any", headers=headers),
            await client.patch(
                "/api/v1/audit/users/any/role",
                json={"role": "admin"},
                headers=headers,
            ),
        ]

        assert [r.status_code for r in responses] == [403] * 6


class TestAuditorCannotEscalate:
    """The separation that makes read-only oversight meaningful."""

    async def test_an_auditor_cannot_grant_roles(
        self, client: AsyncClient
    ) -> None:
        victim_id, _, _ = await _register_and_login(client, email="victim@example.com")
        auditor_token = await _auditor(client)

        response = await client.patch(
            f"/api/v1/audit/users/{victim_id}/role",
            json={"role": "admin"},
            headers=_auth(auditor_token),
        )

        assert response.status_code == 403
        assert "users:manage_roles" in response.json()["detail"]

    async def test_an_auditor_cannot_promote_themselves(
        self, client: AsyncClient
    ) -> None:
        auditor_id, auditor_token, _ = await _register_and_login(
            client, email="selfpromoter@example.com"
        )
        admin_token = await _admin(client)
        await client.patch(
            f"/api/v1/audit/users/{auditor_id}/role",
            json={"role": "auditor"},
            headers=_auth(admin_token),
        )

        response = await client.patch(
            f"/api/v1/audit/users/{auditor_id}/role",
            json={"role": "admin"},
            headers=_auth(auditor_token),
        )

        assert response.status_code == 403

    async def test_an_auditor_cannot_read_who_holds_which_role(
        self, client: AsyncClient
    ) -> None:
        someone_id, _, _ = await _register_and_login(client, email="someone@example.com")
        auditor_token = await _auditor(client)

        response = await client.get(
            f"/api/v1/audit/users/{someone_id}", headers=_auth(auditor_token)
        )

        assert response.status_code == 403


class TestRoleAdministration:
    async def test_an_admin_can_promote_a_user_to_auditor(
        self, client: AsyncClient
    ) -> None:
        user_id, _, _ = await _register_and_login(client, email="promote@example.com")
        admin_token = await _admin(client)

        response = await client.patch(
            f"/api/v1/audit/users/{user_id}/role",
            json={"role": "auditor"},
            headers=_auth(admin_token),
        )

        assert response.status_code == 200
        assert response.json()["role"] == "auditor"

    async def test_a_promotion_takes_effect_on_the_next_request(
        self, client: AsyncClient
    ) -> None:
        user_id, user_token, _ = await _register_and_login(
            client, email="promote@example.com"
        )
        refused = await client.get("/api/v1/audit/ledger", headers=_auth(user_token))
        assert refused.status_code == 403

        admin_token = await _admin(client)
        await client.patch(
            f"/api/v1/audit/users/{user_id}/role",
            json={"role": "auditor"},
            headers=_auth(admin_token),
        )

        # The same, still-valid token now passes: the role is resolved
        # from the database per request, not baked into the JWT, so a
        # revocation takes effect immediately too.
        allowed = await client.get("/api/v1/audit/ledger", headers=_auth(user_token))
        assert allowed.status_code == 200

    async def test_a_demotion_also_takes_effect_immediately(
        self, client: AsyncClient
    ) -> None:
        user_id, user_token, _ = await _register_and_login(
            client, email="demote@example.com"
        )
        admin_token = await _admin(client)
        await client.patch(
            f"/api/v1/audit/users/{user_id}/role",
            json={"role": "auditor"},
            headers=_auth(admin_token),
        )
        assert (
            await client.get("/api/v1/audit/ledger", headers=_auth(user_token))
        ).status_code == 200

        await client.patch(
            f"/api/v1/audit/users/{user_id}/role",
            json={"role": "user"},
            headers=_auth(admin_token),
        )

        assert (
            await client.get("/api/v1/audit/ledger", headers=_auth(user_token))
        ).status_code == 403

    async def test_an_unrecognised_role_is_rejected(
        self, client: AsyncClient
    ) -> None:
        user_id, _, _ = await _register_and_login(client, email="promote@example.com")
        admin_token = await _admin(client)

        response = await client.patch(
            f"/api/v1/audit/users/{user_id}/role",
            json={"role": "superuser"},
            headers=_auth(admin_token),
        )

        assert response.status_code == 422

    async def test_promoting_an_unknown_user_is_a_404(
        self, client: AsyncClient
    ) -> None:
        admin_token = await _admin(client)

        response = await client.patch(
            "/api/v1/audit/users/does-not-exist/role",
            json={"role": "auditor"},
            headers=_auth(admin_token),
        )

        assert response.status_code == 404


class TestLedgerInspection:
    async def test_returns_the_entries_a_wallet_s_activity_produced(
        self, client: AsyncClient
    ) -> None:
        user_id, wallet_id, _ = await _wallet_with_history(
            client, email="customer@example.com"
        )
        auditor_token = await _auditor(client)

        response = await client.get(
            "/api/v1/audit/ledger",
            params={"wallet_id": wallet_id},
            headers=_auth(auditor_token),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert [e["transaction_type"] for e in body["entries"]] == [
            "deposit",
            "withdrawal",
        ]
        # Direction is recorded, which is what makes the ledger
        # replayable into a balance.
        assert [e["direction"] for e in body["entries"]] == ["credit", "debit"]
        assert {e["user_id"] for e in body["entries"]} == {user_id}

    async def test_filters_by_user(self, client: AsyncClient) -> None:
        alice_id, _, _ = await _wallet_with_history(client, email="alice@example.com")
        await _wallet_with_history(client, email="bob@example.com")
        auditor_token = await _auditor(client)

        response = await client.get(
            "/api/v1/audit/ledger",
            params={"user_id": alice_id},
            headers=_auth(auditor_token),
        )

        assert {e["user_id"] for e in response.json()["entries"]} == {alice_id}

    async def test_paginates_and_reports_the_total(
        self, client: AsyncClient
    ) -> None:
        _, wallet_id, _ = await _wallet_with_history(client, email="c@example.com")
        auditor_token = await _auditor(client)

        response = await client.get(
            "/api/v1/audit/ledger",
            params={"wallet_id": wallet_id, "limit": 1},
            headers=_auth(auditor_token),
        )

        body = response.json()
        assert len(body["entries"]) == 1
        assert body["total"] == 2
        assert body["limit"] == 1

    async def test_rejects_a_page_size_above_the_ceiling(
        self, client: AsyncClient
    ) -> None:
        auditor_token = await _auditor(client)

        response = await client.get(
            "/api/v1/audit/ledger",
            params={"limit": MAX_PAGE_SIZE + 1},
            headers=_auth(auditor_token),
        )

        assert response.status_code == 422

    async def test_rejects_an_inverted_time_window(
        self, client: AsyncClient
    ) -> None:
        auditor_token = await _auditor(client)

        response = await client.get(
            "/api/v1/audit/ledger",
            params={
                "occurred_from": "2026-06-01T00:00:00",
                "occurred_to": "2026-01-01T00:00:00",
            },
            headers=_auth(auditor_token),
        )

        assert response.status_code == 422

    async def test_lists_the_access_control_policy(
        self, client: AsyncClient
    ) -> None:
        # Served from the same table the guards enforce, so it cannot
        # drift away from the code the way documentation would.
        auditor_token = await _auditor(client)

        response = await client.get("/api/v1/audit/roles", headers=_auth(auditor_token))

        assert response.status_code == 200
        policy = {row["role"]: row["permissions"] for row in response.json()}
        assert policy["user"] == []
        assert "users:manage_roles" in policy["admin"]
        assert "users:manage_roles" not in policy["auditor"]


class TestIntegrityVerification:
    async def test_a_healthy_wallet_reconciles(self, client: AsyncClient) -> None:
        _, wallet_id, _ = await _wallet_with_history(client, email="c@example.com")
        auditor_token = await _auditor(client)

        response = await client.get(
            f"/api/v1/audit/wallets/{wallet_id}/integrity",
            headers=_auth(auditor_token),
        )

        assert response.status_code == 200
        body = response.json()
        assert Decimal(body["recorded_balance"]) == Decimal("750")
        assert Decimal(body["computed_balance"]) == Decimal("750")
        assert Decimal(body["discrepancy"]) == Decimal("0")
        assert body["entries_examined"] == 2
        assert body["unverifiable_entries"] == 0
        assert body["is_balanced"] is True

    async def test_both_sides_of_a_transfer_still_reconcile(
        self, client: AsyncClient
    ) -> None:
        # The case the direction column exists for: before it, the
        # sender's ledger replayed to +100 instead of -100 and every
        # transferring wallet looked corrupt.
        _, source_id, source_token = await _wallet_with_history(
            client, email="sender@example.com"
        )
        _, destination_id, _ = await _wallet_with_history(
            client, email="receiver@example.com"
        )

        transferred = await client.post(
            "/api/v1/wallet/transfer",
            json={
                "source_wallet_id": source_id,
                "destination_wallet_id": destination_id,
                "amount": "100",
            },
            headers=_auth(source_token),
        )
        assert transferred.status_code == 200, transferred.text

        auditor_token = await _auditor(client)
        for wallet_id in (source_id, destination_id):
            response = await client.get(
                f"/api/v1/audit/wallets/{wallet_id}/integrity",
                headers=_auth(auditor_token),
            )
            body = response.json()
            assert body["is_balanced"] is True, (wallet_id, body)

    async def test_catches_a_balance_changed_behind_the_ledger_s_back(
        self, client: AsyncClient, session_factory: async_sessionmaker
    ) -> None:
        """The scenario this whole feature exists for.

        Someone edits a balance directly in the database — bypassing
        the API, and so leaving no ledger entry behind. The ledger
        cannot be rewritten to match (it is append-only and the ORM
        actively rejects an UPDATE), so replaying it no longer
        reproduces the balance, and the inspection says so.
        """
        _, wallet_id, _ = await _wallet_with_history(client, email="c@example.com")

        async with session_factory() as session:
            await session.execute(
                text("UPDATE wallets SET balance = :balance WHERE id = :id"),
                {"balance": "9999", "id": wallet_id},
            )
            await session.commit()

        auditor_token = await _auditor(client)
        response = await client.get(
            f"/api/v1/audit/wallets/{wallet_id}/integrity",
            headers=_auth(auditor_token),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["is_balanced"] is False
        assert Decimal(body["recorded_balance"]) == Decimal("9999")
        assert Decimal(body["computed_balance"]) == Decimal("750")
        assert Decimal(body["discrepancy"]) == Decimal("9249")
        # The entries themselves are untouched, which is the point: the
        # evidence survived the tampering.
        assert body["entries_examined"] == 2

    async def test_a_legacy_entry_makes_the_result_inconclusive_not_wrong(
        self, client: AsyncClient, session_factory: async_sessionmaker
    ) -> None:
        # Simulates a row written before the direction column existed.
        # Such rows cannot be backfilled, so the honest answer is
        # "cannot confirm" rather than a confident number computed from
        # a guess.
        _, wallet_id, _ = await _wallet_with_history(client, email="c@example.com")

        async with session_factory() as session:
            await session.execute(
                text(
                    "UPDATE transaction_ledger SET direction = NULL, "
                    "transaction_type = 'TRANSFER' WHERE wallet_id = :id"
                ),
                {"id": wallet_id},
            )
            await session.commit()

        auditor_token = await _auditor(client)
        response = await client.get(
            f"/api/v1/audit/wallets/{wallet_id}/integrity",
            headers=_auth(auditor_token),
        )

        body = response.json()
        assert body["unverifiable_entries"] == 2
        assert body["is_balanced"] is False

    async def test_an_unknown_wallet_is_a_404(self, client: AsyncClient) -> None:
        auditor_token = await _auditor(client)

        response = await client.get(
            "/api/v1/audit/wallets/does-not-exist/integrity",
            headers=_auth(auditor_token),
        )

        assert response.status_code == 404


class TestTransferReconstruction:
    async def test_returns_both_legs_under_one_reference(
        self, client: AsyncClient
    ) -> None:
        _, source_id, source_token = await _wallet_with_history(
            client, email="sender@example.com"
        )
        _, destination_id, _ = await _wallet_with_history(
            client, email="receiver@example.com"
        )
        await client.post(
            "/api/v1/wallet/transfer",
            json={
                "source_wallet_id": source_id,
                "destination_wallet_id": destination_id,
                "amount": "100",
            },
            headers=_auth(source_token),
        )

        auditor_token = await _auditor(client)
        ledger = await client.get(
            "/api/v1/audit/ledger",
            params={"wallet_id": source_id, "transaction_type": "transfer"},
            headers=_auth(auditor_token),
        )
        reference_id = ledger.json()["entries"][0]["reference_id"]

        response = await client.get(
            f"/api/v1/audit/transfers/{reference_id}", headers=_auth(auditor_token)
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body["entries"]) == 2
        assert {e["direction"] for e in body["entries"]} == {"debit", "credit"}
        assert {e["wallet_id"] for e in body["entries"]} == {source_id, destination_id}
        assert body["is_well_formed"] is True

    async def test_an_unknown_reference_is_a_404(self, client: AsyncClient) -> None:
        auditor_token = await _auditor(client)

        response = await client.get(
            "/api/v1/audit/transfers/no-such-reference", headers=_auth(auditor_token)
        )

        assert response.status_code == 404
