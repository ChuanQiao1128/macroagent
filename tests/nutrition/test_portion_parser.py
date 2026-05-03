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
    assert result.confidence == pytest.approx(0.90)
    assert result.source == "portion_hint_weight_unit"
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
    assert result.confidence == pytest.approx(expected_confidence)
    assert result.source == "portion_hint_household_unit"
    assert "parsed" in result.reason
    assert "component 'chicken'" in result.reason


def test_parse_portion_range_missing_hint_uses_fallback_range() -> None:
    result = parse_portion_range(component_name="broccoli", portion_hint=None)

    assert result.grams_min == 60.0
    assert result.grams_max == 350.0
    assert result.confidence == pytest.approx(0.25)
    assert result.source == "fallback_default"
    assert "portion hint missing" in result.reason
    assert "component='broccoli'" in result.reason


def test_parse_portion_range_unknown_text_uses_fallback_parse_failure_reason() -> None:
    result = parse_portion_range(component_name="beef", portion_hint="unicorn bucket")

    assert result.grams_min == 60.0
    assert result.grams_max == 350.0
    assert result.confidence == pytest.approx(0.20)
    assert result.source == "fallback_default"
    assert "could not be parsed" in result.reason
    assert "portion_hint='unicorn bucket'" in result.reason


def test_parse_portion_range_non_positive_quantity_uses_fallback() -> None:
    result = parse_portion_range(component_name="salad", portion_hint="0 cup")

    assert result.grams_min == 60.0
    assert result.grams_max == 350.0
    assert result.confidence == pytest.approx(0.20)
    assert result.source == "fallback_default"
    assert "non-positive" in result.reason


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
