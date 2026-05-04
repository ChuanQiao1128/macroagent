from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.accounting import (
    FoodMacroInterval,
    MealMacroInterval,
    aggregate_meal_macro_interval,
    calculate_food_macro_interval,
)
from services.meal.src.component_normalizer import (
    NormalizedFoodCandidate,
    normalize_meal_components,
)
from services.nutrition import (
    MacroMatchCandidate,
    PortionGramRange,
    match_food_candidates,
    parse_portion_range,
)
from services.vision import FoodComponent, VisionAnalysisResponse

DEFAULT_CANDIDATE_LIMIT = 3
DEFAULT_MIN_MATCH_SCORE = 0.60
DEFAULT_CONFIDENT_MATCH_SCORE = 0.70


class ComponentMatchCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    macro_entry_id: str = Field(..., min_length=1)
    macro_entry_name: str = Field(..., min_length=1)
    macro_entry_source: Literal["USDA", "PERSONAL"]
    score: float = Field(..., ge=0, le=1)
    matched_on: str = Field(..., min_length=1)
    match_type: Literal[
        "exact_name",
        "exact_alias",
        "token_containment",
        "fuzzy",
    ]
    reason: str = Field(..., min_length=1)


class MealComponentEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    component_name: str = Field(..., min_length=1)
    component_confidence: float = Field(..., ge=0, le=1)
    portion_hint: str | None = None
    status: Literal["matched", "unmatched"]
    top_candidates: tuple[ComponentMatchCandidate, ...] = Field(default_factory=tuple)
    selected_macro_entry_id: str | None = None
    selected_macro_entry_name: str | None = None
    selected_macro_entry_source: Literal["USDA", "PERSONAL"] | None = None
    selected_match_score: float | None = Field(default=None, ge=0, le=1)
    portion_range: PortionGramRange
    macro_interval: FoodMacroInterval | None = None
    unmatched_reason: str | None = None

    @model_validator(mode="after")
    def _validate_status_fields(self) -> MealComponentEstimate:
        if self.status == "matched":
            if (
                self.selected_macro_entry_id is None
                or self.selected_macro_entry_name is None
                or self.selected_macro_entry_source is None
                or self.selected_match_score is None
                or self.macro_interval is None
            ):
                raise ValueError("matched component must include selected entry and macro interval")
            if self.unmatched_reason is not None:
                raise ValueError("matched component must not include unmatched_reason")
            return self

        if self.selected_macro_entry_id is not None:
            raise ValueError("unmatched component must not include selected_macro_entry_id")
        if self.selected_macro_entry_name is not None:
            raise ValueError("unmatched component must not include selected_macro_entry_name")
        if self.selected_macro_entry_source is not None:
            raise ValueError("unmatched component must not include selected_macro_entry_source")
        if self.selected_match_score is not None:
            raise ValueError("unmatched component must not include selected_match_score")
        if self.macro_interval is not None:
            raise ValueError("unmatched component must not include macro_interval")
        if not self.unmatched_reason:
            raise ValueError("unmatched component must include unmatched_reason")
        return self


class MealEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    component_estimates: tuple[MealComponentEstimate, ...] = Field(default_factory=tuple)
    matched_component_count: int = Field(..., ge=0)
    unmatched_component_count: int = Field(..., ge=0)
    macro_interval: MealMacroInterval

    @model_validator(mode="after")
    def _validate_counts(self) -> MealEstimate:
        matched_count = sum(
            1 for component in self.component_estimates if component.status == "matched"
        )
        unmatched_count = len(self.component_estimates) - matched_count
        if self.matched_component_count != matched_count:
            raise ValueError("matched_component_count does not match component_estimates")
        if self.unmatched_component_count != unmatched_count:
            raise ValueError("unmatched_component_count does not match component_estimates")
        return self


