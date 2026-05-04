from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
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
    NormalizedHiddenIngredientRisk,
    normalize_meal_components,
)
from services.nutrition import (
    MacroMatchCandidate,
    PortionGramRange,
    match_food_candidates,
    parse_portion_range,
)
from services.nutrition.src.version_metadata import (
    TraceVersionMetadata,
    build_trace_version_metadata,
)
from services.vision import FoodComponent, VisionAnalysisResponse

DEFAULT_CANDIDATE_LIMIT = 3
DEFAULT_MIN_MATCH_SCORE = 0.60
DEFAULT_CONFIDENT_MATCH_SCORE = 0.70
DEFAULT_CORRECTION_PRIOR_MINIMUM_SAMPLES = 3
HIGH_IMPACT_KCAL_DELTA_THRESHOLD = 40.0
HIGH_IMPACT_FAT_DELTA_THRESHOLD = 4.0
DOMINANT_UNCERTAINTY_RATIO = 1.35


@dataclass(frozen=True)
class _HighImpactCategory:
    key: str
    phrases: tuple[str, ...]
    kcal_per_100g: float
    fat_g_per_100g: float
    unmatched_question_template: str


class MealUncertaintySignal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    component_name: str
    source: Literal["unmatched_component", "hidden_ingredient_risk"]
    impact: Literal["low", "high"]
    reason: str
    estimated_kcal_delta: float
    estimated_fat_g_delta: float
    recommended_question: str | None = None

    @property
    def impact_score(self) -> float:
        return self.estimated_kcal_delta + (self.estimated_fat_g_delta * 9.0)


