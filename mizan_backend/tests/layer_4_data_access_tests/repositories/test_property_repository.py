"""Functional tests for `PropertyRepository` against a real (in-memory
SQLite) database.

The filtering is the substance here, and it is tested against a fixture
where every listing differs in which amenities it holds — so a filter
that silently matched everything, or nothing, cannot pass.
"""
from __future__ import annotations

from decimal import Decimal
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.layer_4_data_access.repositories.property_repository import (
    PropertyRecord,
    PropertyRepository,
)
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = build_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = build_session_factory(engine)
    async with factory() as open_session:
        yield open_session

    await engine.dispose()


@pytest.fixture
def repository(session: AsyncSession) -> PropertyRepository:
    return PropertyRepository(session)


@pytest_asyncio.fixture
async def catalogue(repository: PropertyRepository) -> dict[str, str]:
    """Six listings covering the amenity combinations that matter:
    all four, none, and several partial overlaps."""
    definitions = [
        # name,              pool,  high,  king,  smoke-free, price, featured
        ("all_four", True, True, True, True, "80000000", True),
        ("none", False, False, False, False, "9000000", False),
        ("pool_only", True, False, False, False, "42000000", False),
        ("high_and_king", False, True, True, False, "58000000", True),
        ("king_and_smoke_free", False, False, True, True, "31000000", False),
        ("smoke_free_only", False, False, False, True, "12000000", False),
    ]
    ids: dict[str, str] = {}
    for name, pool, high, king, smoke_free, price, featured in definitions:
        record = await repository.create_property(
            title=name,
            district="وهران",
            price=Decimal(price),
            bedrooms=3,
            bathrooms=2,
            area_sqm=120,
            is_featured=featured,
            has_private_pool=pool,
            is_high_floor=high,
            has_king_bed=king,
            is_non_smoking=smoke_free,
        )
        ids[name] = record.id
    return ids


async def _titles(
    repository: PropertyRepository, **filters: object
) -> set[str]:
    listings = await repository.get_properties(**filters)  # type: ignore[arg-type]
    return {listing.title for listing in listings}


