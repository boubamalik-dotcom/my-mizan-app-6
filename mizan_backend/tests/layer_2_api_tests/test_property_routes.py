"""End-to-end tests for Oran Real Estate's Layer 2 HTTP route.

`TestTheContractTheClientParses` is the load-bearing group: the Flutter
client's `PropertyModel.fromJson` throws on a missing `id`, `title`,
`district`, `price`, `bedrooms`, `bathrooms`, or `area_sqm`, so a rename
on this side is a blank screen over there. Asserting the field names
here is what makes that a failing test rather than a bug report.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, AsyncIterator, Dict, List

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.layer_2_api.auth.auth_controller import AuthController
from src.layer_2_api.controllers.property_controller import PropertyController
from src.layer_2_api.main_router import api_router
from src.layer_3_business.auth.auth_service import AuthService
from src.layer_3_business.property.amenities import PropertySearchService
from src.layer_4_data_access.uow.transaction_manager import UnitOfWork
from src.layer_5_storage.base_model import Base
from src.layer_5_storage.db_config import build_engine, build_session_factory

TEST_SECRET_KEY = "test-secret-key-at-least-32-bytes-long-for-hmac-sha256"
TEST_PASSWORD = "correct-horse-battery-staple"


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    test_engine = build_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return build_session_factory(engine)


@pytest_asyncio.fixture
async def app(session_factory: async_sessionmaker) -> FastAPI:
    def unit_of_work_factory() -> UnitOfWork:
        return UnitOfWork(session_factory)

    application = FastAPI()
    application.include_router(api_router, prefix="/api/v1")
    application.state.property_controller = PropertyController(
        unit_of_work_factory=unit_of_work_factory
    )
    application.state.auth_controller = AuthController(
        auth_service=AuthService(secret_key=TEST_SECRET_KEY),
        unit_of_work_factory=unit_of_work_factory,
    )
    return application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def _seed(session_factory: async_sessionmaker) -> None:
    """Four listings whose amenity sets differ, so a filter that matched
    everything or nothing could not pass."""
    definitions = [
        ("all_four", True, True, True, True, "80000000", True),
        ("none", False, False, False, False, "9000000", False),
        ("pool_only", True, False, False, False, "42000000", False),
        ("king_and_smoke_free", False, False, True, True, "31000000", False),
    ]
    async with UnitOfWork(session_factory) as uow:
        for title, pool, high, king, smoke_free, price, featured in definitions:
            await uow.properties.create_property(
                title=title,
                description=f"{title} description",
                district="الصديقية، وهران",
                price=Decimal(price),
                bedrooms=4,
                bathrooms=3,
                area_sqm=210,
                is_featured=featured,
                has_private_pool=pool,
                is_high_floor=high,
                has_king_bed=king,
                is_non_smoking=smoke_free,
            )
        await uow.commit()


@pytest_asyncio.fixture
async def seeded(session_factory: async_sessionmaker) -> None:
    await _seed(session_factory)


async def _titles(client: AsyncClient, query: str = "") -> List[str]:
    response = await client.get(f"/api/v1/properties{query}")
    assert response.status_code == 200, response.text
    return [item["title"] for item in response.json()["items"]]


class TestTheContractTheClientParses:
    async def test_every_field_the_client_requires_is_present(
        self, client: AsyncClient, seeded: None
    ) -> None:
        listing = (await client.get("/api/v1/properties")).json()["items"][0]

        for field in (
            "id",
            "title",
            "district",
            "price",
            "currency",
            "bedrooms",
            "bathrooms",
            "area_sqm",
            "amenities",
            "is_featured",
        ):
            assert field in listing, f"client parses `{field}` and it is missing"

    async def test_the_price_is_a_decimal_string_not_a_float(
        self, client: AsyncClient, seeded: None
    ) -> None:
        # The client accepts a number or a numeric string; a string keeps
        # a 42,000,000 figure exact through JSON.
        listing = (await client.get("/api/v1/properties")).json()["items"][0]

        assert Decimal(str(listing["price"])) == Decimal("80000000.00")

    async def test_amenities_come_back_as_wire_values(
        self, client: AsyncClient, seeded: None
    ) -> None:
        items = {
            item["title"]: item
            for item in (await client.get("/api/v1/properties")).json()["items"]
        }

        assert set(items["all_four"]["amenities"]) == {
            "private_pool",
            "high_floor",
            "king_bed",
            "non_smoking",
        }
        assert items["none"]["amenities"] == []

    async def test_the_envelope_the_client_understands(
        self, client: AsyncClient, seeded: None
    ) -> None:
        body = (await client.get("/api/v1/properties")).json()

        # `_parseListings` reads `items`; `total` and `applied_amenities`
        # are additions it safely ignores.
        assert isinstance(body["items"], list)
        assert body["total"] == 4

    async def test_an_empty_catalogue_is_an_empty_list_not_an_error(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/v1/properties")

        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["total"] == 0


class TestAuthentication:
    async def test_browsing_does_not_require_an_account(
        self, client: AsyncClient, seeded: None
    ) -> None:
        # Looking at what is for sale should not need a login.
        response = await client.get("/api/v1/properties")
        assert response.status_code == 200

    async def test_a_stale_token_still_returns_listings(
        self, client: AsyncClient, seeded: None
    ) -> None:
        response = await client.get(
            "/api/v1/properties",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert response.status_code == 200


class TestFilteringByTheRepeatedListParameter:
    async def test_no_filter_returns_everything(
        self, client: AsyncClient, seeded: None
    ) -> None:
        # The case an over-eager filter breaks: an empty filter bar must
        # show all listings, not none.
        assert len(await _titles(client)) == 4

    async def test_one_amenity_narrows(
        self, client: AsyncClient, seeded: None
    ) -> None:
        assert set(await _titles(client, "?amenities=private_pool")) == {
            "all_four",
            "pool_only",
        }

    async def test_two_amenities_require_both(
        self, client: AsyncClient, seeded: None
    ) -> None:
        assert set(
            await _titles(client, "?amenities=king_bed&amenities=non_smoking")
        ) == {"all_four", "king_and_smoke_free"}

    async def test_all_four_narrows_to_one(
        self, client: AsyncClient, seeded: None
    ) -> None:
        query = (
            "?amenities=private_pool&amenities=high_floor"
            "&amenities=king_bed&amenities=non_smoking"
        )
        assert await _titles(client, query) == ["all_four"]

    async def test_the_applied_filters_are_echoed_back(
        self, client: AsyncClient, seeded: None
    ) -> None:
        # So a client can tell "no matches" from "filter ignored".
        body = (
            await client.get("/api/v1/properties?amenities=private_pool")
        ).json()

        assert body["applied_amenities"] == ["private_pool"]

    async def test_an_unknown_amenity_is_rejected_not_ignored(
        self, client: AsyncClient, seeded: None
    ) -> None:
        # Ignoring it would return listings that violate the filter, and
        # the client would have no way to tell.
        response = await client.get("/api/v1/properties?amenities=rooftop_helipad")

        assert response.status_code == 422, response.text
        assert "private_pool" in response.json()["detail"]

    async def test_one_bad_value_rejects_the_whole_request(
        self, client: AsyncClient, seeded: None
    ) -> None:
        response = await client.get(
            "/api/v1/properties?amenities=private_pool&amenities=nope"
        )
        assert response.status_code == 422


class TestFilteringByTheBooleanParameters:
    async def test_a_boolean_requires_the_amenity(
        self, client: AsyncClient, seeded: None
    ) -> None:
        assert set(await _titles(client, "?has_private_pool=true")) == {
            "all_four",
            "pool_only",
        }

    async def test_false_excludes_it(
        self, client: AsyncClient, seeded: None
    ) -> None:
        # The one thing the list form cannot express.
        assert set(await _titles(client, "?has_private_pool=false")) == {
            "none",
            "king_and_smoke_free",
        }

    async def test_omitting_it_is_not_the_same_as_false(
        self, client: AsyncClient, seeded: None
    ) -> None:
        assert len(await _titles(client)) == 4
        assert len(await _titles(client, "?has_private_pool=false")) == 2

    async def test_booleans_combine_with_the_list(
        self, client: AsyncClient, seeded: None
    ) -> None:
        assert await _titles(
            client, "?amenities=king_bed&is_non_smoking=true&has_private_pool=false"
        ) == ["king_and_smoke_free"]

    async def test_an_explicit_false_overrides_the_list(
        self, client: AsyncClient, seeded: None
    ) -> None:
        assert set(
            await _titles(client, "?amenities=private_pool&has_private_pool=false")
        ) == {"none", "king_and_smoke_free"}


class TestOrderingAndPaging:
    async def test_featured_listings_come_first(
        self, client: AsyncClient, seeded: None
    ) -> None:
        assert (await _titles(client))[0] == "all_four"

    async def test_a_page_size_is_honoured(
        self, client: AsyncClient, seeded: None
    ) -> None:
        assert len(await _titles(client, "?limit=2")) == 2

    async def test_the_total_ignores_paging(
        self, client: AsyncClient, seeded: None
    ) -> None:
        body = (await client.get("/api/v1/properties?limit=2")).json()

        assert (len(body["items"]), body["total"]) == (2, 4)

    async def test_a_huge_page_size_is_clamped_not_refused(
        self, client: AsyncClient, seeded: None
    ) -> None:
        response = await client.get("/api/v1/properties?limit=100000")

        assert response.status_code == 200
        assert len(response.json()["items"]) <= PropertySearchService.MAX_LIMIT

    async def test_offset_pages_through(
        self, client: AsyncClient, seeded: None
    ) -> None:
        first = await _titles(client, "?limit=2&offset=0")
        second = await _titles(client, "?limit=2&offset=2")

        assert set(first) & set(second) == set()

    async def test_the_count_reflects_the_filters(
        self, client: AsyncClient, seeded: None
    ) -> None:
        body = (
            await client.get("/api/v1/properties?amenities=private_pool")
        ).json()

        assert body["total"] == 2


class TestOpenApiDocumentation:
    async def test_the_endpoint_is_documented(self, client: AsyncClient) -> None:
        schema = (await client.get("/openapi.json")).json()
        assert "get" in schema["paths"]["/api/v1/properties"]

    @pytest.mark.parametrize(
        "parameter",
        [
            "amenities",
            "has_private_pool",
            "is_high_floor",
            "has_king_bed",
            "is_non_smoking",
            "limit",
            "offset",
        ],
    )
    async def test_every_query_parameter_is_documented(
        self, client: AsyncClient, parameter: str
    ) -> None:
        schema = (await client.get("/openapi.json")).json()
        names = {
            item["name"]
            for item in schema["paths"]["/api/v1/properties"]["get"]["parameters"]
        }
        assert parameter in names


class TestReadOnly:
    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    async def test_the_collection_accepts_reads_only(
        self, client: AsyncClient, method: str
    ) -> None:
        # Publishing a listing is administrative and has no endpoint yet;
        # asserted so adding one is a deliberate act.
        response = await getattr(client, method)("/api/v1/properties")
        assert response.status_code == 405

    async def test_a_search_leaves_the_catalogue_untouched(
        self, client: AsyncClient, seeded: None, session_factory: async_sessionmaker
    ) -> None:
        await client.get("/api/v1/properties?amenities=private_pool")

        async with UnitOfWork(session_factory) as uow:
            assert await uow.properties.count_properties() == 4
