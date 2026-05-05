from __future__ import annotations

import pytest
import yaml

from services.meal.takeoff.macro_quantity import (
    aggregate_meal_macros,
    calculate_component_estimate,
    compute_component_macros,
)


def test_component_interval_and_meal_aggregation_sum_min_best_max() -> None:
    rice = compute_component_macros(
        source={
            "source_ref": "usda:rice",
            "kcal_per_100g": 130.0,
            "protein_g_per_100g": 2.4,
            "carbs_g_per_100g": 28.7,
            "fat_g_per_100g": 0.3,
        },
        portion_range={
            "quantity_min": 180.0,
            "quantity_best": 200.0,
            "quantity_max": 220.0,
            "quantity_unit": "g",
        },
        component_id="component-rice",
        name="white rice",
        category="cooked_grain",
    )
    chicken = compute_component_macros(
        source={
            "source_ref": "usda:chicken",
            "kcal_per_100g": 165.0,
            "protein_g_per_100g": 31.0,
            "carbs_g_per_100g": 0.0,
            "fat_g_per_100g": 3.6,
        },
        portion_range={
            "quantity_min": 90.0,
            "quantity_best": 110.0,
            "quantity_max": 130.0,
            "quantity_unit": "g",
        },
        component_id="component-chicken",
        name="chicken breast",
        category="lean_meat",
    )

    meal = aggregate_meal_macros([rice, chicken], meal_id="meal-123")

    assert rice.kcal_min == pytest.approx(234.0)
    assert rice.kcal_best == pytest.approx(260.0)
    assert rice.kcal_max == pytest.approx(286.0)
    assert rice.protein_best == pytest.approx(4.8)
    assert rice.carbs_best == pytest.approx(57.4)
    assert rice.fat_best == pytest.approx(0.6)

    assert meal.kcal_min == pytest.approx(382.5)
    assert meal.kcal_best == pytest.approx(441.5)
    assert meal.kcal_max == pytest.approx(500.5)
    assert meal.protein_min == pytest.approx(32.22)
    assert meal.protein_best == pytest.approx(38.9)
    assert meal.protein_max == pytest.approx(45.58)
    assert meal.carbs_min == pytest.approx(51.66)
    assert meal.carbs_best == pytest.approx(57.4)
    assert meal.carbs_max == pytest.approx(63.14)
    assert meal.fat_min == pytest.approx(3.78)
    assert meal.fat_best == pytest.approx(4.56)
    assert meal.fat_max == pytest.approx(5.34)
    assert meal.relative_range_width == pytest.approx((500.5 - 382.5) / 441.5)
    assert meal.decision_reason == "component_mode_sum"
    assert "component_mode_sum" in (aggregate_meal_macros.__doc__ or "")


def test_visible_unknown_sauce_uses_policy_nonzero_lower_bound() -> None:
    estimate = calculate_component_estimate(
        {
            "component_id": "component-sauce-visible",
            "name": "creamy sauce",
            "category": "sauce_creamy",
            "source": {"kcal_per_100g": 320.0},
            "unknown_component": {
                "component_type": "sauce",
                "family": "creamy",
                "presence_state": "visible_unknown_type",
                "visible_amount": "light",
                "quantity_unit": "ml",
            },
        }
    )

    assert estimate.portion_range.quantity_min > 0.0
    assert estimate.portion_range.quantity_min == pytest.approx(5.0)
    assert "uncertainty_policy.yaml#unknown_components.sauce.families.creamy.visible_light" in (
        estimate.policy_refs
    )


def test_suspected_hidden_oil_can_use_zero_lower_bound() -> None:
    estimate = calculate_component_estimate(
        {
            "component_id": "component-oil-hidden",
            "name": "possible hidden oil",
            "category": "oil_pure",
            "source": {"kcal_per_100g": 884.0},
            "unknown_component": {
                "component_type": "sauce",
                "family": "oil_based",
                "presence_state": "suspected_hidden",
                "quantity_unit": "ml",
            },
        }
    )

    assert estimate.portion_range.quantity_min == pytest.approx(0.0)
    assert estimate.portion_range.quantity_best == pytest.approx(5.0)
    assert estimate.portion_range.quantity_max == pytest.approx(15.0)


def test_right_skewed_unknown_component_preserves_shape_and_skew_hint() -> None:
    estimate = calculate_component_estimate(
        {
            "component_id": "component-oil-hidden",
            "name": "possible hidden oil",
            "category": "oil_pure",
            "source": {"kcal_per_100g": 884.0},
            "unknown_component": {
                "component_type": "sauce",
                "family": "oil_based",
                "presence_state": "suspected_hidden",
                "quantity_unit": "ml",
            },
        }
    )

    assert estimate.distribution_shape == "right_skewed"
    assert estimate.skew_hint == "policy_upper_tail:sauce/oil_based/suspected_hidden"


def test_unknown_component_bounds_are_loaded_from_policy_file(tmp_path) -> None:
    policy_path = tmp_path / "uncertainty_policy_custom.yaml"
    policy_path.write_text(
        yaml.safe_dump(
            {
                "version": "test-policy",
                "range_decision": {
                    "accept_relative_width_max": 0.35,
                    "warn_relative_width_max": 0.60,
                    "clarify_relative_width_min": 0.60,
                },
                "unknown_components": {
                    "sauce": {
                        "presence_states": {
                            "visible": {"lower_can_be_zero": False},
                            "visible_unknown": {"lower_can_be_zero": False},
                            "visible_unknown_type": {"lower_can_be_zero": False},
                            "suspected_hidden": {"lower_can_be_zero": True},
                            "not_visible": {"lower_can_be_zero": True},
                        },
                        "families": {
                            "oil_based": {
                                "default_quantity_ml": {
                                    "visible_light": {
                                        "min": 11,
                                        "best": 22,
                                        "max": 44,
                                    }
                                }
                            }
                        },
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    estimate = calculate_component_estimate(
        {
            "component_id": "component-oil-visible",
            "name": "visible oil",
            "category": "oil_pure",
            "source": {"kcal_per_100g": 884.0},
            "unknown_component": {
                "component_type": "sauce",
                "family": "oil_based",
                "presence_state": "visible",
                "visible_amount": "light",
                "quantity_unit": "ml",
            },
        },
        uncertainty_policy_path=policy_path,
    )

    assert estimate.portion_range.quantity_min == pytest.approx(11.0)
    assert estimate.portion_range.quantity_best == pytest.approx(22.0)
    assert estimate.portion_range.quantity_max == pytest.approx(44.0)
    assert (
        f"{policy_path.name}#unknown_components.sauce.families.oil_based.visible_light"
        in estimate.policy_refs
    )
