from __future__ import annotations

from services.meal import PortionCorrectionPrior, analyze_meal_components
from services.vision import FoodComponent


def test_analyze_meal_components_applies_correction_prior_after_threshold_with_trace() -> None:
    resolver_calls: list[tuple[str, str | None, str | None]] = []

    def correction_prior_resolver(
        component_name: str,
        selected_macro_entry_id: str | None,
        selected_macro_entry_source: str | None,
    ) -> PortionCorrectionPrior:
        resolver_calls.append(
            (component_name, selected_macro_entry_id, selected_macro_entry_source)
        )
        return PortionCorrectionPrior(
            strategy="macro_entry",
            reference="USDA:usda_seed_0001",
            sample_count=3,
            grams_p50=95.0,
        )

    meal = analyze_meal_components(
        [FoodComponent(name="white rice", confidence=0.91, portion_hint="100 g")],
        correction_prior_resolver=correction_prior_resolver,
        correction_prior_minimum_samples=3,
    )

    assert resolver_calls == [("white rice", "usda_seed_0001", "USDA")]
    component = meal.component_estimates[0]
    assert component.portion_range.grams_p10 == 90.0
    assert component.portion_range.grams_p50 == 95.0
    assert component.portion_range.grams_p90 == 110.0

    assert component.applied_portion_prior is not None
    assert component.applied_portion_prior.strategy == "macro_entry"
    assert component.applied_portion_prior.reference == "USDA:usda_seed_0001"
    assert component.applied_portion_prior.sample_count == 3
    assert component.applied_portion_prior.prior_grams_p50 == 95.0
    assert component.applied_portion_prior.original_grams_p50 == 100.0
    assert component.applied_portion_prior.applied_grams_p50 == 95.0
    assert (
        "p50 adjusted via correction prior (macro_entry, n=3, prior_p50=95g)"
        in component.portion_range.reason
    )


def test_analyze_meal_components_does_not_apply_correction_prior_before_threshold() -> None:
    def correction_prior_resolver(
        _component_name: str,
        _selected_macro_entry_id: str | None,
        _selected_macro_entry_source: str | None,
    ) -> PortionCorrectionPrior:
        return PortionCorrectionPrior(
            strategy="macro_entry",
            reference="USDA:usda_seed_0001",
            sample_count=2,
            grams_p50=95.0,
        )

    meal = analyze_meal_components(
        [FoodComponent(name="white rice", confidence=0.91, portion_hint="100 g")],
        correction_prior_resolver=correction_prior_resolver,
        correction_prior_minimum_samples=3,
    )

    component = meal.component_estimates[0]
    assert component.portion_range.grams_p50 == 100.0
    assert component.applied_portion_prior is None
    assert "p50 adjusted via correction prior" not in component.portion_range.reason


def test_analyze_meal_components_applies_normalized_component_prior_strategy() -> None:
    def correction_prior_resolver(
        _component_name: str,
        _selected_macro_entry_id: str | None,
        _selected_macro_entry_source: str | None,
    ) -> PortionCorrectionPrior:
        return PortionCorrectionPrior(
            strategy="normalized_component",
            reference="white rice",
            sample_count=4,
            grams_p50=105.0,
        )

    meal = analyze_meal_components(
        [FoodComponent(name="white rice", confidence=0.91, portion_hint="100 g")],
        correction_prior_resolver=correction_prior_resolver,
        correction_prior_minimum_samples=3,
    )

    component = meal.component_estimates[0]
    assert component.portion_range.grams_p50 == 105.0
    assert component.applied_portion_prior is not None
    assert component.applied_portion_prior.strategy == "normalized_component"
    assert component.applied_portion_prior.reference == "white rice"
    assert component.applied_portion_prior.sample_count == 4
