"""Domain-level exceptions for the audit rules (Layer 3).

No web framework or database dependency; Layer 2
(`layer_2_api/audit/audit_controller.py`) translates these into HTTP
status codes.
"""
from __future__ import annotations


class AuditError(Exception):
    """Base class for every error raised by the audit business logic."""


class InvalidAuditQueryError(AuditError):
    """Raised when an audit query is not answerable as written — an
    inverted date range, or a page size outside the permitted bounds.

    Layer 2 maps this to **422 Unprocessable Entity**: the request was
    understood, but it does not describe a valid query.
    """

    def __init__(self, reason: str) -> None:
        """
        Args:
            reason: A short, human-readable explanation of what is
                wrong with the query.
        """
        self.reason = reason
        super().__init__(reason)
