from __future__ import annotations

import pytest

from services.accounting import calculate_meal_macro_best_estimate
from services.explainer import MealExplanationText, build_meal_result_explanation
from services.meal import analyze_meal_components
from services.vision import FoodComponent


class _CustomFormatter:
    strategy = "custom_formatter"

    def render(
        self,
        *,
        language: str,
        meal_estimate: object,
        best_estimate: object,
        top_uncertainty_signals: object,
    ) -> MealExplanationText:
        del best_estimate
        signal_names = tuple(
            getattr(signal, "component_name", "unknown")
            for signal in top_uncertainty_signals
        )
        return MealExplanationText(
            language=language,  # type: ignore[arg-type]
            summary=f"{language} custom summary",
            top_uncertainty_drivers=signal_names,
            recommended_user_question=getattr(meal_estimate, "recommended_user_question", None),
        )


class _ForbiddenNumberFormatter:
    strategy = "forbidden_number_formatter"

    def render(
        self,
        *,
        language: str,
        meal_estimate: object,
        best_estimate: object,
        top_uncertainty_signals: object,
    ) -> MealExplanationText:
        del meal_estimate, best_estimate, top_uncertainty_signals
        return MealExplanationText(
            language=language,  # type: ignore[arg-type]
            summary="Injected out-of-trace number 9999.",
            top_uncertainty_drivers=("driver 8888",),
            recommended_user_question=None,
        )


def test_complete_meal_summary_includes_kcal_range_and_best_estimate() -> None:
    meal = analyze_meal_components(
        [FoodComponent(name="white rice", confidence=0.91, portion_hint="100 g")]
    )
    best_estimate = calculate_meal_macro_best_estimate(meal.macro_interval)

    explanation = build_meal_result_explanation(
        meal_estimate=meal,
        best_estimate=best_estimate,
    )

    assert explanation.strategy == "deterministic_template_v1"
    assert (
        explanation.en.summary
        == "Complete estimate. kcal range 117.0 to 143.0; best estimate 130.0."
    )
    assert explanation.zh.summary == "估算完整。kcal 区间 117.0 到 143.0；最佳估计 130.0。"
    assert explanation.en.top_uncertainty_drivers == ()
    assert explanation.zh.top_uncertainty_drivers == ()
    assert explanation.en.recommended_user_question is None
    assert explanation.zh.recommended_user_question is None


def test_high_impact_incomplete_meal_includes_drivers_and_question() -> None:
    meal = analyze_meal_components(
        [
            FoodComponent(
                name="mystery creamy sauce drizzle",
                confidence=0.65,
                portion_hint="1 cup",
            )
        ],
        confident_match_score=1.0,
    )
    best_estimate = calculate_meal_macro_best_estimate(meal.macro_interval)

    explanation = build_meal_result_explanation(
        meal_estimate=meal,
        best_estimate=best_estimate,
    )

    assert meal.estimate_status == "incomplete_high_impact"
    assert explanation.en.summary == "Incomplete estimate. Label: known-components-only."
    assert explanation.zh.summary == "估算不完整。标签：known-components-only。"
    assert len(explanation.en.top_uncertainty_drivers) == 1
    assert "source: unmatched_component" in explanation.en.top_uncertainty_drivers[0]
    assert "impact: high" in explanation.en.top_uncertainty_drivers[0]
    assert len(explanation.zh.top_uncertainty_drivers) == 1
    assert "来源: unmatched_component" in explanation.zh.top_uncertainty_drivers[0]
    assert "影响: high" in explanation.zh.top_uncertainty_drivers[0]
    assert explanation.en.recommended_user_question == meal.recommended_user_question
    assert explanation.en.recommended_user_question is not None
    assert "creamy or oily sauce" in explanation.en.recommended_user_question
    assert explanation.zh.recommended_user_question == meal.recommended_user_question


def test_no_matched_components_remain_known_components_only() -> None:
    meal = analyze_meal_components(
        [FoodComponent(name="mystery foam", confidence=0.55, portion_hint="some amount")]
    )
    best_estimate = calculate_meal_macro_best_estimate(meal.macro_interval)

    explanation = build_meal_result_explanation(
        meal_estimate=meal,
        best_estimate=best_estimate,
    )

    assert meal.matched_component_count == 0
    assert meal.unmatched_component_count == 1
    assert explanation.en.summary == "Incomplete estimate. Label: known-components-only."
    assert explanation.zh.summary == "估算不完整。标签：known-components-only。"
    assert len(explanation.en.top_uncertainty_drivers) == 1
    assert explanation.en.top_uncertainty_drivers[0].startswith(
        "mystery foam | source: unmatched_component | impact: low | "
    )
    assert explanation.en.recommended_user_question is None
    assert explanation.zh.recommended_user_question is None


def test_build_meal_result_explanation_supports_custom_formatter_seam() -> None:
    meal = analyze_meal_components(
        [FoodComponent(name="white rice", confidence=0.91, portion_hint="100 g")]
    )
    best_estimate = calculate_meal_macro_best_estimate(meal.macro_interval)

    explanation = build_meal_result_explanation(
        meal_estimate=meal,
        best_estimate=best_estimate,
        formatter=_CustomFormatter(),
    )

    assert explanation.strategy == "custom_formatter"
    assert explanation.en.summary == "en custom summary"
    assert explanation.zh.summary == "zh custom summary"
    assert explanation.en.top_uncertainty_drivers == ()
    assert explanation.zh.top_uncertainty_drivers == ()


def test_build_meal_result_explanation_rejects_new_numeric_tokens_from_formatter() -> None:
    meal = analyze_meal_components(
        [FoodComponent(name="white rice", confidence=0.91, portion_hint="100 g")]
    )
    best_estimate = calculate_meal_macro_best_estimate(meal.macro_interval)

    with pytest.raises(ValueError, match="introduced numeric tokens"):
        build_meal_result_explanation(
            meal_estimate=meal,
            best_estimate=best_estimate,
            formatter=_ForbiddenNumberFormatter(),
        )
