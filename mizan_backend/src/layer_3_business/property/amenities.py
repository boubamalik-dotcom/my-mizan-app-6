"""Layer 3 — the premium amenity vocabulary and the rules for filtering
on it.

STRICT RULE: pure Python only. No FastAPI, no SQLAlchemy, and nothing
from Layers 2, 4, or 5 — this module turns the strings a client sends
into a decision about what to filter, and nothing else.

The wire values here are the contract `mizan_frontend`'s
`PropertyAmenity` enum already sends (`private_pool`, `high_floor`,
`king_bed`, `non_smoking`). They live in Layer 3 rather than at the
route, because "which amenities exist" is a fact about the product, not
about HTTP: the same vocabulary would apply to a CLI, an import script,
or a second client.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Tuple

from .exceptions import UnknownAmenityError


class Amenity(str, enum.Enum):
    """One filterable premium amenity.

    Inherits from `str` so a value round-trips through JSON and a query
    string as its plain wire form.
    """

    PRIVATE_POOL = "private_pool"
    HIGH_FLOOR = "high_floor"
    KING_BED = "king_bed"
    NON_SMOKING = "non_smoking"

    @classmethod
    def parse(cls, value: object) -> "Amenity":
        """Resolves a wire value to an `Amenity`.

        Raises:
            UnknownAmenityError: If `value` names no known amenity.
                Deliberately an error rather than something skipped:
                ignoring an unrecognised filter would return listings
                that *violate* it, so a client asking for a pool would
                be shown properties without one and have no way to
                tell. Failing loudly is the only answer that cannot
                mislead.
        """
        for amenity in cls:
            if amenity.value == value:
                return amenity
        raise UnknownAmenityError(value, tuple(member.value for member in cls))


@dataclass(frozen=True, slots=True)
class AmenityFilters:
    """Which amenities a search requires, as an explicit tri-state per
    amenity.

    `None` means "do not filter on this one", which is different from
    `False` ("only listings without it"). Collapsing the two — the
    obvious shortcut of passing `False` for anything unchecked — would
    turn an empty filter bar into "show me listings with no amenities at
    all", i.e. an empty page where the user expected everything.
    """

    has_private_pool: Optional[bool] = None
    is_high_floor: Optional[bool] = None
    has_king_bed: Optional[bool] = None
    is_non_smoking: Optional[bool] = None

    @property
    def is_empty(self) -> bool:
        """Whether no amenity constrains the search, so every listing
        qualifies."""
        return all(
            value is None
            for value in (
                self.has_private_pool,
                self.is_high_floor,
                self.has_king_bed,
                self.is_non_smoking,
            )
        )

    def as_mapping(self) -> Mapping[str, Optional[bool]]:
        """The filters keyed by the column each one constrains, so Layer
        4 can build its `WHERE` clause by iterating rather than
        repeating an `if` per amenity."""
        return {
            "has_private_pool": self.has_private_pool,
            "is_high_floor": self.is_high_floor,
            "has_king_bed": self.has_king_bed,
            "is_non_smoking": self.is_non_smoking,
        }


#: Which `AmenityFilters` field each amenity constrains. Declared once,
#: so adding an amenity is a change in two places in this module rather
#: than a hunt through the repository and the route as well.
FILTER_FIELD_FOR: Mapping[Amenity, str] = {
    Amenity.PRIVATE_POOL: "has_private_pool",
    Amenity.HIGH_FLOOR: "is_high_floor",
    Amenity.KING_BED: "has_king_bed",
    Amenity.NON_SMOKING: "is_non_smoking",
}


class PropertySearchService:
    """Pure rules for turning a client's request into a property search.

    Stateless and free of I/O, so a single shared instance is the whole
    object — the same pattern `AuthorizationService` uses.
    """

    #: Listings returned when a client does not ask for a page size.
    DEFAULT_LIMIT = 50

    #: The most a client may ask for in one page. A ceiling rather than
    #: a suggestion: without one, `?limit=1000000` is a way to make the
    #: server serialise the whole table on request.
    MAX_LIMIT = 200

    def filters_from_wire(
        self, values: Optional[Iterable[object]]
    ) -> AmenityFilters:
        """Builds `AmenityFilters` from the repeated `amenities` query
        parameter the client sends.

        Every named amenity becomes a `True` requirement; the rest stay
        `None`. Listing an amenity is how a client says "require this" —
        there is no wire form for "require the *absence* of a pool",
        because no filter bar offers it.

        Args:
            values: The wire values, or `None`/empty for no filter.

        Returns:
            The requirements. `AmenityFilters.is_empty` when nothing was
            asked for.

        Raises:
            UnknownAmenityError: If any value names no known amenity.
        """
        if not values:
            return AmenityFilters()

        required: dict[str, Optional[bool]] = {}
        for value in values:
            amenity = Amenity.parse(value)
            required[FILTER_FIELD_FOR[amenity]] = True

        return AmenityFilters(**required)

    def merge_filters(
        self, *, from_wire: AmenityFilters, explicit: AmenityFilters
    ) -> AmenityFilters:
        """Combines the two ways a client can express amenity filters.

        The list form (`?amenities=private_pool`) is what the built
        client sends; the boolean form (`?has_private_pool=true`) is the
        explicit per-amenity parameter. Both narrow the search, and an
        explicit boolean wins where the two speak about the same
        amenity — it is the more specific statement, being the only one
        of the two that can ask for `False`.

        Args:
            from_wire: Requirements derived from the `amenities` list.
            explicit: Requirements given as individual booleans.

        Returns:
            One set of requirements covering both.
        """
        combined = dict(from_wire.as_mapping())
        for field, value in explicit.as_mapping().items():
            if value is not None:
                combined[field] = value
        return AmenityFilters(**combined)

    def resolve_page_size(self, limit: Optional[int]) -> int:
        """Clamps a requested page size into something servable.

        Args:
            limit: What the client asked for, or `None`.

        Returns:
            The page size to use.
        """
        if limit is None:
            return self.DEFAULT_LIMIT
        return max(1, min(limit, self.MAX_LIMIT))

    def resolve_offset(self, offset: Optional[int]) -> int:
        """Normalises a requested offset, treating a negative one as the
        start rather than as an error — it names no page, and refusing
        the request would be a harsher answer than the mistake
        deserves."""
        if offset is None or offset < 0:
            return 0
        return offset

    @staticmethod
    def describe(filters: AmenityFilters) -> Tuple[str, ...]:
        """The amenities a search requires, as wire values, for logging
        and for echoing back what was applied."""
        mapping = filters.as_mapping()
        return tuple(
            amenity.value
            for amenity, field in FILTER_FIELD_FOR.items()
            if mapping[field] is True
        )
