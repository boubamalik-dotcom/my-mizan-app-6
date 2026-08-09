"""Layer 5 — SQLAlchemy ORM model for Oran Real Estate's property
listings.

STRICT RULE: this module contains an ORM model only. It has zero imports
from Layers 2, 3, or 4 — it knows nothing about business rules, HTTP, or
how it is accessed. `layer_4_data_access/repositories/
property_repository.py` is the only code elsewhere in the backend that
imports it.

**Two column names deviate from the brief, to match the client that
already exists.** `mizan_frontend`'s `PropertyModel.fromJson` throws on
a missing field, and its `PropertyCard` renders the price as a plain
formatted figure with no period attached:

* the brief's `price_per_night` is **`price`** here. The listings are
  sales at tens of millions of dinars ("شقة فاخرة … 42,000,000 DZD"),
  not nightly rates, so a per-night column would misname what it holds
  and the UI would display it under no such label anyway.
* the brief's `location_name` is **`district`**, which is the field the
  client reads and the word the card prints beneath the title.

The four premium amenities are stored as the brief specifies — four
indexed booleans rather than a list column or a join table. For a fixed,
small set that exists to be filtered on, a boolean per amenity is the
shape the database can actually use an index for; a JSON array would
force a scan, and a join table would turn "has all four" into four
joins or a grouped count.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..base_model import Base, TimestampMixin, generate_uuid

#: Fixed-point precision for the listing price. Two decimal places
#: rather than the wallet's four: a property is priced to the dinar, and
#: `Numeric` (not `float`) because a price that renders as
#: `41999999.99999` in a listing would look like a defect even though
#: the error is microscopic.
PRICE_PRECISION = 18
PRICE_SCALE = 2

#: Used when a listing is created without an explicit currency. The
#: client defaults to the same value, so the two agree on what a
#: currency-less listing means.
DEFAULT_CURRENCY = "DZD"


class PropertyModel(Base, TimestampMixin):
    """A single property listing.

    Unlike `WalletModel` there is no `version_id_col`: a listing is
    edited by whoever manages it, not raced over by concurrent
    requests, so there is no lost update to prevent. If listings ever
    gain a "reserved by" field that two clients could set at once, that
    is the point to revisit it.
    """

    __tablename__ = "properties"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_property_price_non_negative"),
        CheckConstraint("bedrooms >= 0", name="ck_property_bedrooms_non_negative"),
        CheckConstraint("bathrooms >= 0", name="ck_property_bathrooms_non_negative"),
        CheckConstraint("area_sqm > 0", name="ck_property_area_positive"),
        # The four amenities are queried together — "show me listings
        # with a private pool *and* a high floor" — so one composite
        # index serves any subset of them, in this column order, rather
        # than four separate indexes the planner would have to combine.
        Index(
            "ix_property_amenities",
            "has_private_pool",
            "is_high_floor",
            "has_king_bed",
            "is_non_smoking",
        ),
        # Featured listings sort first and the district is the most
        # likely future filter.
        Index("ix_property_featured_price", "is_featured", "price"),
        Index("ix_property_district", "district"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )

    #: Arabic headline, e.g. "شقة فاخرة بإطلالة على البحر".
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    #: Long-form prose. `Text` rather than `String(n)` because a
    #: description has no natural maximum that would not eventually be
    #: hit and truncated.
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    price: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default=DEFAULT_CURRENCY
    )

    #: Neighbourhood, e.g. "الصديقية، وهران". Called `district` rather
    #: than the brief's `location_name`; see the module docstring.
    district: Mapped[str] = mapped_column(String(255), nullable=False)

    bedrooms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bathrooms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: Floor area in square metres.
    area_sqm: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Whether the listing carries the gold "مميّز" ribbon in the UI.
    is_featured: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )

    # -- The four premium amenity filters ---------------------------------
    #
    # Not nullable, and defaulted to false: "we do not know whether this
    # listing has a private pool" is not a state the filter could act on
    # — a three-valued column would make `has_private_pool=true` and
    # `has_private_pool=false` fail to partition the listings between
    # them, and a buyer filtering for a pool would silently lose every
    # unknown listing with no way to tell.

    has_private_pool: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_high_floor: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    has_king_bed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_non_smoking: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        """Compact representation for logs/debuggers, not part of any
        public API contract."""
        return (
            f"PropertyModel(id={self.id!r}, title={self.title!r}, "
            f"district={self.district!r}, price={self.price!r})"
        )
