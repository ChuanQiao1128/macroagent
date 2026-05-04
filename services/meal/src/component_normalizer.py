from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from services.vision import FoodComponent, VisionAnalysisResponse

ComponentState = Literal["cooked", "raw", "fried", "grilled", "plain", "sauced"]
HiddenRiskImpact = Literal["low", "medium", "high", "unknown"]


class NormalizedFoodCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    visual_evidence: tuple[str, ...] = Field(default_factory=tuple)


class NormalizedStateHint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: ComponentState
    confidence: float = Field(..., ge=0.0, le=1.0)
    visual_evidence: tuple[str, ...] = Field(default_factory=tuple)


class NormalizedHiddenIngredientRisk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ingredient: str = Field(..., min_length=1)
    likelihood: float = Field(..., ge=0.0, le=1.0)
    macro_impact: HiddenRiskImpact
    rationales: tuple[str, ...] = Field(default_factory=tuple)


class NormalizedMealComponent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    component_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    portion_hint: str | None = None
    top_food_candidates: tuple[NormalizedFoodCandidate, ...] = Field(default_factory=tuple)
    state_hints: tuple[NormalizedStateHint, ...] = Field(default_factory=tuple)
    hidden_ingredient_risks: tuple[NormalizedHiddenIngredientRisk, ...] = Field(
        default_factory=tuple
    )
    source_component_ids: tuple[str, ...] = Field(default_factory=tuple)
    source_component_names: tuple[str, ...] = Field(default_factory=tuple)


