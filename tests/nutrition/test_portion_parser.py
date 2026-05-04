from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.nutrition import PortionGramRange, parse_component_portion_range, parse_portion_range


@pytest.mark.parametrize(
    ("portion_hint", "expected_min", "expected_max"),
    [
        ("100 g", 90.0, 110.0),
        ("80g", 72.0, 88.0),
        ("0.25 kg", 225.0, 275.0),
    ],
)
def test_parse_portion_range_parses_weight_units(
    portion_hint: str,
    expected_min: float,
    expected_max: float,
) -> None:
    result = parse_portion_range(component_name="rice", portion_hint=portion_hint)

    assert result.grams_min == expected_min
    assert result.grams_max == expected_max
    assert result.grams_p10 == expected_min
    assert result.grams_p50 == pytest.approx((expected_min + expected_max) / 2.0)
    assert result.grams_p90 == expected_max
    assert result.percentiles_available is True
    assert result.confidence == pytest.approx(0.90)
    assert result.source == "portion_hint_weight_unit"
    assert result.uncertainty_flags == ()
    assert "parsed" in result.reason
    assert "component 'rice'" in result.reason


@pytest.mark.parametrize(
    ("portion_hint", "expected_min", "expected_max", "expected_confidence"),
    [
        ("half cup", 60.0, 130.0, 0.68),
        ("bowl", 240.0, 600.0, 0.58),
        ("one plate", 280.0, 700.0, 0.68),
        ("2 slices", 36.0, 180.0, 0.68),
        ("piece", 25.0, 180.0, 0.58),
        ("1 egg", 40.0, 75.0, 0.68),
        ("3 scoops", 60.0, 150.0, 0.68),
        ("1 tablespoon", 10.0, 20.0, 0.68),
        ("2 teaspoons", 6.0, 16.0, 0.68),
        ("palm-sized", 75.0, 150.0, 0.58),
        ("palm sized", 75.0, 150.0, 0.58),
    ],
)
def test_parse_portion_range_parses_common_household_units(
    portion_hint: str,
    expected_min: float,
    expected_max: float,
    expected_confidence: float,
) -> None:
    result = parse_portion_range(component_name="chicken", portion_hint=portion_hint)

    assert result.grams_min == expected_min
    assert result.grams_max == expected_max
    assert result.grams_p10 == expected_min
    assert result.grams_p50 == pytest.approx((expected_min + expected_max) / 2.0)
    assert result.grams_p90 == expected_max
    assert result.percentiles_available is True
    assert result.confidence == pytest.approx(expected_confidence)
    assert result.source == "portion_hint_household_unit"
    assert "parsed" in result.reason
    assert "component 'chicken'" in result.reason


def test_parse_portion_range_missing_hint_uses_fallback_range() -> None:
    result = parse_portion_range(component_name="broccoli", portion_hint=None)

    assert result.grams_min == 60.0
    assert result.grams_max == 350.0
    assert result.grams_p10 == 60.0
    assert result.grams_p50 == 205.0
    assert result.grams_p90 == 350.0
    assert result.percentiles_available is True
    assert result.confidence == pytest.approx(0.25)
    assert result.source == "fallback_default"
    assert result.uncertainty_flags == ("missing_portion_hint",)
    assert "portion hint missing" in result.reason
    assert "component='broccoli'" in result.reason


def test_parse_portion_range_unknown_text_uses_fallback_parse_failure_reason() -> None:
    result = parse_portion_range(component_name="beef", portion_hint="unicorn bucket")

    assert result.grams_min == 60.0
    assert result.grams_max == 350.0
    assert result.grams_p10 == 60.0
    assert result.grams_p50 == 205.0
    assert result.grams_p90 == 350.0
    assert result.percentiles_available is True
    assert result.confidence == pytest.approx(0.20)
    assert result.source == "fallback_default"
    assert result.uncertainty_flags == ("unknown_portion_hint",)
    assert "could not be parsed" in result.reason
    assert "portion_hint='unicorn bucket'" in result.reason