class PortionCorrectionPrior(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: Literal["macro_entry", "normalized_component"]
    reference: str = Field(..., min_length=1)
    sample_count: int = Field(..., ge=1)
    grams_p50: float = Field(..., gt=0)


class AppliedPortionPriorTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: Literal["macro_entry", "normalized_component"]
    reference: str = Field(..., min_length=1)
    sample_count: int = Field(..., ge=1)
    prior_grams_p50: float = Field(..., gt=0)
    original_grams_p50: float = Field(..., ge=0)
    applied_grams_p50: float = Field(..., ge=0)


PortionPriorResolver = Callable[
    [str, str | None, Literal["USDA", "PERSONAL"] | None],
    PortionCorrectionPrior | None,
]


HIGH_IMPACT_CATEGORIES = (
    _HighImpactCategory(
        key="creamy_or_oily_sauce",
        phrases=(
            "sauce",
            "dressing",
            "gravy",
            "aioli",
            "mayo",
            "mayonnaise",
            "alfredo",
            "creamy",
            "oily sauce",
        ),
        kcal_per_100g=280.0,
        fat_g_per_100g=26.0,
        unmatched_question_template=(
            "Did {component_name} include a creamy or oily sauce? About how much was on the meal?"
        ),
    ),
    _HighImpactCategory(
        key="nuts_or_nut_butter",
        phrases=(
            "nut",
            "nuts",
            "walnut",
            "walnuts",
            "almond",
            "almonds",
            "nut butter",
            "peanut butter",
            "almond butter",
            "cashew butter",
            "hazelnut butter",
            "tahini",
        ),
        kcal_per_100g=600.0,
        fat_g_per_100g=50.0,
        unmatched_question_template=(
            "Did {component_name} include nuts or nut butter? About how much was included?"
        ),
    ),
    _HighImpactCategory(
        key="oil_or_butter",
        phrases=("oil", "butter", "buttered", "ghee", "margarine"),
        kcal_per_100g=884.0,
        fat_g_per_100g=100.0,
        unmatched_question_template=(
            "Was extra oil or butter used for {component_name}? About how much was used?"
        ),
    ),
    _HighImpactCategory(
        key="cheese_or_cream",
        phrases=("cheese", "cream", "cream cheese", "sour cream", "queso"),
        kcal_per_100g=360.0,
        fat_g_per_100g=30.0,
        unmatched_question_template=(
            "Did {component_name} include cheese or cream? About how much was added?"
        ),
    ),
    _HighImpactCategory(
        key="sugary_drink_or_dessert",
        phrases=(
            "dessert",
            "cake",
            "cookie",
            "brownie",
            "ice cream",
            "milkshake",
            "pastry",
            "donut",
            "soda",
            "cola",
            "sugary drink",
            "sweetened beverage",
            "sweetened drink",
            "sweet tea",
            "juice",
            "boba",
        ),
        kcal_per_100g=220.0,
        fat_g_per_100g=8.0,
        unmatched_question_template=(
            "Was there a sugary drink or dessert for {component_name}? What was it and how much?"
        ),
    ),
)
HIGH_IMPACT_BY_KEY = {category.key: category for category in HIGH_IMPACT_CATEGORIES}


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
    hidden_ingredient_risks: tuple[NormalizedHiddenIngredientRisk, ...] = Field(
        default_factory=tuple
    )
    applied_portion_prior: AppliedPortionPriorTrace | None = None
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

    estimate_status: Literal["complete", "incomplete_low_impact", "incomplete_high_impact"] = (
        "complete"
    )
    macro_range_label: Literal["full_meal", "known_components_only"] = "full_meal"
    component_estimates: tuple[MealComponentEstimate, ...] = Field(default_factory=tuple)
    matched_component_count: int = Field(..., ge=0)
    unmatched_component_count: int = Field(..., ge=0)
    macro_interval: MealMacroInterval
    uncertainty_signals: tuple[MealUncertaintySignal, ...] = Field(default_factory=tuple)
    recommended_user_question: str | None = None
    trace_versions: TraceVersionMetadata = Field(default_factory=build_trace_version_metadata)

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
    correction_prior_resolver: PortionPriorResolver | None = None,
    correction_prior_minimum_samples: int = DEFAULT_CORRECTION_PRIOR_MINIMUM_SAMPLES,
) -> MealEstimate:
    """Map vision components into deterministic nutrition estimates."""
    if candidate_limit <= 0:
        raise ValueError("candidate_limit must be greater than 0")
    if not 0 <= min_match_score <= 1:
        raise ValueError("min_match_score must be within [0, 1]")
    if not 0 <= confident_match_score <= 1:
        raise ValueError("confident_match_score must be within [0, 1]")
    if correction_prior_minimum_samples <= 0:
        raise ValueError("correction_prior_minimum_samples must be greater than 0")

    trace_versions = (
        components.trace_versions
        if isinstance(components, VisionAnalysisResponse)
        else build_trace_version_metadata()
    )
    normalized_components = normalize_meal_components(components)

    component_estimates: list[MealComponentEstimate] = []
    matched_intervals: list[FoodMacroInterval] = []
    uncertainty_signals: list[MealUncertaintySignal] = []

    for component in normalized_components.components:
        base_portion_range = parse_portion_range(
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
        macro_entry_id_for_prior: str | None = None
        macro_entry_source_for_prior: Literal["USDA", "PERSONAL"] | None = None
        if selected is not None and selected.score >= confident_match_score:
            macro_entry_id_for_prior = selected.entry.id
            macro_entry_source_for_prior = selected.entry.source

        applied_portion_prior: AppliedPortionPriorTrace | None = None
        portion_range = base_portion_range
        if correction_prior_resolver is not None:
            resolved_prior = correction_prior_resolver(
                component.name,
                macro_entry_id_for_prior,
                macro_entry_source_for_prior,
            )
            portion_range, applied_portion_prior = _apply_portion_prior(
                portion_range=base_portion_range,
                prior=resolved_prior,
                minimum_samples=correction_prior_minimum_samples,
            )

        uncertainty_signals.extend(
            _collect_hidden_risk_uncertainty_signals(
                component_name=component.name,
                portion_range=portion_range,
                hidden_ingredient_risks=component.hidden_ingredient_risks,
            )
        )

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
                    hidden_ingredient_risks=component.hidden_ingredient_risks,
                    applied_portion_prior=applied_portion_prior,
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
                hidden_ingredient_risks=component.hidden_ingredient_risks,
                applied_portion_prior=applied_portion_prior,
                unmatched_reason=unmatched_reason,
            )
        )
        uncertainty_signals.append(
            _build_unmatched_uncertainty_signal(
                component_name=component.name,
                component_confidence=component.confidence,
                portion_range=portion_range,
                top_candidates=top_candidates,
                unmatched_reason=unmatched_reason,
            )
        )

    meal_interval = aggregate_meal_macro_interval(matched_intervals)
    high_impact_present = any(signal.impact == "high" for signal in uncertainty_signals)
    if not uncertainty_signals:
        estimate_status: Literal["complete", "incomplete_low_impact", "incomplete_high_impact"] = (
            "complete"
        )
    elif high_impact_present:
        estimate_status = "incomplete_high_impact"
    else:
        estimate_status = "incomplete_low_impact"
    return MealEstimate(
        estimate_status=estimate_status,
        macro_range_label="full_meal" if not uncertainty_signals else "known_components_only",
        component_estimates=tuple(component_estimates),
        matched_component_count=len(matched_intervals),
        unmatched_component_count=len(component_estimates) - len(matched_intervals),
        macro_interval=meal_interval,
        uncertainty_signals=tuple(uncertainty_signals),
        recommended_user_question=_select_recommended_user_question(uncertainty_signals),
        trace_versions=trace_versions,
    )