class TestNoFilters:
    async def test_returns_every_listing(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        # The case an over-eager filter breaks: all four amenity
        # parameters omitted must mean "no constraint", not "false".
        assert await _titles(repository) == set(catalogue)

    async def test_explicit_none_is_the_same_as_omitting(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        assert (
            await _titles(
                repository,
                has_private_pool=None,
                is_high_floor=None,
                has_king_bed=None,
                is_non_smoking=None,
            )
            == set(catalogue)
        )


class TestSingleAmenity:
    async def test_a_private_pool(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        assert await _titles(repository, has_private_pool=True) == {
            "all_four",
            "pool_only",
        }

    async def test_a_high_floor(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        assert await _titles(repository, is_high_floor=True) == {
            "all_four",
            "high_and_king",
        }

    async def test_a_king_bed(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        assert await _titles(repository, has_king_bed=True) == {
            "all_four",
            "high_and_king",
            "king_and_smoke_free",
        }

    async def test_non_smoking(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        assert await _titles(repository, is_non_smoking=True) == {
            "all_four",
            "king_and_smoke_free",
            "smoke_free_only",
        }


class TestFalseIsNotTheSameAsUnfiltered:
    async def test_false_selects_only_listings_without_it(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        assert await _titles(repository, has_private_pool=False) == {
            "none",
            "high_and_king",
            "king_and_smoke_free",
            "smoke_free_only",
        }

    async def test_true_and_false_partition_the_catalogue(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        # Which is only true because the column is NOT NULL — a nullable
        # amenity would leave listings in neither half.
        with_pool = await _titles(repository, has_private_pool=True)
        without_pool = await _titles(repository, has_private_pool=False)

        assert with_pool & without_pool == set()
        assert with_pool | without_pool == set(catalogue)


class TestCombinedFilters:
    async def test_two_amenities_require_both(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        # AND, not OR: a filter bar of independent checkboxes narrows.
        assert await _titles(
            repository, is_high_floor=True, has_king_bed=True
        ) == {"all_four", "high_and_king"}

    async def test_all_four_narrows_to_one(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        assert await _titles(
            repository,
            has_private_pool=True,
            is_high_floor=True,
            has_king_bed=True,
            is_non_smoking=True,
        ) == {"all_four"}

    async def test_an_unsatisfiable_combination_returns_nothing(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        # An empty result is a legitimate answer, not an error.
        assert (
            await _titles(repository, has_private_pool=True, is_high_floor=False)
            == {"pool_only"}
        )
        assert (
            await _titles(
                repository, has_private_pool=True, is_non_smoking=True,
                is_high_floor=False,
            )
            == set()
        )

    async def test_mixing_require_and_exclude(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        assert await _titles(
            repository, has_king_bed=True, has_private_pool=False
        ) == {"high_and_king", "king_and_smoke_free"}


class TestOrdering:
    async def test_featured_first_then_by_descending_price(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        listings = await repository.get_properties()

        featured = [listing for listing in listings if listing.is_featured]
        assert [listing.title for listing in listings[: len(featured)]] == [
            "all_four",
            "high_and_king",
        ]
        rest = [listing.price for listing in listings[len(featured) :]]
        assert rest == sorted(rest, reverse=True)

    async def test_the_order_is_stable_across_identical_requests(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        first = [listing.id for listing in await repository.get_properties()]
        second = [listing.id for listing in await repository.get_properties()]

        assert first == second

    async def test_paging_neither_skips_nor_repeats(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        # What the primary-key tiebreak in the ORDER BY is for: without
        # it, two listings at the same price could swap between requests.
        page_one = await repository.get_properties(limit=2, offset=0)
        page_two = await repository.get_properties(limit=2, offset=2)
        page_three = await repository.get_properties(limit=2, offset=4)

        seen = [listing.id for page in (page_one, page_two, page_three)
                for listing in page]
        assert len(seen) == len(set(seen)) == len(catalogue)


class TestCounting:
    async def test_counts_every_match_ignoring_paging(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        # So a client can tell "2 shown" from "6 exist".
        page = await repository.get_properties(limit=2)
        total = await repository.count_properties()

        assert (len(page), total) == (2, 6)

    async def test_the_count_respects_the_same_filters(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        assert await repository.count_properties(has_private_pool=True) == 2

    async def test_an_empty_catalogue_counts_zero(
        self, repository: PropertyRepository
    ) -> None:
        assert await repository.count_properties() == 0


class TestDerivedAmenityList:
    async def test_lists_exactly_what_the_listing_has(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        listings = {
            listing.title: listing for listing in await repository.get_properties()
        }

        assert set(listings["all_four"].amenities()) == {
            "private_pool",
            "high_floor",
            "king_bed",
            "non_smoking",
        }
        assert listings["none"].amenities() == ()
        assert set(listings["pool_only"].amenities()) == {"private_pool"}

    async def test_the_list_and_the_filters_cannot_disagree(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        # Derived rather than stored, so every listing a filter returns
        # advertises the amenity that matched it.
        for listing in await repository.get_properties(has_king_bed=True):
            assert "king_bed" in listing.amenities()


class TestSingleLookup:
    async def test_finds_a_listing_by_id(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        found = await repository.get_property_by_id(catalogue["pool_only"])

        assert found is not None and found.title == "pool_only"

    async def test_returns_none_for_an_unknown_id(
        self, repository: PropertyRepository
    ) -> None:
        assert await repository.get_property_by_id("no-such-listing") is None


class TestRecordsAreNotOrmObjects:
    async def test_callers_never_receive_a_sqlalchemy_object(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        listing: PropertyRecord = (await repository.get_properties())[0]

        assert not hasattr(listing, "_sa_instance_state")
        with pytest.raises((AttributeError, TypeError)):
            listing.title = "mutated"  # type: ignore[misc]

    async def test_the_price_is_a_decimal_not_a_float(
        self, repository: PropertyRepository, catalogue: dict[str, str]
    ) -> None:
        # A listing at 42,000,000 shown as 41999999.99999 would look like
        # a defect even though the error is microscopic.
        listing = (await repository.get_properties())[0]
        assert isinstance(listing.price, Decimal)
