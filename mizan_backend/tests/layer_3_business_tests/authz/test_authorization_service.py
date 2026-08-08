"""Unit tests for the pure Layer 3 authorization rules.

No FastAPI, no SQLAlchemy, no Pydantic, no database, no network — every
test here runs purely in memory, proving `roles.py`,
`authorization_service.py`, and `authz_exceptions.py` are fully
testable in isolation.

For an access-control policy that is worth as much as its weakest
grant, the negative cases below matter more than the positive ones: it
is far more important to prove an auditor *cannot* escalate than that
an admin can.
"""
from __future__ import annotations

import pytest

from src.layer_3_business.authz.authorization_service import AuthorizationService
from src.layer_3_business.authz.authz_exceptions import (
    AuthorizationError,
    InvalidRoleError,
    PermissionDeniedError,
)
from src.layer_3_business.authz.roles import (
    DEFAULT_ROLE,
    ROLE_PERMISSIONS,
    Permission,
    Role,
)


@pytest.fixture
def service() -> AuthorizationService:
    return AuthorizationService()


class TestRoleParsing:
    def test_parses_each_known_role_from_its_value(self) -> None:
        assert Role.parse("user") is Role.USER
        assert Role.parse("auditor") is Role.AUDITOR
        assert Role.parse("admin") is Role.ADMIN

    def test_passes_an_already_parsed_role_through(self) -> None:
        assert Role.parse(Role.AUDITOR) is Role.AUDITOR

    @pytest.mark.parametrize("value", ["superuser", "", "Admin", None, 7])
    def test_rejects_anything_else(self, value: object) -> None:
        # Never falls back to a default: quietly downgrading an
        # unrecognised role would turn a data problem into a security
        # problem, and quietly upgrading it would be worse.
        with pytest.raises(InvalidRoleError):
            Role.parse(value)

    def test_invalid_role_is_an_authorization_error(self) -> None:
        assert issubclass(InvalidRoleError, AuthorizationError)

    def test_a_role_serializes_as_its_plain_value(self) -> None:
        # Matters because the value round-trips through JSON and a
        # database column.
        assert Role.AUDITOR.value == "auditor"
        assert f"{Role.AUDITOR.value}" == "auditor"


class TestPolicyTable:
    def test_every_role_has_an_entry(self) -> None:
        # A role missing from the table would silently hold nothing.
        assert set(ROLE_PERMISSIONS) == set(Role)

    def test_an_ordinary_user_holds_no_elevated_permission(self) -> None:
        assert ROLE_PERMISSIONS[Role.USER] == frozenset()

    def test_an_admin_holds_every_permission(self) -> None:
        assert ROLE_PERMISSIONS[Role.ADMIN] == frozenset(Permission)

    def test_the_default_role_for_a_new_account_is_the_ordinary_one(self) -> None:
        assert DEFAULT_ROLE is Role.USER


class TestAuditorIsReadOnly:
    """The separation that makes the audit trail trustworthy."""

    def test_an_auditor_can_read_the_ledger(
        self, service: AuthorizationService
    ) -> None:
        assert service.has_permission(Role.AUDITOR, Permission.AUDIT_READ_LEDGER)

    def test_an_auditor_can_read_any_wallet(
        self, service: AuthorizationService
    ) -> None:
        assert service.has_permission(Role.AUDITOR, Permission.AUDIT_READ_ANY_WALLET)

    def test_an_auditor_cannot_manage_roles(
        self, service: AuthorizationService
    ) -> None:
        # Otherwise read-only oversight could quietly grant itself
        # write access, and the separation would be worthless.
        assert not service.has_permission(
            Role.AUDITOR, Permission.MANAGE_USER_ROLES
        )

    def test_an_auditor_holds_no_permission_outside_the_audit_family(
        self, service: AuthorizationService
    ) -> None:
        # Written against the whole enum rather than a hard-coded list,
        # so a future permission is denied to auditors by default and
        # granting it has to be a deliberate edit that fails this test.
        for permission in Permission:
            if permission.value.startswith("audit:"):
                continue
            assert not service.has_permission(Role.AUDITOR, permission), permission


