"""Layer 2 — Pydantic response schemas for Oran Real Estate.

Field names are the wire contract `mizan_frontend`'s
`PropertyModel.fromJson` already parses. It throws a `FormatException`
on a missing `id`, `title`, `district`, `price`, `bedrooms`,
`bathrooms`, or `area_sqm`, so every one of those is required here
rather than optional — an optional field would turn a data gap into a
blank screen in the client instead of a loud failure on the server.
"""
from __future__ import annotations

from decimal import Decimal
from typing import List

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """FastAPI's standard error envelope, declared so the property
    endpoint documents its failures in the OpenAPI schema."""

    detail: str


class PropertyResponse(BaseModel):
    """One property listing."""

    id: str
    title: str
    description: str
    price: Decimal = Field(
        description="The listing price, as a decimal string — not a float, "
        "so a figure in the tens of millions is never shown with a "
        "rounding artefact."
    )
    currency: str
    district: str = Field(
        description="Neighbourhood, shown beneath the title. Stored as "
        "`properties.district`."
    )
    bedrooms: int
    bathrooms: int
    area_sqm: int = Field(description="Floor area in square metres.")
    is_featured: bool = Field(
        description="Whether the listing carries the gold \"مميّز\" ribbon."
    )
    amenities: List[str] = Field(
        description="The premium amenities this listing offers, as wire "
        "values (`private_pool`, `high_floor`, `king_bed`, "
        "`non_smoking`). Derived from the four boolean columns, so the "
        "array and the filters can never disagree."
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "9f2a1c44-6f1e-4a3b-9e77-0c2f8a51d310",
                "title": "شقة فاخرة بإطلالة على البحر",
                "description": "شقة واسعة بإطلالة مباشرة على البحر.",
                "price": "42000000.00",
                "currency": "DZD",
                "district": "الصديقية، وهران",
                "bedrooms": 4,
                "bathrooms": 3,
                "area_sqm": 210,
                "is_featured": True,
                "amenities": ["private_pool", "high_floor", "king_bed"],
            }
        }
    }


class PropertyListResponse(BaseModel):
    """The `GET /properties` payload.

    An `items` envelope rather than a bare array, matching the other
    Mizan collection endpoints and leaving room for `total` — which a
    bare array has nowhere to put. The client accepts either shape (see
    `PropertyRemoteDataSource._parseListings`), so the envelope costs it
    nothing.
    """

    items: List[PropertyResponse]
    total: int = Field(
        description="How many listings match the filters in total, "
        "ignoring paging — so a client can tell \"50 shown\" from "
        "\"50 exist\"."
    )
    applied_amenities: List[str] = Field(
        default_factory=list,
        description="The amenity filters actually applied, echoed back. "
        "A client can confirm its request was understood rather than "
        "inferring it from the results, which for a filter is the "
        "difference between \"no matches\" and \"filter ignored\".",
    )
