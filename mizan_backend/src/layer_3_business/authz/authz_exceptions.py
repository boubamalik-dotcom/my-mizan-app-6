"""Domain-level exceptions for authorization (Layer 3).

These carry no dependency on any web framework or database driver.
Layer 2 is responsible for translating them into HTTP status codes —
see `layer_2_api/audit/audit_controller.py` and
`layer_2_api/auth/deps.py`.
"""
from __future__ import annotations


class AuthorizationError(Exception):
    """Base class for every error raised by the authorization rules.

    Catching `AuthorizationError` is guaranteed to catch every
    subclass below without needing to know the full list in advance.
    """


class PermissionDeniedError(AuthorizationError):
    """Raised when a principal attempts something their role does not
    permit.

    Distinct from an authentication failure: the caller *is* who they
    say they are, they simply may not do this. Layer 2 maps this to
    **403 Forbidden**, never 401 — answering 401 would invite the
    client to re-authenticate, which cannot possibly help.
    """

    def __init__(self, *, role: object, permission: object) -> None:
        """
        Args:
            role: The role the principal actually holds.
            permission: The permission that was required.
        """
        self.role = role
        self.permission = permission
        role_value = getattr(role, "value", role)
        permission_value = getattr(permission, "value", permission)
        super().__init__(
            f'Role "{role_value}" does not have the required permission '
            f'"{permission_value}".'
        )


class InvalidRoleError(AuthorizationError):
    """Raised when a value cannot be resolved to a known `Role`.

    Reached when persisted or supplied data names a role this build
    does not define — a data-integrity problem that must fail loudly
    rather than resolve to some default.
    """

    def __init__(self, value: object) -> None:
        """
        Args:
            value: The unrecognised role value.
        """
        self.value = value
        super().__init__(f'"{value}" is not a recognised role.')