class TestOrdinaryUsersHaveNoElevatedAccess:
    @pytest.mark.parametrize("permission", list(Permission))
    def test_a_user_holds_no_permission_at_all(
        self, service: AuthorizationService, permission: Permission
    ) -> None:
        assert not service.has_permission(Role.USER, permission)

    def test_a_user_cannot_read_the_ledger(
        self, service: AuthorizationService
    ) -> None:
        with pytest.raises(PermissionDeniedError):
            service.require_permission(Role.USER, Permission.AUDIT_READ_LEDGER)


class TestRequirePermission:
    def test_returns_silently_when_the_role_holds_it(
        self, service: AuthorizationService
    ) -> None:
        service.require_permission(Role.ADMIN, Permission.MANAGE_USER_ROLES)

    def test_raises_when_it_does_not(self, service: AuthorizationService) -> None:
        # Raising rather than returning a bool is what makes the guard
        # hard to misuse: an ignored return value fails open.
        with pytest.raises(PermissionDeniedError) as exc_info:
            service.require_permission(Role.AUDITOR, Permission.MANAGE_USER_ROLES)

        assert exc_info.value.role is Role.AUDITOR
        assert exc_info.value.permission is Permission.MANAGE_USER_ROLES

    def test_the_message_names_the_role_and_the_permission(
        self, service: AuthorizationService
    ) -> None:
        with pytest.raises(PermissionDeniedError) as exc_info:
            service.require_permission(Role.USER, Permission.AUDIT_READ_LEDGER)

        message = str(exc_info.value)
        assert "user" in message
        assert "audit:read_ledger" in message


class TestCanReadWallet:
    def test_a_user_may_read_their_own_wallet(
        self, service: AuthorizationService
    ) -> None:
        # By ownership, needing no elevated role at all.
        assert service.can_read_wallet(
            role=Role.USER, actor_user_id="u1", owner_user_id="u1"
        )

    def test_a_user_may_not_read_someone_else_s(
        self, service: AuthorizationService
    ) -> None:
        assert not service.can_read_wallet(
            role=Role.USER, actor_user_id="u1", owner_user_id="u2"
        )

    def test_an_auditor_may_read_anyone_s(
        self, service: AuthorizationService
    ) -> None:
        assert service.can_read_wallet(
            role=Role.AUDITOR, actor_user_id="auditor", owner_user_id="u2"
        )

    def test_an_admin_may_read_anyone_s(
        self, service: AuthorizationService
    ) -> None:
        assert service.can_read_wallet(
            role=Role.ADMIN, actor_user_id="admin", owner_user_id="u2"
        )


class TestInitialRoleForNewAccounts:
    def test_an_ordinary_registration_gets_the_default_role(
        self, service: AuthorizationService
    ) -> None:
        assert (
            service.initial_role_for(
                email="someone@example.com", bootstrap_admin_emails=()
            )
            is Role.USER
        )

    def test_a_configured_bootstrap_address_gets_admin(
        self, service: AuthorizationService
    ) -> None:
        # Without this the first admin could never exist: granting a
        # role requires a permission only an admin holds.
        assert (
            service.initial_role_for(
                email="compliance@mizan.app",
                bootstrap_admin_emails=("compliance@mizan.app",),
            )
            is Role.ADMIN
        )

    def test_matching_ignores_case_and_surrounding_whitespace(
        self, service: AuthorizationService
    ) -> None:
        assert (
            service.initial_role_for(
                email="  Compliance@Mizan.App ",
                bootstrap_admin_emails=(" compliance@mizan.app ",),
            )
            is Role.ADMIN
        )

    def test_a_near_miss_does_not_get_admin(
        self, service: AuthorizationService
    ) -> None:
        assert (
            service.initial_role_for(
                email="compliance@mizan.app.attacker.com",
                bootstrap_admin_emails=("compliance@mizan.app",),
            )
            is Role.USER
        )

    def test_blank_entries_in_the_configured_list_grant_nothing(
        self, service: AuthorizationService
    ) -> None:
        # An unset `BOOTSTRAP_ADMIN_EMAILS` splits into [""], which must
        # not match an empty-ish address.
        assert (
            service.initial_role_for(email="", bootstrap_admin_emails=("", "  "))
            is Role.USER
        )
