from __future__ import annotations

from typing import Literal

import pytest

from services.meal.takeoff.energy_density import (
    evaluate_component_energy_density,
    evaluate_meal_energy_density,
    run_energy_density_checks,
)


@pytest.mark.parametrize(
    ("kcal_best", "expected_decision"),
    [
        (240.0, "WARN"),
        (320.0, "CLARIFY"),
        (400.0, "BLOCK"),
    ],
)
def test_component_outlier_levels_emit_warn_clarify_block(
    kcal_best: float,
    expected_decision: Literal["WARN", "CLARIFY", "BLOCK"],
) -> None:
    result = evaluate_component_energy_density(
        {
            "component_id": "component-rice",
            "category": "cooked_grain",
            "kcal_best": kcal_best,
            "quantity_best": 100.0,
        }
    )

    assert result.scope == "component"
    assert result.decision == expected_decision
    assert result.reason == "density_above_expected_band"
    assert result.policy_ref == "energy_density_policy.yaml#per_component.cooked_grain"


def test_mixed_meal_aggregate_outlier_is_suppressed_when_components_pass() -> None:
    components = [
        {
            "component_id": "component-rice",
            "category": "cooked_grain",
            "kcal_best": 150.0,
            "quantity_best": 100.0,
        },
        {
            "component_id": "component-chicken",
            "category": "lean_meat",
            "kcal_best": 170.0,
            "quantity_best": 100.0,
        },
    ]
    meal = {
        "meal_id": "meal-mixed-1",
        "meal_type": "mixed_bowl",
        "kcal_best": 640.0,
        "quantity_best": 100.0,
    }

    audit = run_energy_density_checks(components=components, meal=meal)
    meal_check = evaluate_meal_energy_density(
        meal,
        component_checks=audit.component_checks,
    )

    assert [check.decision for check in audit.component_checks] == ["ACCEPT", "ACCEPT"]
    assert meal_check.decision == "ACCEPT"
    assert meal_check.suppressed is True
    assert meal_check.reason == "aggregate_outlier_suppressed_components_passed"
    assert meal_check.density_kcal_per_g == pytest.approx(6.4)