class NormalizedMealComponents(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    components: tuple[NormalizedMealComponent, ...] = Field(default_factory=tuple)
    meal_uncertainty_flags: tuple[str, ...] = Field(default_factory=tuple)


@dataclass(frozen=True)
class _ExtractedComponent:
    component_id: str
    source_name: str
    name: str
    confidence: float
    portion_hint: str | None
    portion_confidence: float
    top_food_candidates: tuple[NormalizedFoodCandidate, ...]
    state_hints: tuple[NormalizedStateHint, ...]
    hidden_ingredient_risks: tuple[NormalizedHiddenIngredientRisk, ...]


@dataclass
class _CandidateAccumulator:
    confidence: float
    visual_evidence: list[str] = field(default_factory=list)


@dataclass
class _StateHintAccumulator:
    confidence: float
    visual_evidence: list[str] = field(default_factory=list)


@dataclass
class _HiddenRiskAccumulator:
    likelihood: float
    rationales: list[str] = field(default_factory=list)


@dataclass
class _ComponentAccumulator:
    component_id: str
    name: str
    confidence: float
    portion_hint: str | None
    portion_confidence: float
    source_component_ids: list[str] = field(default_factory=list)
    source_component_names: list[str] = field(default_factory=list)
    candidates: dict[str, _CandidateAccumulator] = field(default_factory=dict)
    state_hints: dict[ComponentState, _StateHintAccumulator] = field(default_factory=dict)
    hidden_ingredient_risks: dict[tuple[str, HiddenRiskImpact], _HiddenRiskAccumulator] = field(
        default_factory=dict
    )


def normalize_meal_components(
    components: Sequence[FoodComponent] | VisionAnalysisResponse,
) -> NormalizedMealComponents:
    """Normalize legacy or structured vision output before nutrition matching."""
    if isinstance(components, VisionAnalysisResponse):
        extracted_components = _extract_structured_components(components)
        meal_uncertainty_flags = tuple(
            _dedupe_preserving_order(
                _normalize_name(flag) for flag in components.meal_uncertainty_flags
            )
        )
    else:
        extracted_components = _extract_legacy_components(components)
        meal_uncertainty_flags = tuple()

    merged = _merge_components(extracted_components)
    normalized_components = tuple(_to_normalized_component(component) for component in merged)
    return NormalizedMealComponents(
        components=normalized_components,
        meal_uncertainty_flags=meal_uncertainty_flags,
    )


def _extract_legacy_components(components: Sequence[FoodComponent]) -> list[_ExtractedComponent]:
    extracted: list[_ExtractedComponent] = []
    for index, component in enumerate(components, start=1):
        normalized_name = _normalize_name(component.name)
        if not normalized_name:
            normalized_name = "unknown component"
        portion_hint = _normalize_optional_text(component.portion_hint)
        extracted.append(
            _ExtractedComponent(
                component_id=f"legacy_component_{index}",
                source_name=_normalize_free_text(component.name) or normalized_name,
                name=normalized_name,
                confidence=component.confidence,
                portion_hint=portion_hint,
                portion_confidence=component.confidence,
                top_food_candidates=(
                    NormalizedFoodCandidate(
                        name=normalized_name,
                        confidence=component.confidence,
                        visual_evidence=(),
                    ),
                ),
                state_hints=(),
                hidden_ingredient_risks=(),
            )
        )
    return extracted


def _extract_structured_components(
    response: VisionAnalysisResponse,
) -> list[_ExtractedComponent]:
    extracted: list[_ExtractedComponent] = []
    for index, component in enumerate(response.components, start=1):
        candidate_models: list[NormalizedFoodCandidate] = []
        for candidate in component.candidates:
            normalized_candidate_name = _normalize_name(candidate.name)
            if not normalized_candidate_name:
                continue
            candidate_models.append(
                NormalizedFoodCandidate(
                    name=normalized_candidate_name,
                    confidence=candidate.confidence,
                    visual_evidence=tuple(
                        _dedupe_preserving_order(
                            _normalize_free_text(evidence) for evidence in candidate.visual_evidence
                        )
                    ),
                )
            )

        canonical_name = (
            candidate_models[0].name
            if candidate_models
            else _normalize_name(component.visible_name) or "unknown component"
        )
        source_name = _normalize_free_text(component.visible_name) or canonical_name
        normalized_component_id = _normalize_identifier(component.component_id)
        component_id = normalized_component_id or f"structured_component_{index}"

        state_hints = tuple(
            NormalizedStateHint(
                state=state_hint.state,
                confidence=state_hint.confidence,
                visual_evidence=tuple(
                    _dedupe_preserving_order(
                        _normalize_free_text(evidence) for evidence in state_hint.visual_evidence
                    )
                ),
            )
            for state_hint in component.state_hints
        )
        hidden_risks = tuple(
            NormalizedHiddenIngredientRisk(
                ingredient=_normalize_name(risk.ingredient) or "unknown ingredient",
                likelihood=risk.likelihood,
                macro_impact=risk.macro_impact,
                rationales=tuple(
                    _dedupe_preserving_order(
                        _normalize_free_text(risk.rationale),
                    )
                )
                if risk.rationale
                else (),
            )
            for risk in component.hidden_ingredient_risks
        )
        portion_hint = _normalize_optional_text(component.portion.description)

        extracted.append(
            _ExtractedComponent(
                component_id=component_id,
                source_name=source_name,
                name=canonical_name,
                confidence=candidate_models[0].confidence if candidate_models else 0.0,
                portion_hint=portion_hint,
                portion_confidence=component.portion.confidence,
                top_food_candidates=tuple(candidate_models),
                state_hints=state_hints,
                hidden_ingredient_risks=hidden_risks,
            )
        )
    return extracted


def _merge_components(
    extracted_components: Sequence[_ExtractedComponent],
) -> list[_ComponentAccumulator]:
    merged: dict[str, _ComponentAccumulator] = {}

    for component in extracted_components:
        accumulator = merged.get(component.name)
        if accumulator is None:
            accumulator = _ComponentAccumulator(
                component_id=component.component_id,
                name=component.name,
                confidence=component.confidence,
                portion_hint=component.portion_hint,
                portion_confidence=component.portion_confidence,
                source_component_ids=[],
                source_component_names=[],
            )
            merged[component.name] = accumulator
        else:
            accumulator.confidence = max(accumulator.confidence, component.confidence)
            if component.portion_hint is not None and (
                accumulator.portion_hint is None
                or component.portion_confidence > accumulator.portion_confidence
            ):
                accumulator.portion_hint = component.portion_hint
                accumulator.portion_confidence = component.portion_confidence

        _append_unique(accumulator.source_component_ids, component.component_id)
        _append_unique(accumulator.source_component_names, component.source_name)

        _merge_candidates(accumulator, component.top_food_candidates)
        _merge_state_hints(accumulator, component.state_hints)
        _merge_hidden_ingredient_risks(accumulator, component.hidden_ingredient_risks)

    return list(merged.values())


def _merge_candidates(
    accumulator: _ComponentAccumulator,
    candidates: Sequence[NormalizedFoodCandidate],
) -> None:
    for candidate in candidates:
        existing = accumulator.candidates.get(candidate.name)
        if existing is None:
            accumulator.candidates[candidate.name] = _CandidateAccumulator(
                confidence=candidate.confidence,
                visual_evidence=list(candidate.visual_evidence),
            )
            continue
        existing.confidence = max(existing.confidence, candidate.confidence)
        for evidence in candidate.visual_evidence:
            _append_unique(existing.visual_evidence, evidence)


def _merge_state_hints(
    accumulator: _ComponentAccumulator,
    hints: Sequence[NormalizedStateHint],
) -> None:
    for hint in hints:
        existing = accumulator.state_hints.get(hint.state)
        if existing is None:
            accumulator.state_hints[hint.state] = _StateHintAccumulator(
                confidence=hint.confidence,
                visual_evidence=list(hint.visual_evidence),
            )
            continue
        existing.confidence = max(existing.confidence, hint.confidence)
        for evidence in hint.visual_evidence:
            _append_unique(existing.visual_evidence, evidence)


def _merge_hidden_ingredient_risks(
    accumulator: _ComponentAccumulator,
    risks: Sequence[NormalizedHiddenIngredientRisk],
) -> None:
    for risk in risks:
        key = (risk.ingredient, risk.macro_impact)
        existing = accumulator.hidden_ingredient_risks.get(key)
        if existing is None:
            accumulator.hidden_ingredient_risks[key] = _HiddenRiskAccumulator(
                likelihood=risk.likelihood,
                rationales=list(risk.rationales),
            )
            continue
        existing.likelihood = max(existing.likelihood, risk.likelihood)
        for rationale in risk.rationales:
            _append_unique(existing.rationales, rationale)


def _to_normalized_component(accumulator: _ComponentAccumulator) -> NormalizedMealComponent:
    top_food_candidates = tuple(
        NormalizedFoodCandidate(
            name=name,
            confidence=candidate.confidence,
            visual_evidence=tuple(candidate.visual_evidence),
        )
        for name, candidate in sorted(
            accumulator.candidates.items(),
            key=lambda item: (-item[1].confidence, item[0]),
        )
    )
    state_hints = tuple(
        NormalizedStateHint(
            state=state,
            confidence=hint.confidence,
            visual_evidence=tuple(hint.visual_evidence),
        )
        for state, hint in sorted(
            accumulator.state_hints.items(),
            key=lambda item: (-item[1].confidence, item[0]),
        )
    )
    hidden_ingredient_risks = tuple(
        NormalizedHiddenIngredientRisk(
            ingredient=ingredient,
            likelihood=risk.likelihood,
            macro_impact=macro_impact,
            rationales=tuple(risk.rationales),
        )
        for (ingredient, macro_impact), risk in sorted(
            accumulator.hidden_ingredient_risks.items(),
            key=lambda item: (-item[1].likelihood, item[0][0], item[0][1]),
        )
    )
    return NormalizedMealComponent(
        component_id=accumulator.component_id,
        name=accumulator.name,
        confidence=accumulator.confidence,
        portion_hint=accumulator.portion_hint,
        top_food_candidates=top_food_candidates,
        state_hints=state_hints,
        hidden_ingredient_risks=hidden_ingredient_risks,
        source_component_ids=tuple(accumulator.source_component_ids),
        source_component_names=tuple(accumulator.source_component_names),
    )


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = _normalize_free_text(value)
    return normalized or None


def _normalize_name(value: str | None) -> str:
    return _normalize_free_text(value).lower()


def _normalize_identifier(value: str | None) -> str:
    return _normalize_free_text(value)


def _normalize_free_text(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _dedupe_preserving_order(values: Sequence[str]) -> list[str]:
    results: list[str] = []
    for value in values:
        if not value:
            continue
        _append_unique(results, value)
    return results


def _append_unique(values: list[str], item: str) -> None:
    if item and item not in values:
        values.append(item)


__all__ = [
    "NormalizedFoodCandidate",
    "NormalizedHiddenIngredientRisk",
    "NormalizedMealComponent",
    "NormalizedMealComponents",
    "NormalizedStateHint",
    "normalize_meal_components",
]
