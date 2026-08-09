"""Layer 2 — Oran Real Estate property HTTP routes.

Routes are intentionally thin: they parse transport-level input,
delegate to `PropertyController`, and marshal its result into response
schemas. All business logic and domain-exception translation lives in
the controller.

Mounted under `/api/v1` by `main.py`, so the path below resolves to
`/api/v1/properties` — what `mizan_frontend`'s Oran Real Estate
mini-program already calls.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request

from ...layer_4_data_access.repositories.property_repository import PropertyRecord
from ...layer_4_data_access.repositories.user_repository import UserRecord
from ..auth.deps import get_current_user_or_none
from ..controllers.property_controller import PropertyController
from ..schemas.property_schemas import (
    ErrorResponse,
    PropertyListResponse,
    PropertyResponse,
)

router = APIRouter(prefix="/properties", tags=["properties"])


def get_property_controller(request: Request) -> PropertyController:
    """Resolves the app-wide `PropertyController` singleton.

    Constructed once at startup in `main.py` (the composition root) and
    stored on `app.state`, so it is never re-instantiated per request.
    """
    return request.app.state.property_controller


def _to_response(listing: PropertyRecord) -> PropertyResponse:
    return PropertyResponse(
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
        amenities=list(listing.amenities()),
    )


@router.get(
    "",
    response_model=PropertyListResponse,
    responses={
        422: {
            "model": ErrorResponse,
            "description": "An amenity filter names something unrecognised.",
        }
    },
    summary="Search property listings",
    description=(
        "Returns property listings, featured first and then by "
        "descending price.\n\n"
        "**Amenity filters can be given two ways**, and both narrow the "
        "search:\n\n"
        "* a repeated list — `?amenities=private_pool&amenities=high_floor` "
        "— which is what the Oran Real Estate client sends;\n"
        "* individual booleans — `?has_private_pool=true&is_high_floor=false` "
        "— which are the only form able to ask for the *absence* of an "
        "amenity.\n\n"
        "Omitting a filter means \"do not filter on it\", which is not "
        "the same as `false` (\"only listings without it\"). Constraints "
        "combine with `AND`, so an empty filter bar returns everything "
        "rather than nothing.\n\n"
        "An unrecognised amenity name is rejected with **422** rather "
        "than ignored: a filter the server quietly dropped would return "
        "listings that violate it, and the client would have no way to "
        "tell.\n\n"
        "Authentication is optional — browsing what is for sale does not "
        "require an account — but the client sends its token anyway, so "
        "the endpoint is ready to personalise later without a second "
        "route."
    ),
)
async def list_properties(
    amenities: Optional[List[str]] = Query(
        default=None,
        description=(
            "Repeated amenity requirement, e.g. "
            "`?amenities=private_pool&amenities=king_bed`. Supported "
            "values: `private_pool`, `high_floor`, `king_bed`, "
            "`non_smoking`."
        ),
    ),
    has_private_pool: Optional[bool] = Query(
        default=None, description="Require (or exclude) a private pool."
    ),
    is_high_floor: Optional[bool] = Query(
        default=None, description="Require (or exclude) a high floor."
    ),
    has_king_bed: Optional[bool] = Query(
        default=None, description="Require (or exclude) a king bed."
    ),
    is_non_smoking: Optional[bool] = Query(
        default=None, description="Require (or exclude) a non-smoking listing."
    ),
    limit: Optional[int] = Query(
        default=None,
        ge=1,
        description="Page size. Clamped to a server maximum of 200.",
    ),
    offset: Optional[int] = Query(
        default=None, ge=0, description="How many matching listings to skip."
    ),
    controller: PropertyController = Depends(get_property_controller),
    _: Optional[UserRecord] = Depends(get_current_user_or_none),
) -> PropertyListResponse:
    """Search property listings, optionally narrowed by premium
    amenities."""
    listings, total, applied = await controller.list_properties(
        amenities=amenities,
        has_private_pool=has_private_pool,
        is_high_floor=is_high_floor,
        has_king_bed=has_king_bed,
        is_non_smoking=is_non_smoking,
        limit=limit,
        offset=offset,
    )
    return PropertyListResponse(
        items=[_to_response(listing) for listing in listings],
        total=total,
        applied_amenities=list(applied),
    )
