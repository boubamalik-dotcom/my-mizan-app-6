"""Layer 4 — async repository abstracting SQLAlchemy-based property
listing persistence for Oran Real Estate.

Like `wallet_repository.py`, this is the only place besides Layer 5 that
imports `PropertyModel` or touches an `AsyncSession`. Layers 2 and 3
only ever see the plain `PropertyRecord` dataclass returned here.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...layer_3_business.property.amenities import Amenity, AmenityFilters
from ...layer_5_storage.models.property_model import PropertyModel


class PropertyRepositoryError(Exception):
    """Base class for every error raised by `PropertyRepository`."""


class PropertyNotFoundError(PropertyRepositoryError):
    """Raised when an operation references a property id that does not
    exist."""

    def __init__(self, property_id: str) -> None:
        """
        Args:
            property_id: The identifier that could not be resolved.
        """
        self.property_id = property_id
        super().__init__(f'Property "{property_id}" does not exist.')


@dataclass(frozen=True, slots=True)
class PropertyRecord:
    """An immutable snapshot of one listing, fully decoupled from
    `PropertyModel` — callers never need to import SQLAlchemy."""

    id: str
    title: str
    description: str
    price: Decimal
    currency: str
    district: str
    bedrooms: int
    bathrooms: int
    area_sqm: int
    is_featured: bool
    has_private_pool: bool
    is_high_floor: bool
    has_king_bed: bool
    is_non_smoking: bool

    def amenities(self) -> tuple[str, ...]:
        """The amenities this listing offers, as the wire values the
        client expects in its `amenities` array.

        Derived from the four columns rather than stored, so the array a
        client reads and the booleans a filter matches on can never
        disagree — which they would the moment one was updated and the
        other was not.
        """
        held = {
            Amenity.PRIVATE_POOL: self.has_private_pool,
            Amenity.HIGH_FLOOR: self.is_high_floor,
            Amenity.KING_BED: self.has_king_bed,
            Amenity.NON_SMOKING: self.is_non_smoking,
        }
        return tuple(amenity.value for amenity, present in held.items() if present)


class PropertyRepository:
    """Async repository for property listings.

    Bound to a single `AsyncSession` for its lifetime — typically one
    per `UnitOfWork` transaction — so every read it performs sees that
    transaction's consistent snapshot.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Args:
            session: The `AsyncSession` this repository will use for
                every operation. Its transaction boundary is owned by
                the caller, not by this class.
        """
        self._session = session

    async def get_properties(
        self,
        *,
        has_private_pool: Optional[bool] = None,
        is_high_floor: Optional[bool] = None,
        has_king_bed: Optional[bool] = None,
        is_non_smoking: Optional[bool] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> list[PropertyRecord]:
        """Lists properties, narrowed to those matching every amenity
        constraint given.

        Each amenity parameter is **tri-state**, and the distinction is
        the whole point of the signature:

        * `None` — do not filter on this amenity.
        * `True` — only listings that have it.
        * `False` — only listings that do not.

        `None` and `False` are emphatically different. Passing `False`
        for every unchecked box — the obvious shortcut — would turn an
        empty filter bar into "listings with none of these amenities",
        so the user would clear their filters and be shown fewer results
        instead of all of them.

        Constraints combine with `AND`: asking for a private pool and a
        high floor returns listings with both, which is what a filter bar
        of independent checkboxes means.

        Args:
            has_private_pool: Constrain on a private pool, or `None`.
            is_high_floor: Constrain on a high floor, or `None`.
            has_king_bed: Constrain on a king bed, or `None`.
            is_non_smoking: Constrain on non-smoking, or `None`.
            limit: Page size. `None` for no limit — callers reaching
                this repository directly (seeds, tests) may legitimately
                want everything; the HTTP layer always supplies one.
            offset: How many matching listings to skip.

        Returns:
            The matching listings, featured first and then by descending
            price, so the ordering is stable between identical requests
            rather than whatever the planner happens to return.
        """
        statement = self._apply_amenity_filters(
            select(PropertyModel),
            AmenityFilters(
                has_private_pool=has_private_pool,
                is_high_floor=is_high_floor,
                has_king_bed=has_king_bed,
                is_non_smoking=is_non_smoking,
            ),
        )

        statement = statement.order_by(
            PropertyModel.is_featured.desc(),
            PropertyModel.price.desc(),
            # A final tiebreak on the primary key: without it, two
            # listings at the same price could swap places between
            # requests and paging would skip or repeat one of them.
            PropertyModel.id.asc(),
        ).offset(offset)

        if limit is not None:
            statement = statement.limit(limit)

        result = await self._session.execute(statement)
        return [self._to_record(row) for row in result.scalars().all()]

    async def count_properties(
        self,
        *,
        has_private_pool: Optional[bool] = None,
        is_high_floor: Optional[bool] = None,
        has_king_bed: Optional[bool] = None,
        is_non_smoking: Optional[bool] = None,
    ) -> int:
        """How many listings match the same constraints, ignoring
        paging — so a client can tell "50 shown" from "50 exist"."""
        from sqlalchemy import func

        statement = self._apply_amenity_filters(
            select(func.count(PropertyModel.id)),
            AmenityFilters(
                has_private_pool=has_private_pool,
                is_high_floor=is_high_floor,
                has_king_bed=has_king_bed,
                is_non_smoking=is_non_smoking,
            ),
        )
        return int(await self._session.scalar(statement) or 0)

    async def get_property_by_id(self, property_id: str) -> Optional[PropertyRecord]:
        """Fetches one listing by id.

        Args:
            property_id: The listing's identifier.

        Returns:
            A `PropertyRecord`, or `None` if no such listing exists.
        """
        listing = await self._session.get(PropertyModel, property_id)
        return self._to_record(listing) if listing is not None else None

    async def create_property(
        self,
        *,
        title: str,
        description: str = "",
        price: Decimal,
        currency: str = "DZD",
        district: str,
        bedrooms: int = 0,
        bathrooms: int = 0,
        area_sqm: int,
        is_featured: bool = False,
        has_private_pool: bool = False,
        is_high_floor: bool = False,
        has_king_bed: bool = False,
        is_non_smoking: bool = False,
    ) -> PropertyRecord:
        """Registers a listing. Used by the seed script and by tests;
        there is no HTTP endpoint for it yet, since publishing a listing
        is an administrative act rather than something the buyer-facing
        app does.

        Returns:
            A `PropertyRecord` for the new listing.
        """
        listing = PropertyModel(
            title=title,
            description=description,
            price=price,
            currency=currency,
            district=district,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            area_sqm=area_sqm,
            is_featured=is_featured,
            has_private_pool=has_private_pool,
            is_high_floor=is_high_floor,
            has_king_bed=has_king_bed,
            is_non_smoking=is_non_smoking,
        )
        self._session.add(listing)
        await self._session.flush()
        return self._to_record(listing)

    # -- Internal helpers -------------------------------------------------

    @staticmethod
    def _apply_amenity_filters(
        statement: Select, filters: AmenityFilters
    ) -> Select:
        """Adds one `WHERE` clause per constrained amenity.

        Built by iterating Layer 3's mapping rather than with four `if`
        statements, so adding a fifth amenity does not mean remembering
        to extend this method too — a forgotten branch here would
        silently ignore the new filter, which is exactly the failure the
        domain refuses to allow at the edge.
        """
        for column_name, required in filters.as_mapping().items():
            if required is None:
                continue
            statement = statement.where(
                getattr(PropertyModel, column_name).is_(required)
            )
        return statement

    @staticmethod
    def _to_record(listing: PropertyModel) -> PropertyRecord:
        """Maps a `PropertyModel` row to its plain-data counterpart."""
        return PropertyRecord(
            id=listing.id,
            title=listing.title,
            description=listing.description,
            price=listing.price,
            currency=listing.currency,
            district=listing.district,
            bedrooms=listing.bedrooms,
            bathrooms=listing.bathrooms,
            area_sqm=listing.area_sqm,
            is_featured=listing.is_featured,
            has_private_pool=listing.has_private_pool,
            is_high_floor=listing.is_high_floor,
            has_king_bed=listing.has_king_bed,
            is_non_smoking=listing.is_non_smoking,
        )


__all__: Sequence[str] = (
    "PropertyNotFoundError",
    "PropertyRecord",
    "PropertyRepository",
    "PropertyRepositoryError",
)
