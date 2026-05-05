from __future__ import annotations

import pytest

from services.meal.takeoff.evidence_arbitration import (
    arbitrate_evidence_claims,
    calibrate_confidence_score,
    load_evidence_arbitration_policy,
)
from services.meal.takeoff.schemas import (
    EvidenceClaim,
    FoodIdentityClaim,
    MacroValueClaim,
    PortionQuantityClaim,
)


def _claim(
    claim_id: str,
    payload: FoodIdentityClaim | MacroValueClaim | PortionQuantityClaim,
    *,
    source_type: str = "vision",
    confidence_label: str = "medium",
    confidence_score: float = 0.60,
) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=claim_id,
        source_type=source_type,
        confidence_label=confidence_label,
        confidence_score=confidence_score,
        evidence_refs=[f"evidence:{claim_id}"],
        evidence_timestamp="2026-05-05T00:00:00Z",
        payload=payload,
    )


def test_policy_file_loads_expected_thresholds() -> None:
    policy = load_evidence_arbitration_policy()

    assert policy["conflict_detection"]["portion_quantity"]["compatibility_threshold"] == 0.50
    assert policy["conflict_detection"]["macro_value"]["conflict_threshold"] == 0.20


def test_compatible_portion_claims_merge_before_conflict() -> None:
    claims = [
        _claim(
            "portion-vision",
            PortionQuantityClaim(
                claim_type="portion_quantity",
                component_id="component-rice",
                quantity_min=160.0,
                quantity_best=190.0,
                quantity_max=220.0,
                quantity_unit="g",
            ),
            source_type="vision",
            confidence_score=0.58,
        ),
        _claim(
            "portion-container",
            PortionQuantityClaim(
                claim_type="portion_quantity",
                component_id="component-rice",
                quantity_min=180.0,
                quantity_best=205.0,
                quantity_max=230.0,
                quantity_unit="g",
            ),
            source_type="personal_prior",
            confidence_score=0.75,
        ),
    ]

    result = arbitrate_evidence_claims(claims)

    assert result.conflicts == []
    assert len(result.merged_claims) == 1
    merged_payload = result.merged_claims[0].payload
    assert isinstance(merged_payload, PortionQuantityClaim)
    assert merged_payload.quantity_min == 180.0
    assert merged_payload.quantity_best == pytest.approx(197.5)
    assert merged_payload.quantity_max == 220.0
    assert result.merged_claims[0].claim_id == "merged:portion-container+portion-vision"


def test_incompatible_portion_claims_create_conflict() -> None:
    claims = [
        _claim(
            "portion-small",
            PortionQuantityClaim(
                claim_type="portion_quantity",
                component_id="component-rice",
                quantity_min=80.0,
                quantity_best=90.0,
                quantity_max=100.0,
                quantity_unit="g",
            ),
        ),
        _claim(
            "portion-large",
            PortionQuantityClaim(
                claim_type="portion_quantity",
                component_id="component-rice",
                quantity_min=200.0,
                quantity_best=220.0,
                quantity_max=240.0,
                quantity_unit="g",
            ),
        ),
    ]

    result = arbitrate_evidence_claims(claims)

    assert result.merged_claims == []
    assert len(result.conflicts) == 1
    assert result.conflicts[0].claim_type == "portion_quantity"
    assert result.conflicts[0].metric == "range_overlap"


def test_macro_claims_differing_more_than_twenty_percent_create_conflict() -> None:
    claims = [
        _claim(
            "macro-database",
            MacroValueClaim(
                claim_type="macro_value",
                component_id="component-rice",
                kcal=100.0,
                value_basis="database_source",
            ),
            source_type="nutrition_database",
        ),
        _claim(
            "macro-recompute",
            MacroValueClaim(
                claim_type="macro_value",
                component_id="component-rice",
                kcal=130.0,
                value_basis="deterministic_recompute",
            ),
            source_type="deterministic_calculator",
        ),
    ]

    result = arbitrate_evidence_claims(claims)

    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.claim_type == "macro_value"
    assert conflict.metric == "relative_diff:kcal"
    assert conflict.metric_value == pytest.approx(30.0 / 100.0)
    assert conflict.decision == "clarify_user"


def test_macro_claims_within_twenty_percent_do_not_conflict() -> None:
    claims = [
        _claim(
            "macro-database",
            MacroValueClaim(
                claim_type="macro_value",
                component_id="component-rice",
                kcal=100.0,
                protein_g=2.0,
                value_basis="database_source",
            ),
            source_type="nutrition_database",
        ),
        _claim(
            "macro-recompute",
            MacroValueClaim(
                claim_type="macro_value",
                component_id="component-rice",
                kcal=119.0,
                protein_g=2.3,
                value_basis="deterministic_recompute",
            ),
            source_type="deterministic_calculator",
        ),
    ]

    result = arbitrate_evidence_claims(claims)

    assert result.conflicts == []


def test_food_identity_category_mismatch_creates_conflict() -> None:
    claims = [
        _claim(
            "identity-rice",
            FoodIdentityClaim(
                claim_type="food_identity",
                component_id="component-1",
                raw_name="rice",
                taxonomy_category="grain rice",
            ),
        ),
        _claim(
            "identity-sauce",
            FoodIdentityClaim(
                claim_type="food_identity",
                component_id="component-1",
                raw_name="cream sauce",
                taxonomy_category="sauce dairy",
            ),
        ),
    ]

    result = arbitrate_evidence_claims(claims)

    assert len(result.conflicts) == 1
    assert result.conflicts[0].claim_type == "food_identity"
    assert result.conflicts[0].metric == "category_jaccard"


def test_confidence_calibration_loads_source_scores_from_yaml() -> None:
    assert calibrate_confidence_score("barcode_off_unverified", "medium") == pytest.approx(0.55)
    assert calibrate_confidence_score("user_correction", "high") == pytest.approx(0.95)

    with pytest.raises(KeyError):
        calibrate_confidence_score("unknown_source", "high")
