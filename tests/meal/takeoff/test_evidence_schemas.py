from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.meal.takeoff.schemas import (
    EvidenceClaim,
    FoodIdentityClaim,
    MacroValueClaim,
    MealSignature,
    PersonalContainer,
    PortionRange,
    SourceQuality,
)


def test_strict_models_reject_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SourceQuality(
            identity_confidence="high",
            nutrition_value_confidence="medium",
            regional_relevance="high",
            verification_status="user_contributed",
            unexpected="field",
        )


def test_evidence_claim_discriminated_union_validates_by_claim_type() -> None:
    claim = EvidenceClaim(
        claim_id="claim-identity-1",
        source_type="vision",
        confidence_label="medium",
        confidence_score=0.62,
        evidence_refs=["image_sha256:abc"],
        evidence_timestamp="2026-05-05T00:00:00Z",
        payload={
            "claim_type": "food_identity",
            "component_id": "component-1",
            "raw_name": "white rice",
            "canonical_name": "cooked white rice",
            "taxonomy_category": "grain rice",
        },
    )

    assert isinstance(claim.payload, FoodIdentityClaim)
    assert claim.payload.claim_type == "food_identity"
    assert claim.payload.canonical_name == "cooked white rice"


def test_evidence_claim_wrong_payload_for_claim_type_fails_validation() -> None:
    with pytest.raises(ValidationError):
        EvidenceClaim(
            claim_id="claim-bad-payload",
            source_type="vision",
            confidence_label="medium",
            confidence_score=0.62,
            evidence_refs=["image_sha256:abc"],
            evidence_timestamp="2026-05-05T00:00:00Z",
            payload={
                "claim_type": "food_identity",
                "component_id": "component-1",
                "quantity_min": 160.0,
                "quantity_best": 190.0,
                "quantity_max": 220.0,
                "quantity_unit": "g",
            },
        )


def test_evidence_claim_payload_is_not_untyped_value_dict() -> None:
    assert "value" not in EvidenceClaim.model_fields
    assert "value" not in MacroValueClaim.model_fields

    with pytest.raises(ValidationError):
        EvidenceClaim(
            claim_id="claim-bad-value",
            source_type="vision",
            confidence_label="low",
            confidence_score=0.30,
            evidence_refs=["image_sha256:abc"],
            evidence_timestamp="2026-05-05T00:00:00Z",
            payload={
                "claim_type": "macro_value",
                "component_id": "component-1",
                "value": {"kcal": 200.0},
                "value_basis": "llm_raw",
            },
        )


def test_source_quality_represents_off_identity_high_nutrition_medium() -> None:
    quality = SourceQuality(
        identity_confidence="high",
        nutrition_value_confidence="medium",
        regional_relevance="medium",
        verification_status="user_contributed",
    )

    assert quality.identity_confidence == "high"
    assert quality.nutrition_value_confidence == "medium"


def test_portion_range_supports_multiple_scale_evidence_sources() -> None:
    portion = PortionRange(
        component_id="component-rice",
        quantity_unit="g",
        quantity_min=180.0,
        quantity_best=205.0,
        quantity_max=230.0,
        primary_basis="reference_object_calibrated",
        scale_evidence_ids=["scale-spoon", "scale-bowl"],
        portion_phase="as_consumed",
        consumption_fraction=0.75,
        confidence_label="medium",
        confidence_score=0.68,
        uncertainty_drivers=["bowl partly occluded"],
    )

    assert portion.scale_evidence_ids == ["scale-spoon", "scale-bowl"]
    assert portion.consumption_fraction == 0.75


def test_personal_container_uses_independent_dimension_defaults() -> None:
    first = PersonalContainer(
        container_id="container-1",
        user_id="user-1",
        name="rice bowl",
        calibration_source="user_measured",
        calibration_confidence="high",
        created_at="2026-05-05T00:00:00Z",
        updated_at="2026-05-05T00:00:00Z",
    )
    second = PersonalContainer(
        container_id="container-2",
        user_id="user-1",
        name="small plate",
        calibration_source="user_estimated",
        calibration_confidence="low",
        created_at="2026-05-05T00:00:00Z",
        updated_at="2026-05-05T00:00:00Z",
    )

    first.dimensions_mm["height"] = 80.0

    assert second.dimensions_mm == {}


def test_meal_signature_validates_takeoff_identity_fields() -> None:
    signature = MealSignature(
        signature_hash="meal-sig-abc",
        component_categories=["grain", "protein"],
        normalized_components=["cooked white rice", "salmon sushi"],
        cuisine_tags=["japanese"],
        meal_type="plated_meal",
        restaurant_or_brand="local sushi shop",
    )

    assert signature.meal_type == "plated_meal"
    assert signature.normalized_components == ["cooked white rice", "salmon sushi"]
