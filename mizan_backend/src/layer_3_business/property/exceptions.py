"""Layer 3 — pure domain exceptions for property search.

Plain Python exceptions with no framework imports: Layer 2's
`PropertyController` is the only place that turns these into HTTP status
codes.
"""
from __future__ import annotations

from typing import Sequence


class PropertyDomainError(Exception):
    """Base class for every property-search rule violation."""


class UnknownAmenityError(PropertyDomainError):
    """Raised when a client filters on an amenity this server does not
    know.

    Rejected rather than ignored. A filter the server quietly drops
    returns listings that do not satisfy it — a buyer who asked for a
    private pool would be shown properties without one, with nothing to
    indicate the request had been discarded. An error is the only
    response that cannot mislead, and it tells a client built against a
    newer vocabulary exactly what went wrong.
    """

    def __init__(self, value: object, known: Sequence[str]) -> None:
        """
        Args:
            value: The unrecognised wire value.
            known: Every amenity this server does support, listed in the
                message so the caller can correct the request without
                reading the source.
        """
        self.value = value
        self.known = tuple(known)
        super().__init__(
            f'Unknown amenity "{value}". Supported amenities: '
            f"{', '.join(self.known)}."
        )
