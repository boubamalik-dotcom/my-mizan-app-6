"""Layer 3 — pure business logic for authorization decisions.

STRICT RULE: no FastAPI, no Pydantic, no SQLAlchemy. Every method is a
deterministic, side-effect-free function of its arguments: no database
lookups, no request objects, no I/O of any kind. An access-control
decision that cannot be reproduced from its inputs alone cannot be
audited, so this class is built so that every "yes" or "no" it returns
is fully explained by the role and permission passed in.
"""
from __future__ import annotations

from typing import FrozenSet, Iterable

from .authz_exceptions import PermissionDeniedError
from .roles import DEFAULT_ROLE, ROLE_PERMISSIONS, Permission, Role


class AuthorizationService:
    """Answers "may this role do this?" against [ROLE_PERMISSIONS]."""

    def permissions_for(self, role: Role) -> FrozenSet[Permission]:
        """Returns every permission `role` holds.

        A role absent from the policy table yields an empty set rather
        than raising: the safe reading of "no policy recorded" is "no
        access granted".
        """
        return ROLE_PERMISSIONS.get(role, frozenset())

    def has_permission(self, role: Role, permission: Permission) -> bool:
        """Returns whether `role` holds `permission`."""
        return permission in self.permissions_for(role)

    def require_permission(self, role: Role, permission: Permission) -> None:
        """Asserts that `role` holds `permission`.

        Raises:
            PermissionDeniedError: If it does not. Raising rather than
                returning a bool is what makes the guard hard to
                misuse — an ignored return value fails open, while an
                unhandled exception fails closed.
        """
        if not self.has_permission(role, permission):
            raise PermissionDeniedError(role=role, permission=permission)

    def can_read_wallet(
        self, *, role: Role, actor_user_id: str, owner_user_id: str
    ) -> bool:
        """Whether `actor_user_id` may read a wallet owned by
        `owner_user_id`.

        Two independent grounds, which is exactly the distinction the
        Audit API rests on: a user may read their **own** wallet by
        ownership, while an auditor may read **anyone's** by
        permission. Ownership is checked first because it is the
        common case and needs no elevated role at all.
        """
        if actor_user_id == owner_user_id:
            return True
        return self.has_permission(role, Permission.AUDIT_READ_ANY_WALLET)

    def initial_role_for(
        self, *, email: str, bootstrap_admin_emails: Iterable[str]
    ) -> Role:
        """The role a newly registered `email` should receive.

        Everyone gets [DEFAULT_ROLE] unless their address is on the
        deployment's bootstrap list, which exists solely to create the
        first admin — granting a role otherwise requires
        [Permission.MANAGE_USER_ROLES], which only an admin holds, so
        without this the first one could never exist.

        Compared case-insensitively, since email local parts are
        routinely typed with inconsistent case and a near-miss here
        would silently produce an ordinary user where an admin was
        intended.
        """
        normalised = {
            candidate.strip().lower()
            for candidate in bootstrap_admin_emails
            if candidate.strip()
        }
        if email.strip().lower() in normalised:
            return Role.ADMIN
        return DEFAULT_ROLE
