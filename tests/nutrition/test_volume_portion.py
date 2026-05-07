from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.nutrition import (
    VolumeEstimate,
    estimate_portion_from_volume,
    parse_volume_portion_range,
    resolve_density_profile,
)


def test_volume_estimate_converts_cooked_rice_to_gram_percentiles() -> None:
    estimate = VolumeEstimate(
        volume_ml_p10=180.0,
        volume_ml_p50=200.0,
        volume_ml_p90=220.0,
        confidence=0.74,
        method="arkit_depth_region",
        evidence_ids=("scale:arkit_scene_depth:1",),
    )

    portion = estimate_portion_from_volume(
        component_name="cooked white rice",
        volume_estimate=estimate,
    )

    assert portion.grams_p10 == 117.0
    assert portion.grams_p50 == 150.0
    assert portion.grams_p90 == 198.0
    assert portion.percentiles_available is True
    assert portion.confidence == pytest.approx(0.74)
    assert portion.source == "volume_estimate_density_table"
    assert portion.uncertainty_flags == (
        "volume_geometry_estimate",
        "volume_density_estimate",
    )


def test_volume_estimate_uses_wide_generic_density_fallback_when_unknown() -> None:
    estimate = VolumeEstimate(
        volume_ml_p10=100.0,
        volume_ml_p50=120.0,
        volume_ml_p90=150.0,
        confidence=0.80,
        method="arkit_depth_region",
    )

    portion = estimate_portion_from_volume(
        component_name="mystery casserole",
        volume_estimate=estimate,
    )

    assert portion.grams_p10 == 30.0
    assert portion.grams_p50 == 78.0
    assert portion.grams_p90 == 157.5
    assert portion.confidence == pytest.approx(0.45)
    assert "generic_density_profile" in portion.uncertainty_flags


def test_density_profile_resolution_uses_component_and_category_hints() -> None:
    assert resolve_density_profile("americano").density_class == "generic_mixed_food"
    assert (
        resolve_density_profile("americano", category_hint="coffee drink").density_class
        == "beverage_or_soup"
    )
    assert resolve_density_profile("salmon fillet").density_class == "protein_solid"


def test_parse_volume_portion_range_alias_matches_primary_function() -> None:
    estimate = VolumeEstimate(
        volume_ml_p10=10.0,
        volume_ml_p50=20.0,
        volume_ml_p90=30.0,
        confidence=0.6,
        method="manual_container",
    )

    primary = estimate_portion_from_volume(
        component_name="olive oil",
        volume_estimate=estimate,
    )
    alias = parse_volume_portion_range(
        component_name="olive oil",
        volume_estimate=estimate,
    )

    assert alias == primary


def test_volume_estimate_rejects_invalid_percentile_ordering() -> None:
    with pytest.raises(ValidationError):
        VolumeEstimate(
            volume_ml_p10=120.0,
            volume_ml_p50=100.0,
            volume_ml_p90=130.0,
            confidence=0.8,
            method="arkit_depth_region",
        )
