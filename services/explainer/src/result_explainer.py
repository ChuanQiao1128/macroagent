from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from services.accounting import MacroBestEstimateSet
from services.meal import MealEstimate, MealUncertaintySignal

ExplanationLanguage = Literal["en", "zh"]
DEFAULT_MAX_UNCERTAINTY_DRIVERS = 3
_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")


class MealExplanationText(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    language: ExplanationLanguage
    summary: str = Field(..., min_length=1)
    top_uncertainty_drivers: tuple[str, ...] = Field(default_factory=tuple)
    recommended_user_question: str | None = None


class MealResultExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: str = Field(..., min_length=1)
    en: MealExplanationText
    zh: MealExplanationText


class ResultExplanationFormatter(Protocol):
    strategy: str

    def render(
        self,
        *,
        language: ExplanationLanguage,
        meal_estimate: MealEstimate,
        best_estimate: MacroBestEstimateSet,
        top_uncertainty_signals: Sequence[MealUncertaintySignal],
    ) -> MealExplanationText: ...


class DeterministicResultExplanationFormatter:
    strategy = "deterministic_template_v1"

    def render(
        self,
        *,
        language: ExplanationLanguage,
        meal_estimate: MealEstimate,
        best_estimate: MacroBestEstimateSet,
        top_uncertainty_signals: Sequence[MealUncertaintySignal],
    ) -> MealExplanationText:
        summary = _build_summary(
            language=language,
            meal_estimate=meal_estimate,
            best_estimate=best_estimate,
        )
        drivers = tuple(
            _format_uncertainty_driver(language=language, signal=signal)
            for signal in top_uncertainty_signals
        )

        return MealExplanationText(
            language=language,
            summary=summary,
            top_uncertainty_drivers=drivers,
            recommended_user_question=meal_estimate.recommended_user_question,
        )


def build_meal_result_explanation(
    *,
    meal_estimate: MealEstimate,
    best_estimate: MacroBestEstimateSet,
    formatter: ResultExplanationFormatter | None = None,
    max_uncertainty_drivers: int = DEFAULT_MAX_UNCERTAINTY_DRIVERS,
) -> MealResultExplanation:
    if max_uncertainty_drivers <= 0:
        raise ValueError("max_uncertainty_drivers must be greater than 0")

    selected_signals = _select_top_uncertainty_signals(
        meal_estimate.uncertainty_signals,
        limit=max_uncertainty_drivers,
    )
    active_formatter = formatter or DeterministicResultExplanationFormatter()

    en_text = active_formatter.render(
        language="en",
        meal_estimate=meal_estimate,
        best_estimate=best_estimate,
        top_uncertainty_signals=selected_signals,
    )
    zh_text = active_formatter.render(
        language="zh",
        meal_estimate=meal_estimate,
        best_estimate=best_estimate,
        top_uncertainty_signals=selected_signals,
    )

    _assert_no_new_numbers(
        texts=(en_text, zh_text),
        meal_estimate=meal_estimate,
        best_estimate=best_estimate,
    )
    return MealResultExplanation(
        strategy=active_formatter.strategy,
        en=en_text,
        zh=zh_text,
    )


def _build_summary(
    *,
    language: ExplanationLanguage,
    meal_estimate: MealEstimate,
    best_estimate: MacroBestEstimateSet,
) -> str:
    if meal_estimate.estimate_status == "complete":
        kcal_min = meal_estimate.macro_interval.kcal.min
        kcal_max = meal_estimate.macro_interval.kcal.max
        kcal_best = best_estimate.kcal.value
        if language == "zh":
            return (
                "估算完整。kcal 区间 "
                f"{kcal_min} 到 {kcal_max}；最佳估计 {kcal_best}。"
            )
        return (
            "Complete estimate. "
            f"kcal range {kcal_min} to {kcal_max}; best estimate {kcal_best}."
        )

    if language == "zh":
        return "估算不完整。标签：known-components-only。"
    return "Incomplete estimate. Label: known-components-only."


def _format_uncertainty_driver(
    *,
    language: ExplanationLanguage,
    signal: MealUncertaintySignal,
) -> str:
    if language == "zh":
        return (
            f"{signal.component_name} | 来源: {signal.source} | 影响: {signal.impact} | "
            f"{signal.reason}"
        )
    return (
        f"{signal.component_name} | source: {signal.source} | impact: {signal.impact} | "
        f"{signal.reason}"
    )


def _select_top_uncertainty_signals(
    signals: Sequence[MealUncertaintySignal],
    *,
    limit: int,
) -> tuple[MealUncertaintySignal, ...]:
    ranked = sorted(signals, key=lambda signal: signal.impact_score, reverse=True)
    return tuple(ranked[:limit])


def _assert_no_new_numbers(
    *,
    texts: Sequence[MealExplanationText],
    meal_estimate: MealEstimate,
    best_estimate: MacroBestEstimateSet,
) -> None:
    allowed_number_tokens = _collect_number_tokens_from_value(
        {
            "meal_estimate": meal_estimate.model_dump(mode="json"),
            "best_estimate": best_estimate.model_dump(mode="json"),
        }
    )

    rendered_text = {
        "summary": [text.summary for text in texts],
        "top_uncertainty_drivers": [
            driver
            for text in texts
            for driver in text.top_uncertainty_drivers
        ],
        "recommended_user_question": [
            text.recommended_user_question for text in texts if text.recommended_user_question
        ],
    }
    used_number_tokens = _collect_number_tokens_from_value(rendered_text)
    unexpected_tokens = sorted(
        token for token in used_number_tokens if token not in allowed_number_tokens
    )
    if unexpected_tokens:
        joined = ", ".join(unexpected_tokens)
        raise ValueError(f"explanation introduced numeric tokens not found in trace: {joined}")


def _collect_number_tokens_from_value(value: object) -> set[str]:
    tokens: set[str] = set()

    if isinstance(value, bool) or value is None:
        return tokens
    if isinstance(value, (int, float)):
        tokens.add(str(value))
        return tokens
    if isinstance(value, str):
        tokens.update(_NUMBER_PATTERN.findall(value))
        return tokens
    if isinstance(value, Mapping):
        for nested in value.values():
            tokens.update(_collect_number_tokens_from_value(nested))
        return tokens
    if isinstance(value, Sequence):
        for nested in value:
            tokens.update(_collect_number_tokens_from_value(nested))
        return tokens
    return tokens


__all__ = [
    "DEFAULT_MAX_UNCERTAINTY_DRIVERS",
    "DeterministicResultExplanationFormatter",
    "MealExplanationText",
    "MealResultExplanation",
    "ResultExplanationFormatter",
    "build_meal_result_explanation",
]
