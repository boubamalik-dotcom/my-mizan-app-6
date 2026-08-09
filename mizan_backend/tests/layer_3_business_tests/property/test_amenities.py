"""Unit tests for Layer 3's property-search rules.

The distinction these exist to protect is `None` versus `False`: "do not
filter on this amenity" versus "only listings without it". Collapsing
the two is the mistake that turns an empty filter bar into an empty
results page, and it is invisible until someone clears their filters.
"""
from __future__ import annotations

import pytest

from src.layer_3_business.property.amenities import (
    Amenity,
    AmenityFilters,
    FILTER_FIELD_FOR,
    PropertySearchService,
)
from src.layer_3_business.property.exceptions import (
    PropertyDomainError,
    UnknownAmenityError,
)


@pytest.fixture
def service() -> PropertySearchService:
    return PropertySearchService()


class TestTheAmenityVocabulary:
    def test_the_wire_values_are_the_ones_the_client_sends(self) -> None:
        # Fixed by `mizan_frontend`'s PropertyAmenity enum; renaming one
        # here silently breaks that client's filter bar.
        assert {amenity.value for amenity in Amenity} == {
            "private_pool",
            "high_floor",
            "king_bed",
            "non_smoking",
        }

    def test_every_amenity_maps_to_a_filter_field(self) -> None:
        # A missing entry would mean an amenity that parses but filters
        # nothing — accepted and then ignored, the exact failure this
        # module refuses to allow.
        assert set(FILTER_FIELD_FOR) == set(Amenity)

    def test_every_filter_field_is_a_real_field(self) -> None:
        fields = set(AmenityFilters().as_mapping())
        assert set(FILTER_FIELD_FOR.values()) <= fields

    def test_parses_a_known_value(self) -> None:
        assert Amenity.parse("private_pool") is Amenity.PRIVATE_POOL

    @pytest.mark.parametrize(
        "value", ["", "PRIVATE_POOL", "pool", "private pool", None, 7]
    )
    def test_rejects_anything_else(self, value: object) -> None:
        with pytest.raises(UnknownAmenityError):
            Amenity.parse(value)

    def test_the_refusal_lists_what_is_supported(self) -> None:
        # So a client built against a different vocabulary can see the
        # difference without reading the source.
        with pytest.raises(UnknownAmenityError) as exc_info:
            Amenity.parse("rooftop_helipad")

        message = str(exc_info.value)
        for amenity in Amenity:
            assert amenity.value in message


class TestFiltersFromWire:
    def test_no_amenities_constrains_nothing(
        self, service: PropertySearchService
    ) -> None:
        # The case that matters most: an empty filter bar must mean
        # "show everything", not "show listings with no amenities".
        filters = service.filters_from_wire(None)

        assert filters.is_empty
        assert all(value is None for value in filters.as_mapping().values())

    def test_an_empty_list_also_constrains_nothing(
        self, service: PropertySearchService
    ) -> None:
        assert service.filters_from_wire([]).is_empty

    def test_a_named_amenity_becomes_a_true_requirement(
        self, service: PropertySearchService
    ) -> None:
        filters = service.filters_from_wire(["private_pool"])

        assert filters.has_private_pool is True
        # And crucially, the others stay None rather than becoming False.
        assert filters.is_high_floor is None
        assert filters.has_king_bed is None
        assert filters.is_non_smoking is None

    def test_several_amenities_all_become_requirements(
        self, service: PropertySearchService
    ) -> None:
        filters = service.filters_from_wire(["private_pool", "king_bed"])

        assert (filters.has_private_pool, filters.has_king_bed) == (True, True)
        assert filters.is_high_floor is None

    def test_all_four_can_be_required(
        self, service: PropertySearchService
    ) -> None:
        filters = service.filters_from_wire(
            [amenity.value for amenity in Amenity]
        )

        assert all(value is True for value in filters.as_mapping().values())
        assert not filters.is_empty

    def test_a_repeated_amenity_is_harmless(
        self, service: PropertySearchService
    ) -> None:
        filters = service.filters_from_wire(["king_bed", "king_bed"])
        assert filters.has_king_bed is True

    def test_one_unknown_value_rejects_the_whole_request(
        self, service: PropertySearchService
    ) -> None:
        # Not "apply the ones we understood": a partially applied filter
        # returns listings that violate the part that was dropped.
        with pytest.raises(UnknownAmenityError):
            service.filters_from_wire(["private_pool", "rooftop_helipad"])