def analyze_meal_components(
    components: Sequence[FoodComponent] | VisionAnalysisResponse,
    *,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    min_match_score: float = DEFAULT_MIN_MATCH_SCORE,
    confident_match_score: float = DEFAULT_CONFIDENT_MATCH_SCORE,
) -> MealEstimate:
    """Map vision components into deterministic nutrition estimates."""
    if candidate_limit <= 0:
        raise ValueError("candidate_limit must be greater than 0")
    if not 0 <= min_match_score <= 1:
        raise ValueError("min_match_score must be within [0, 1]")
    if not 0 <= confident_match_score <= 1:
        raise ValueError("confident_match_score must be within [0, 1]")

    normalized_components = normalize_meal_components(components)

    component_estimates: list[MealComponentEstimate] = []
    matched_intervals: list[FoodMacroInterval] = []

    for component in normalized_components.components:
        portion_range = parse_portion_range(
            component_name=component.name,
            portion_hint=component.portion_hint,
        )
        raw_candidates = match_food_candidates(
            _extract_query_candidates(
                component_name=component.name,
                component_candidates=component.top_food_candidates,
            ),
            state_hints=tuple(
                (state_hint.state, state_hint.confidence) for state_hint in component.state_hints
            ),
            limit=candidate_limit,
            min_score=min_match_score,
        )
        top_candidates = tuple(_to_component_candidate(candidate) for candidate in raw_candidates)

        selected = raw_candidates[0] if raw_candidates else None
        if selected is not None and selected.score >= confident_match_score:
            macro_interval = calculate_food_macro_interval(
                entry=selected.entry,
                gram_range=portion_range,
            )
            matched_intervals.append(macro_interval)
            component_estimates.append(
                MealComponentEstimate(
                    component_name=component.name,
                    component_confidence=component.confidence,
                    portion_hint=component.portion_hint,
                    status="matched",
                    top_candidates=top_candidates,
                    selected_macro_entry_id=selected.entry.id,
                    selected_macro_entry_name=selected.entry.name,
                    selected_macro_entry_source=selected.entry.source,
                    selected_match_score=selected.score,
                    portion_range=portion_range,
                    macro_interval=macro_interval,
                )
            )
            continue

        if selected is None:
            unmatched_reason = (
                f"no food match candidate met min_match_score={min_match_score:.2f}"
            )
        else:
            unmatched_reason = (
                "top food match candidate score "
                f"{selected.score:.3f} below confident_match_score={confident_match_score:.2f}"
            )

        component_estimates.append(
            MealComponentEstimate(
                component_name=component.name,
                component_confidence=component.confidence,
                portion_hint=component.portion_hint,
                status="unmatched",
                top_candidates=top_candidates,
                portion_range=portion_range,
                unmatched_reason=unmatched_reason,
            )
        )

    meal_interval = aggregate_meal_macro_interval(matched_intervals)
    return MealEstimate(
        component_estimates=tuple(component_estimates),
        matched_component_count=len(matched_intervals),
        unmatched_component_count=len(component_estimates) - len(matched_intervals),
        macro_interval=meal_interval,
    )


def estimate_meal_from_components(
    components: Sequence[FoodComponent] | VisionAnalysisResponse,
    *,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    min_match_score: float = DEFAULT_MIN_MATCH_SCORE,
    confident_match_score: float = DEFAULT_CONFIDENT_MATCH_SCORE,
) -> MealEstimate:
    """Compatibility alias for analyze_meal_components()."""
    return analyze_meal_components(
        components,
        candidate_limit=candidate_limit,
        min_match_score=min_match_score,
        confident_match_score=confident_match_score,
    )


def _to_component_candidate(candidate: MacroMatchCandidate) -> ComponentMatchCandidate:
    entry = candidate.entry
    return ComponentMatchCandidate(
        macro_entry_id=entry.id,
        macro_entry_name=entry.name,
        macro_entry_source=entry.source,
        score=candidate.score,
        matched_on=candidate.matched_on,
        match_type=candidate.match_type,
        reason=candidate.reason,
    )


def _extract_query_candidates(
    *,
    component_name: str,
    component_candidates: Sequence[NormalizedFoodCandidate],
) -> tuple[tuple[str, float], ...]:
    normalized_candidates: dict[str, tuple[str, float]] = {}

    for candidate in component_candidates:
        candidate_name = getattr(candidate, "name", None)
        candidate_confidence = getattr(candidate, "confidence", None)
        if not isinstance(candidate_name, str):
            continue
        normalized_name = " ".join(candidate_name.casefold().split())
        if not normalized_name:
            continue
        confidence = _clamp_confidence(candidate_confidence, fallback=1.0)

        existing = normalized_candidates.get(normalized_name)
        if existing is None or confidence > existing[1]:
            normalized_candidates[normalized_name] = (candidate_name, confidence)

    if normalized_candidates:
        return tuple(normalized_candidates.values())

    fallback_name = " ".join(component_name.split())
    if not fallback_name:
        return ()
    return ((fallback_name, 1.0),)


def _clamp_confidence(value: object, *, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(0.0, min(1.0, parsed))


__all__ = [
    "ComponentMatchCandidate",
    "DEFAULT_CANDIDATE_LIMIT",
    "DEFAULT_CONFIDENT_MATCH_SCORE",
    "DEFAULT_MIN_MATCH_SCORE",
    "MealComponentEstimate",
    "MealEstimate",
    "analyze_meal_components",
    "estimate_meal_from_components",
]
