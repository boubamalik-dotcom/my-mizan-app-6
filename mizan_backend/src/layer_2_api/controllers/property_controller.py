"""Layer 2 — Oran Real Estate property controller.

`PropertyController` orchestrates the listing search:

1. Calls Layer 3 (`PropertySearchService`) to turn the client's raw
   query parameters into amenity requirements and a servable page size —
   pure logic, no I/O.
2. Uses Layer 4 (`UnitOfWork`, `PropertyRepository`) to run the search
   and count the matches.
3. Translates the one domain exception this flow can raise into an
   `HTTPException`, so this is the only place a property domain error
   becomes an HTTP status code.

**On placement:** the brief asked for this at
`src/layer_3_business/controllers/property_controller.py`. It cannot
live there. `tests/test_layer_isolation.py` forbids Layer 3 from
importing Layers 2, 4, or 5, so a Layer 3 controller could not reach a
repository at all — and Layer 2 is where `WalletController`,
`QueueController`, `ChatController`, and `AuthController` already are.
The *business rules* the brief wanted in Layer 3 are in Layer 3
(`layer_3_business/property/amenities.py`); only the orchestration,
which needs both neighbours at once, sits here.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterable, Iterator, List, Optional, Tuple

from fastapi import HTTPException, status

from ...layer_3_business.property.amenities import (
    AmenityFilters,
    PropertySearchService,
)
from ...layer_3_business.property.exceptions import UnknownAmenityError
from ...layer_4_data_access.repositories.property_repository import PropertyRecord
from ...layer_4_data_access.uow.transaction_manager import UnitOfWork


class PropertyController:
    """Coordinates Layer 3 search rules and Layer 4 persistence to serve
    Oran Real Estate's REST endpoint."""

    def __init__(
        self,
        *,
        search_service: Optional[PropertySearchService] = None,
        unit_of_work_factory: Callable[[], UnitOfWork] = UnitOfWork,
    ) -> None:
        """
        Args:
            search_service: The Layer 3 service that parses amenity
                filters and clamps paging. Stateless, so a shared
                default instance is fine.
            unit_of_work_factory: A zero-argument callable returning a
                fresh, not-yet-entered `UnitOfWork`. Injected so tests
                can point it at an isolated test database.
        """
        self._search_service = search_service or PropertySearchService()
        self._unit_of_work_factory = unit_of_work_factory

    async def list_properties(
        self,
        *,
        amenities: Optional[Iterable[object]] = None,
        has_private_pool: Optional[bool] = None,
        is_high_floor: Optional[bool] = None,
        has_king_bed: Optional[bool] = None,
        is_non_smoking: Optional[bool] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Tuple[List[PropertyRecord], int, Tuple[str, ...]]:
        """Searches listings.

        Accepts the amenity filters in both forms the API offers — the
        repeated `amenities` list the built client sends, and the
        individual booleans — and merges them before querying, so the
        two can be combined without the repository needing to know there
        were two.

        Args:
            amenities: Wire values from the repeated `amenities`
                parameter.
            has_private_pool: Explicit per-amenity constraint, or `None`.
            is_high_floor: Explicit per-amenity constraint, or `None`.
            has_king_bed: Explicit per-amenity constraint, or `None`.
            is_non_smoking: Explicit per-amenity constraint, or `None`.
            limit: Requested page size; clamped by Layer 3.
            offset: How many matches to skip.

        Returns:
            A `(listings, total, applied_amenities)` triple. `total`
            counts every match, ignoring paging.

        Raises:
            HTTPException: 422 if an amenity name is not recognised.
        """
        with self._translate_domain_errors():
            filters = self._search_service.merge_filters(
                from_wire=self._search_service.filters_from_wire(amenities),
                explicit=AmenityFilters(
                    has_private_pool=has_private_pool,
                    is_high_floor=is_high_floor,
                    has_king_bed=has_king_bed,
                    is_non_smoking=is_non_smoking,
                ),
            )

        page_size = self._search_service.resolve_page_size(limit)
        skip = self._search_service.resolve_offset(offset)
        constraints = filters.as_mapping()

        async with self._unit_of_work_factory() as uow:
            listings = await uow.properties.get_properties(
                **constraints, limit=page_size, offset=skip
            )
            total = await uow.properties.count_properties(**constraints)

        # No commit: this is a read-only use case, and `UnitOfWork`
        # deliberately does not auto-commit, so the transaction is simply
        # rolled back when the block exits.
        return listings, total, self._search_service.describe(filters)

    @staticmethod
    @contextmanager
    def _translate_domain_errors() -> Iterator[None]:
        """Context manager translating the property domain exceptions
        into the matching `HTTPException`.

        Mapping:

        * `UnknownAmenityError` -> 422 Unprocessable Entity
        """
        try:
            yield
        except UnknownAmenityError as exc:
            # 422 rather than 400: the request is well-formed, its
            # *content* names something that does not exist. The message
            # lists the amenities that do, so a client built against a
            # different vocabulary can see the difference immediately.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