def test_parse_portion_range_non_positive_quantity_uses_fallback() -> None:
    result = parse_portion_range(component_name="salad", portion_hint="0 cup")

    assert result.grams_min == 60.0
    assert result.grams_max == 350.0
    assert result.grams_p10 == 60.0
    assert result.grams_p50 == 205.0
    assert result.grams_p90 == 350.0
    assert result.percentiles_available is True
    assert result.confidence == pytest.approx(0.20)
    assert result.source == "fallback_default"
    assert result.uncertainty_flags == ("non_positive_quantity",)
    assert "non-positive" in result.reason


def test_parse_portion_range_weight_hint_with_approximate_language_sets_flag() -> None:
    result = parse_portion_range(component_name="rice", portion_hint="about 100 g")

    assert result.grams_p10 == 90.0
    assert result.grams_p50 == 100.0
    assert result.grams_p90 == 110.0
    assert result.confidence == pytest.approx(0.90)
    assert result.source == "portion_hint_weight_unit"
    assert result.uncertainty_flags == ("approximate_quantity",)


@pytest.mark.parametrize(
    ("portion_hint", "expected_flags"),
    [
        ("bowl", ("implicit_quantity",)),
        ("palm-sized", ("implicit_quantity",)),
        ("1 cup", ()),
        ("about bowl", ("implicit_quantity", "approximate_quantity")),
    ],
)
def test_parse_portion_range_household_flags_reflect_implicit_and_approximate_hints(
    portion_hint: str,
    expected_flags: tuple[str, ...],
) -> None:
    result = parse_portion_range(component_name="chicken", portion_hint=portion_hint)

    assert result.source == "portion_hint_household_unit"
    assert result.uncertainty_flags == expected_flags


@pytest.mark.parametrize(
    ("portion_hint", "expected_min", "expected_max"),
    [
        ("1/2 cup", 60.0, 130.0),
        ("1 1/2 cups", 180.0, 390.0),
        ("three quarters cup", 90.0, 195.0),
        ("about one and a half cups", 180.0, 390.0),
    ],
)
def test_parse_portion_range_parses_fractional_and_mixed_household_quantities(
    portion_hint: str,
    expected_min: float,
    expected_max: float,
) -> None:
    result = parse_portion_range(component_name="lentils", portion_hint=portion_hint)

    assert result.grams_min == expected_min
    assert result.grams_max == expected_max
    assert result.confidence == pytest.approx(0.68)
    assert result.source == "portion_hint_household_unit"
    assert "parsed" in result.reason
    assert "component 'lentils'" in result.reason


def test_parse_component_portion_range_alias_matches_primary_api() -> None:
    primary = parse_portion_range(component_name="tofu", portion_hint="1 cup")
    alias = parse_component_portion_range(component_name="tofu", portion_hint="1 cup")

    assert alias == primary


def test_portion_gram_range_is_immutable() -> None:
    result = parse_portion_range(component_name="rice", portion_hint="100 g")

    with pytest.raises(ValidationError):
        result.grams_min = 1.0


def test_portion_gram_range_rejects_invalid_bounds_and_negative_values() -> None:
    with pytest.raises(ValidationError):
        PortionGramRange(
            grams_min=200.0,
            grams_max=100.0,
            confidence=0.5,
            source="fallback_default",
            reason="invalid bounds",
        )

    with pytest.raises(ValidationError):
        PortionGramRange(
            grams_min=-1.0,
            grams_max=100.0,
            confidence=0.5,
            source="fallback_default",
            reason="negative grams",
        )


def test_portion_gram_range_rejects_invalid_percentile_ordering() -> None:
    with pytest.raises(ValidationError):
        PortionGramRange(
            grams_p10=150.0,
            grams_p50=120.0,
            grams_p90=200.0,
            confidence=0.7,
            source="fallback_default",
            reason="invalid percentile ordering",
        )
