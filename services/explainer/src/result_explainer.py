from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
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
        top_uncertainty_signals=selected_signals,
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
    detail = _build_uncertainty_driver_detail(language=language, signal=signal)
    if language == "zh":
        return f"{signal.component_name} | 来源: {signal.source} | 影响: {signal.impact} | {detail}"
    return (
        f"{signal.component_name} | source: {signal.source} | impact: {signal.impact} | {detail}"
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
    top_uncertainty_signals: Sequence[MealUncertaintySignal],
) -> None:
    summary_allowed_number_tokens = _collect_number_tokens_from_value(
        (
            meal_estimate.macro_interval.kcal.min,
            meal_estimate.macro_interval.kcal.max,
            best_estimate.kcal.value,
        )
    )
    driver_allowed_number_tokens = _collect_number_tokens_from_value(
        tuple(
            {
                "estimated_kcal_delta": signal.estimated_kcal_delta,
                "estimated_fat_g_delta": signal.estimated_fat_g_delta,
            }
            for signal in top_uncertainty_signals
        )
    )
    question_allowed_number_tokens = _collect_number_tokens_from_value(
        tuple(
            question
            for question in (
                meal_estimate.recommended_user_question,
                *[signal.recommended_question for signal in top_uncertainty_signals],
            )
            if question
        )
    )

    _assert_field_numbers_within_allowed(
        field_name="summary",
        values=tuple(text.summary for text in texts),
        allowed_tokens=summary_allowed_number_tokens,
    )
    _assert_field_numbers_within_allowed(
        field_name="top_uncertainty_drivers",
        values=tuple(
            driver
            for text in texts
            for driver in text.top_uncertainty_drivers
        ),
        allowed_tokens=driver_allowed_number_tokens,
    )
    _assert_field_numbers_within_allowed(
        field_name="recommended_user_question",
        values=tuple(
            text.recommended_user_question
            for text in texts
            if text.recommended_user_question
        ),
        allowed_tokens=question_allowed_number_tokens,
    )

def _assert_field_numbers_within_allowed(
    *,
    field_name: str,
    values: Sequence[str],
    allowed_tokens: set[str],
) -> None:
    used_number_tokens = _collect_number_tokens_from_value(values)
    unexpected_tokens = sorted(token for token in used_number_tokens if token not in allowed_tokens)
    if unexpected_tokens:
        joined = ", ".join(unexpected_tokens)
        raise ValueError(
            "explanation introduced numeric tokens not allowed in "
            f"{field_name}: {joined}"
        )


def _collect_number_tokens_from_value(value: object) -> set[str]:
    tokens: set[str] = set()

    if isinstance(value, bool) or value is None:
        return tokens
    if isinstance(value, (int, float)):
        tokens.add(_normalize_number_token(str(value)))
        return tokens
    if isinstance(value, str):
        tokens.update(_normalize_number_token(token) for token in _NUMBER_PATTERN.findall(value))
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


def _normalize_number_token(token: str) -> str:
    normalized_input = token.strip()
    if not normalized_input:
        return normalized_input
    try:
        decimal_value = Decimal(normalized_input)
    except InvalidOperation:
        return normalized_input

    normalized = format(decimal_value.normalize(), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    if normalized in {"-0", "+0", ""}:
        return "0"
    return normalized


def _build_uncertainty_driver_detail(
    *,
    language: ExplanationLanguage,
    signal: MealUncertaintySignal,
) -> str:
    zh_source = "隐藏配料风险" if signal.source == "hidden_ingredient_risk" else "未匹配食材"
    zh_impact = "高" if signal.impact == "high" else "低"
    if language == "zh":
        if signal.source == "hidden_ingredient_risk":
            return (
                f"{zh_source}（{zh_impact}影响）；"
                f"潜在增量约 {signal.estimated_kcal_delta} kcal，"
                f"{signal.estimated_fat_g_delta} g 脂肪。"
            )
        if signal.impact == "high":
            return (
                f"{zh_source}（{zh_impact}影响）；"
                f"潜在增量约 {signal.estimated_kcal_delta} kcal，"
                f"{signal.estimated_fat_g_delta} g 脂肪。"
            )
        return (
            f"{zh_source}（{zh_impact}影响）；"
            f"潜在增量约 {signal.estimated_kcal_delta} kcal，"
            f"{signal.estimated_fat_g_delta} g 脂肪。"
        )

    source_label = (
        "hidden ingredient risk"
        if signal.source == "hidden_ingredient_risk"
        else "unmatched component"
    )
    if signal.source == "hidden_ingredient_risk":
        return (
            f"{source_label} ({signal.impact} impact); "
            f"estimated delta about {signal.estimated_kcal_delta} kcal and "
            f"{signal.estimated_fat_g_delta} g fat."
        )
    if signal.impact == "high":
        return (
            f"{source_label} ({signal.impact} impact); "
            f"estimated delta about {signal.estimated_kcal_delta} kcal and "
            f"{signal.estimated_fat_g_delta} g fat."
        )
    return (
        f"{source_label} ({signal.impact} impact); "
        f"estimated delta about {signal.estimated_kcal_delta} kcal and "
        f"{signal.estimated_fat_g_delta} g fat."
    )


__all__ = [
    "DEFAULT_MAX_UNCERTAINTY_DRIVERS",
    "DeterministicResultExplanationFormatter",
    "MealExplanationText",
    "MealResultExplanation",
    "ResultExplanationFormatter",
    "build_meal_result_explanation",
]