def estimate_meal_from_components(
    components: Sequence[FoodComponent] | VisionAnalysisResponse,
    *,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    min_match_score: float = DEFAULT_MIN_MATCH_SCORE,
    confident_match_score: float = DEFAULT_CONFIDENT_MATCH_SCORE,
    correction_prior_resolver: PortionPriorResolver | None = None,
    correction_prior_minimum_samples: int = DEFAULT_CORRECTION_PRIOR_MINIMUM_SAMPLES,
) -> MealEstimate:
    """Compatibility alias for analyze_meal_components()."""
    return analyze_meal_components(
        components,
        candidate_limit=candidate_limit,
        min_match_score=min_match_score,
        confident_match_score=confident_match_score,
        correction_prior_resolver=correction_prior_resolver,
        correction_prior_minimum_samples=correction_prior_minimum_samples,
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


def _apply_portion_prior(
    *,
    portion_range: PortionGramRange,
    prior: PortionCorrectionPrior | None,
    minimum_samples: int,
) -> tuple[PortionGramRange, AppliedPortionPriorTrace | None]:
    if prior is None or prior.sample_count < minimum_samples:
        return portion_range, None

    prior_p50 = _round_one_decimal(prior.grams_p50)
    applied_p10 = portion_range.grams_p10
    applied_p90 = portion_range.grams_p90
    if prior_p50 < portion_range.grams_p10 or prior_p50 > portion_range.grams_p90:
        lower_spread = max(0.0, portion_range.grams_p50 - portion_range.grams_p10)
        upper_spread = max(0.0, portion_range.grams_p90 - portion_range.grams_p50)
        applied_p10 = _round_one_decimal(max(0.0, prior_p50 - lower_spread))
        applied_p90 = _round_one_decimal(max(prior_p50, prior_p50 + upper_spread))

    applied_range = PortionGramRange(
        grams_min=applied_p10,
        grams_max=applied_p90,
        grams_p10=applied_p10,
        grams_p50=prior_p50,
        grams_p90=applied_p90,
        percentiles_available=portion_range.percentiles_available,
        confidence=portion_range.confidence,
        source=portion_range.source,
        reason=(
            f"{portion_range.reason}; p50 adjusted via correction prior "
            f"({prior.strategy}, n={prior.sample_count}, prior_p50={prior_p50:g}g)"
        ),
        uncertainty_flags=portion_range.uncertainty_flags,
    )
    return applied_range, AppliedPortionPriorTrace(
        strategy=prior.strategy,
        reference=prior.reference,
        sample_count=prior.sample_count,
        prior_grams_p50=prior_p50,
        original_grams_p50=portion_range.grams_p50,
        applied_grams_p50=prior_p50,
    )


def _build_unmatched_uncertainty_signal(
    *,
    component_name: str,
    component_confidence: float,
    portion_range: PortionGramRange,
    top_candidates: Sequence[ComponentMatchCandidate],
    unmatched_reason: str,
) -> MealUncertaintySignal:
    category = _detect_high_impact_category(
        (
            component_name,
            *[candidate.macro_entry_name for candidate in top_candidates],
        )
    )
    if category is None:
        return MealUncertaintySignal(
            component_name=component_name,
            source="unmatched_component",
            impact="low",
            reason=unmatched_reason,
            estimated_kcal_delta=0.0,
            estimated_fat_g_delta=0.0,
            recommended_question=None,
        )

    estimated_unknown_grams = _estimate_unmatched_unknown_grams(portion_range, component_confidence)
    estimated_kcal_delta = _round_one_decimal(
        (estimated_unknown_grams * category.kcal_per_100g) / 100.0
    )
    estimated_fat_delta = _round_one_decimal(
        (estimated_unknown_grams * category.fat_g_per_100g) / 100.0
    )
    high_impact = (
        estimated_kcal_delta >= HIGH_IMPACT_KCAL_DELTA_THRESHOLD
        or estimated_fat_delta >= HIGH_IMPACT_FAT_DELTA_THRESHOLD
    )
    reason_prefix = (
        f"{unmatched_reason}; potential high-impact category detected: {category.key}"
        if high_impact
        else f"{unmatched_reason}; potential category detected: {category.key}"
    )
    return MealUncertaintySignal(
        component_name=component_name,
        source="unmatched_component",
        impact="high" if high_impact else "low",
        reason=reason_prefix,
        estimated_kcal_delta=estimated_kcal_delta,
        estimated_fat_g_delta=estimated_fat_delta,
        recommended_question=category.unmatched_question_template.format(
            component_name=component_name
        )
        if high_impact
        else None,
    )


def _collect_hidden_risk_uncertainty_signals(
    *,
    component_name: str,
    portion_range: PortionGramRange,
    hidden_ingredient_risks: Sequence[NormalizedHiddenIngredientRisk],
) -> tuple[MealUncertaintySignal, ...]:
    signals: list[MealUncertaintySignal] = []
    for risk in hidden_ingredient_risks:
        category = _detect_high_impact_category((risk.ingredient, component_name))
        if category is None:
            continue

        potential_unknown_grams = _estimate_hidden_risk_unknown_grams(
            portion_range=portion_range,
            likelihood=risk.likelihood,
        )
        estimated_kcal_delta = _round_one_decimal(
            (potential_unknown_grams * category.kcal_per_100g) / 100.0
        )
        estimated_fat_delta = _round_one_decimal(
            (potential_unknown_grams * category.fat_g_per_100g) / 100.0
        )
        materially_high = (
            risk.likelihood >= 0.5
            and (
                risk.macro_impact in {"medium", "high", "unknown"}
                or estimated_kcal_delta >= HIGH_IMPACT_KCAL_DELTA_THRESHOLD
                or estimated_fat_delta >= HIGH_IMPACT_FAT_DELTA_THRESHOLD
            )
        )
        if not materially_high:
            continue

        rationale_suffix = (
            f"; evidence: {'; '.join(risk.rationales)}" if risk.rationales else ""
        )
        signals.append(
            MealUncertaintySignal(
                component_name=component_name,
                source="hidden_ingredient_risk",
                impact="high",
                reason=(
                    "hidden ingredient risk detected: "
                    f"{risk.ingredient} (likelihood={risk.likelihood:.2f}, "
                    f"macro_impact={risk.macro_impact}){rationale_suffix}"
                ),
                estimated_kcal_delta=estimated_kcal_delta,
                estimated_fat_g_delta=estimated_fat_delta,
                recommended_question=(
                    f"For {component_name}, was there hidden {risk.ingredient}? "
                    "About how much was used?"
                ),
            )
        )
    return tuple(signals)


def _detect_high_impact_category(texts: Sequence[str]) -> _HighImpactCategory | None:
    normalized_texts = tuple(_normalize_gate_text(text) for text in texts)
    for category in HIGH_IMPACT_CATEGORIES:
        if any(
            _contains_phrase(normalized_text, category.phrases)
            for normalized_text in normalized_texts
        ):
            return category
    return None


def _contains_phrase(normalized_text: str, phrases: Sequence[str]) -> bool:
    if not normalized_text:
        return False
    padded_text = f" {normalized_text} "
    return any(f" {phrase} " in padded_text for phrase in phrases)


def _normalize_gate_text(text: str) -> str:
    lowered = text.casefold()
    collapsed = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(collapsed.split())


def _estimate_unmatched_unknown_grams(
    portion_range: PortionGramRange,
    component_confidence: float,
) -> float:
    center_grams = portion_range.grams_p50
    confidence_scale = 0.5 + (0.5 * (1.0 - max(0.0, min(1.0, component_confidence))))
    return max(15.0, center_grams * confidence_scale)


def _estimate_hidden_risk_unknown_grams(
    *,
    portion_range: PortionGramRange,
    likelihood: float,
) -> float:
    center_grams = portion_range.grams_p50
    hidden_fraction = 0.08 + (0.22 * max(0.0, min(1.0, likelihood)))
    return max(5.0, center_grams * hidden_fraction)


def _select_recommended_user_question(signals: Sequence[MealUncertaintySignal]) -> str | None:
    high_impact_signals = [
        signal
        for signal in signals
        if signal.impact == "high" and signal.recommended_question is not None
    ]
    if not high_impact_signals:
        return None
    ranked = sorted(high_impact_signals, key=lambda signal: signal.impact_score, reverse=True)
    if len(ranked) == 1:
        return ranked[0].recommended_question
    second_score = ranked[1].impact_score
    if second_score <= 0:
        return ranked[0].recommended_question
    if ranked[0].impact_score >= second_score * DOMINANT_UNCERTAINTY_RATIO:
        return ranked[0].recommended_question
    return None


def _round_one_decimal(value: float) -> float:
    return round(value, 1)


__all__ = [
    "AppliedPortionPriorTrace",
    "ComponentMatchCandidate",
    "DEFAULT_CANDIDATE_LIMIT",
    "DEFAULT_CORRECTION_PRIOR_MINIMUM_SAMPLES",
    "DEFAULT_CONFIDENT_MATCH_SCORE",
    "DEFAULT_MIN_MATCH_SCORE",
    "HIGH_IMPACT_BY_KEY",
    "MealComponentEstimate",
    "MealEstimate",
    "MealUncertaintySignal",
    "PortionCorrectionPrior",
    "PortionPriorResolver",
    "analyze_meal_components",
    "estimate_meal_from_components",
]