class TestMergingTheTwoFilterForms:
    def test_the_list_form_alone_is_used(
        self, service: PropertySearchService
    ) -> None:
        merged = service.merge_filters(
            from_wire=service.filters_from_wire(["private_pool"]),
            explicit=AmenityFilters(),
        )

        assert merged.has_private_pool is True

    def test_the_boolean_form_alone_is_used(
        self, service: PropertySearchService
    ) -> None:
        merged = service.merge_filters(
            from_wire=AmenityFilters(),
            explicit=AmenityFilters(is_high_floor=True),
        )

        assert merged.is_high_floor is True

    def test_the_two_combine(self, service: PropertySearchService) -> None:
        merged = service.merge_filters(
            from_wire=service.filters_from_wire(["private_pool"]),
            explicit=AmenityFilters(is_non_smoking=True),
        )

        assert (merged.has_private_pool, merged.is_non_smoking) == (True, True)

    def test_an_explicit_false_wins_over_the_list(
        self, service: PropertySearchService
    ) -> None:
        # The boolean form is the more specific statement: it is the only
        # one of the two that can ask for an amenity's absence, so if a
        # caller says both "require a pool" and "has_private_pool=false",
        # the explicit denial is what they meant.
        merged = service.merge_filters(
            from_wire=service.filters_from_wire(["private_pool"]),
            explicit=AmenityFilters(has_private_pool=False),
        )

        assert merged.has_private_pool is False

    def test_an_omitted_boolean_never_overrides_the_list(
        self, service: PropertySearchService
    ) -> None:
        # `None` means "said nothing", so it must not overwrite a
        # requirement the list already established.
        merged = service.merge_filters(
            from_wire=service.filters_from_wire(["king_bed"]),
            explicit=AmenityFilters(has_king_bed=None),
        )

        assert merged.has_king_bed is True

    def test_neither_form_leaves_the_search_unconstrained(
        self, service: PropertySearchService
    ) -> None:
        merged = service.merge_filters(
            from_wire=AmenityFilters(), explicit=AmenityFilters()
        )
        assert merged.is_empty


class TestPaging:
    def test_a_missing_limit_gets_the_default(
        self, service: PropertySearchService
    ) -> None:
        assert service.resolve_page_size(None) == service.DEFAULT_LIMIT

    def test_a_request_above_the_ceiling_is_clamped(
        self, service: PropertySearchService
    ) -> None:
        # Without a ceiling, `?limit=1000000` is a way to make the server
        # serialise the whole table on request.
        assert service.resolve_page_size(10_000) == service.MAX_LIMIT

    def test_a_reasonable_limit_is_honoured(
        self, service: PropertySearchService
    ) -> None:
        assert service.resolve_page_size(12) == 12

    @pytest.mark.parametrize("limit", [0, -5])
    def test_a_nonsense_limit_still_returns_something(
        self, service: PropertySearchService, limit: int
    ) -> None:
        # A page of zero listings is never what anyone wanted.
        assert service.resolve_page_size(limit) == 1

    @pytest.mark.parametrize(("offset", "expected"), [(None, 0), (-3, 0), (20, 20)])
    def test_offsets_are_normalised(
        self, service: PropertySearchService, offset: int, expected: int
    ) -> None:
        assert service.resolve_offset(offset) == expected


class TestDescribingWhatWasApplied:
    def test_lists_only_the_required_amenities(
        self, service: PropertySearchService
    ) -> None:
        filters = service.filters_from_wire(["king_bed", "private_pool"])

        assert set(service.describe(filters)) == {"king_bed", "private_pool"}

    def test_an_unconstrained_search_describes_nothing(
        self, service: PropertySearchService
    ) -> None:
        assert service.describe(AmenityFilters()) == ()

    def test_an_excluded_amenity_is_not_reported_as_required(
        self, service: PropertySearchService
    ) -> None:
        # `False` is a constraint, but not a *requirement*, and echoing
        # it as one would tell the client the opposite of what it asked.
        assert service.describe(AmenityFilters(has_private_pool=False)) == ()


class TestPurity:
    def test_the_rules_module_imports_no_framework(self) -> None:
        import inspect

        from src.layer_3_business.property import amenities

        source = inspect.getsource(amenities)
        for forbidden in ("fastapi", "sqlalchemy", "pydantic", "redis"):
            assert forbidden not in source

    def test_every_property_error_shares_one_base(self) -> None:
        assert issubclass(UnknownAmenityError, PropertyDomainError)
