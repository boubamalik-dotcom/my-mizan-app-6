"""Layer 3 — the role/permission model, as pure data.

STRICT RULE: this module must never import FastAPI, Pydantic, or
SQLAlchemy. It is plain `enum` and `frozenset` definitions, so the
entire access-control policy can be read, reviewed, and unit-tested
without a web framework or a database anywhere in sight — which is the
point, since for a regulated system this table *is* the compliance
artifact auditors will ask to see.
"""
from __future__ import annotations

import enum
from typing import FrozenSet, Mapping


class Role(str, enum.Enum):
    """Who a principal is, for access-control purposes.

    Deliberately a small, closed set rather than free-form strings: a
    typo in a role name must be a load-time error, not a silent grant
    or a silent denial.

    Inherits from `str` so a role round-trips through JSON, a database
    column, and a JWT claim as its plain value (`"auditor"`) without
    any bespoke serialization.
    """

    #: An ordinary customer. Owns wallets and chats; can see only their
    #: own data.
    USER = "user"

    #: Clinic reception. Holds exactly one capability beyond an ordinary
    #: user's — calling the next patient — so a receptionist can run a
    #: waiting room without being handed platform administration.
    #:
    #: **Not yet scoped to a particular clinic.** Nothing in the data
    #: model ties an account to a clinic, so this role can advance *any*
    #: clinic's queue. Narrowing it needs a `users.clinic_id` column and
    #: an ownership check alongside the permission check; until then,
    #: grant it only to staff trusted across every clinic on the
    #: deployment.
    CLINIC_STAFF = "clinic_staff"

    #: Read-only oversight. May inspect *any* wallet's ledger for
    #: regulatory review, but may never move money or change anything —
    #: the separation that makes the audit trail trustworthy.
    AUDITOR = "auditor"

    #: Full administrative control, including granting roles.
    ADMIN = "admin"

    @classmethod
    def parse(cls, value: object) -> "Role":
        """Resolves `value` to a `Role`.

        Raises:
            InvalidRoleError: If `value` is not one of the defined
                roles. Never falls back to a default — quietly
                downgrading an unrecognised role to `USER` would turn a
                data problem into a security problem, and quietly
                upgrading it would be worse.
        """
        from .authz_exceptions import InvalidRoleError

        if isinstance(value, cls):
            return value
        for role in cls:
            if role.value == value:
                return role
        raise InvalidRoleError(value)


class Permission(str, enum.Enum):
    """A single capability a role may hold.

    Routes are guarded by permissions rather than by roles directly, so
    that adding a role, or moving a capability between roles, is a
    change to [ROLE_PERMISSIONS] alone and never a hunt through every
    endpoint.
    """

    #: Read the append-only transaction ledger for any wallet.
    AUDIT_READ_LEDGER = "audit:read_ledger"

    #: Read any wallet's state, regardless of who owns it.
    AUDIT_READ_ANY_WALLET = "audit:read_any_wallet"

    #: Grant or revoke another user's role.
    MANAGE_USER_ROLES = "users:manage_roles"

    #: Call the next patient in a clinic's queue — the operation that
    #: moves the queue forward. Held by clinic staff, never by the
    #: patients standing in it: a patient who could advance the queue
    #: could serve themselves to the front of it.
    QUEUE_ADVANCE = "queue:advance"


#: The complete access-control policy: which permissions each role
#: holds. Every grant in the system is visible here, in one place.
#:
#: `AUDITOR` is intentionally read-only — it holds no permission that
#: mutates anything, and notably not [Permission.MANAGE_USER_ROLES],
#: so an auditor cannot quietly grant themselves more access. `USER`
#: holds no elevated permission at all: ordinary wallet and chat access
#: is authorized by *ownership* (see `WalletController`), not by role,
#: and this table exists only to describe access that reaches beyond
#: one's own data.
ROLE_PERMISSIONS: Mapping[Role, FrozenSet[Permission]] = {
    Role.USER: frozenset(),
    Role.CLINIC_STAFF: frozenset({Permission.QUEUE_ADVANCE}),
    Role.AUDITOR: frozenset(
        {
            Permission.AUDIT_READ_LEDGER,
            Permission.AUDIT_READ_ANY_WALLET,
        }
    ),
    Role.ADMIN: frozenset(Permission),
}

#: The role a newly registered account receives.
DEFAULT_ROLE = Role.USER
