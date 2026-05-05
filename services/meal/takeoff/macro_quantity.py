from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, ConfigDict, Field, model_validator

from services.meal.takeoff.portion_refiner import (
    DEFAULT_UNCERTAINTY_POLICY_PATH,
    UnknownComponentRequest,
    resolve_unknown_component_bounds,
)
from services.meal.takeoff.schemas import PortionRange, StrictModel

DistributionShape = Literal["symmetric", "right_skewed", "left_skewed", "unknown"]


class MacroSource(StrictModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source_ref: str | None = None
    kcal_per_100g: float = Field(
        ge=0,
        validation_alias=AliasChoices("kcal_per_100g", "kcal_per_100ml"),
    )
    protein_g_per_100g: float | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("protein_g_per_100g", "protein_per_100g"),
    )
    carbs_g_per_100g: float | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("carbs_g_per_100g", "carbs_per_100g"),
    )
    fat_g_per_100g: float | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("fat_g_per_100g", "fat_per_100g"),
    )


class QuantityRange(StrictModel):
    quantity_min: float = Field(ge=0)
    quantity_best: float = Field(ge=0)
    quantity_max: float = Field(ge=0)
    quantity_unit: Literal["g", "ml", "piece", "serving"] = "g"
    distribution_shape: DistributionShape = "unknown"
    skew_hint: str | None = None

    @model_validator(mode="after")
    def _validate_quantity_order(self) -> QuantityRange:
        if not self.quantity_min <= self.quantity_best <= self.quantity_max:
            raise ValueError("quantity range must satisfy min <= best <= max")
        return self


class ComponentMacroEstimate(StrictModel):
    component_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    source_ref: str | None = None
    portion_range: QuantityRange
    kcal_min: float = Field(ge=0)
    kcal_best: float = Field(ge=0)
    kcal_max: float = Field(ge=0)
    protein_min: float | None = Field(default=None, ge=0)
    protein_best: float | None = Field(default=None, ge=0)
    protein_max: float | None = Field(default=None, ge=0)
    carbs_min: float | None = Field(default=None, ge=0)
    carbs_best: float | None = Field(default=None, ge=0)
    carbs_max: float | None = Field(default=None, ge=0)
    fat_min: float | None = Field(default=None, ge=0)
    fat_best: float | None = Field(default=None, ge=0)
    fat_max: float | None = Field(default=None, ge=0)
    distribution_shape: DistributionShape = "unknown"
    skew_hint: str | None = None
    policy_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class MealMacroEstimate(StrictModel):
    meal_id: str = Field(..., min_length=1)
    kcal_min: float = Field(ge=0)
    kcal_best: float = Field(ge=0)
    kcal_max: float = Field(ge=0)
    protein_min: float | None = Field(default=None, ge=0)
    protein_best: float | None = Field(default=None, ge=0)
    protein_max: float | None = Field(default=None, ge=0)
    carbs_min: float | None = Field(default=None, ge=0)
    carbs_best: float | None = Field(default=None, ge=0)
    carbs_max: float | None = Field(default=None, ge=0)
    fat_min: float | None = Field(default=None, ge=0)
    fat_best: float | None = Field(default=None, ge=0)
    fat_max: float | None = Field(default=None, ge=0)
    confidence_label: Literal["high", "medium", "low"] = "medium"
    relative_range_width: float | None = Field(default=None, ge=0)
    components: list[ComponentMacroEstimate] = Field(default_factory=list)
    top_uncertainty_drivers: list[str] = Field(default_factory=list)
    decision: Literal["ACCEPT", "WARN", "CLARIFY", "BLOCK"] = "ACCEPT"
    decision_reason: str = "component_mode_sum"


class UnknownComponentInput(StrictModel):
    component_type: str = Field(..., min_length=1)
    family: str = Field(..., min_length=1)
    presence_state: str = Field(..., min_length=1)
    visible_amount: Literal["light", "medium", "heavy"] | None = None
    quantity_unit: Literal["g", "ml", "piece", "serving"] = "ml"


class ComponentCalculationInput(StrictModel):
    component_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    source_ref: str | None = None
    source: MacroSource
    portion_range: QuantityRange | None = None
    unknown_component: UnknownComponentInput | None = None
    distribution_shape: DistributionShape = "unknown"
    skew_hint: str | None = None
    policy_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


def compute_component_macros(
    source: MacroSource | Mapping[str, Any],
    portion_range: QuantityRange | PortionRange | Mapping[str, Any] | None,
    *,
    component_id: str = "component",
    name: str = "component",
    category: str = "unknown",
    source_ref: str | None = None,
    distribution_shape: DistributionShape | None = None,
    skew_hint: str | None = None,
    policy_refs: Sequence[str] | None = None,
    evidence_refs: Sequence[str] | None = None,
    unknown_component: UnknownComponentInput | Mapping[str, Any] | None = None,
    uncertainty_policy_path: Path | str = DEFAULT_UNCERTAINTY_POLICY_PATH,
) -> ComponentMacroEstimate:
    """Compute deterministic min/best/max macro interval for one component."""
    source_model = _coerce_source(source)
    quantity_model, resolved_policy_refs = _resolve_quantity_range(
        portion_range=portion_range,
        unknown_component=unknown_component,
        policy_path=uncertainty_policy_path,
    )
    _validate_supported_quantity_unit(quantity_model.quantity_unit)

    multiplier_min = quantity_model.quantity_min / 100.0
    multiplier_best = quantity_model.quantity_best / 100.0
    multiplier_max = quantity_model.quantity_max / 100.0

    if distribution_shape in (None, "unknown"):
        distribution_shape = quantity_model.distribution_shape
    final_skew_hint = skew_hint if skew_hint is not None else quantity_model.skew_hint

    merged_policy_refs = [*(policy_refs or []), *resolved_policy_refs]
    final_source_ref = source_ref if source_ref is not None else source_model.source_ref

    return ComponentMacroEstimate(
        component_id=component_id,
        name=name,
        category=category,
        source_ref=final_source_ref,
        portion_range=quantity_model,
        kcal_min=source_model.kcal_per_100g * multiplier_min,
        kcal_best=source_model.kcal_per_100g * multiplier_best,
        kcal_max=source_model.kcal_per_100g * multiplier_max,
        protein_min=_scaled_optional(source_model.protein_g_per_100g, multiplier_min),
        protein_best=_scaled_optional(source_model.protein_g_per_100g, multiplier_best),
        protein_max=_scaled_optional(source_model.protein_g_per_100g, multiplier_max),
        carbs_min=_scaled_optional(source_model.carbs_g_per_100g, multiplier_min),
        carbs_best=_scaled_optional(source_model.carbs_g_per_100g, multiplier_best),
        carbs_max=_scaled_optional(source_model.carbs_g_per_100g, multiplier_max),
        fat_min=_scaled_optional(source_model.fat_g_per_100g, multiplier_min),
        fat_best=_scaled_optional(source_model.fat_g_per_100g, multiplier_best),
        fat_max=_scaled_optional(source_model.fat_g_per_100g, multiplier_max),
        distribution_shape=distribution_shape,
        skew_hint=final_skew_hint,
        policy_refs=_dedupe(merged_policy_refs),
        evidence_refs=_dedupe(evidence_refs or []),
    )


def calculate_component_estimate(
    component: ComponentCalculationInput | Mapping[str, Any],
    *,
    uncertainty_policy_path: Path | str = DEFAULT_UNCERTAINTY_POLICY_PATH,
) -> ComponentMacroEstimate:
    component_model = _coerce_component_input(component)
    return compute_component_macros(
        source=component_model.source,
        portion_range=component_model.portion_range,
        component_id=component_model.component_id,
        name=component_model.name,
        category=component_model.category,
        source_ref=component_model.source_ref,
        distribution_shape=component_model.distribution_shape,
        skew_hint=component_model.skew_hint,
        policy_refs=component_model.policy_refs,
        evidence_refs=component_model.evidence_refs,
        unknown_component=component_model.unknown_component,
        uncertainty_policy_path=uncertainty_policy_path,
    )


def aggregate_meal_macros(
    components: Sequence[ComponentMacroEstimate | Mapping[str, Any]],
    *,
    meal_id: str = "meal",
    confidence_label: Literal["high", "medium", "low"] = "medium",
    top_uncertainty_drivers: Sequence[str] | None = None,
    decision: Literal["ACCEPT", "WARN", "CLARIFY", "BLOCK"] = "ACCEPT",
    decision_reason: str = "component_mode_sum",
) -> MealMacroEstimate:
    """Aggregate component macro intervals by direct summation.

    This `component_mode_sum` aggregation is a v0.3 approximation: it sums each
    component's min/best/max directly and is not guaranteed to equal the true
    statistical mode of the total meal distribution.
    """
    component_models = [_coerce_component_estimate(component) for component in components]
    kcal_min = sum(component.kcal_min for component in component_models)
    kcal_best = sum(component.kcal_best for component in component_models)
    kcal_max = sum(component.kcal_max for component in component_models)

    if top_uncertainty_drivers is None:
        top_uncertainty_drivers = _default_uncertainty_drivers(component_models)

    return MealMacroEstimate(
        meal_id=meal_id,
        kcal_min=kcal_min,
        kcal_best=kcal_best,
        kcal_max=kcal_max,
        protein_min=_sum_optional_field(component_models, "protein_min"),
        protein_best=_sum_optional_field(component_models, "protein_best"),
        protein_max=_sum_optional_field(component_models, "protein_max"),
        carbs_min=_sum_optional_field(component_models, "carbs_min"),
        carbs_best=_sum_optional_field(component_models, "carbs_best"),
        carbs_max=_sum_optional_field(component_models, "carbs_max"),
        fat_min=_sum_optional_field(component_models, "fat_min"),
        fat_best=_sum_optional_field(component_models, "fat_best"),
        fat_max=_sum_optional_field(component_models, "fat_max"),
        confidence_label=confidence_label,
        relative_range_width=calculate_relative_range_width(
            kcal_min=kcal_min,
            kcal_best=kcal_best,
            kcal_max=kcal_max,
        ),
        components=component_models,
        top_uncertainty_drivers=list(top_uncertainty_drivers),
        decision=decision,
        decision_reason=decision_reason,
    )


def calculate_relative_range_width(
    *,
    kcal_min: float | None,
    kcal_best: float | None,
    kcal_max: float | None,
) -> float | None:
    if kcal_min is None or kcal_best is None or kcal_max is None:
        return None
    if not _is_valid_kcal_interval(kcal_min=kcal_min, kcal_best=kcal_best, kcal_max=kcal_max):
        return None
    if kcal_best == 0:
        if kcal_min == 0 and kcal_max == 0:
            return 0.0
        return None
    return (kcal_max - kcal_min) / kcal_best


def _is_valid_kcal_interval(
    *,
    kcal_min: float,
    kcal_best: float,
    kcal_max: float,
) -> bool:
    if not all(math.isfinite(value) for value in (kcal_min, kcal_best, kcal_max)):
        return False
    if kcal_min < 0 or kcal_best < 0 or kcal_max < 0:
        return False
    return kcal_min <= kcal_best <= kcal_max


def calculate_meal_macros(
    components: Sequence[ComponentMacroEstimate | Mapping[str, Any]],
    *,
    meal_id: str = "meal",
    confidence_label: Literal["high", "medium", "low"] = "medium",
) -> MealMacroEstimate:
    return aggregate_meal_macros(
        components,
        meal_id=meal_id,
        confidence_label=confidence_label,
    )


def _coerce_component_input(
    component: ComponentCalculationInput | Mapping[str, Any],
) -> ComponentCalculationInput:
    if isinstance(component, ComponentCalculationInput):
        return component
    return ComponentCalculationInput.model_validate(component)


def _coerce_component_estimate(
    component: ComponentMacroEstimate | Mapping[str, Any],
) -> ComponentMacroEstimate:
    if isinstance(component, ComponentMacroEstimate):
        return component
    return ComponentMacroEstimate.model_validate(component)


def _coerce_source(source: MacroSource | Mapping[str, Any]) -> MacroSource:
    if isinstance(source, MacroSource):
        return source
    return MacroSource.model_validate(source)


def _resolve_quantity_range(
    *,
    portion_range: QuantityRange | PortionRange | Mapping[str, Any] | None,
    unknown_component: UnknownComponentInput | Mapping[str, Any] | None,
    policy_path: Path | str,
) -> tuple[QuantityRange, list[str]]:
    if portion_range is not None:
        return _coerce_quantity_range(portion_range), []

    if unknown_component is None:
        raise ValueError("either portion_range or unknown_component is required")

    unknown_component_model = _coerce_unknown_component(unknown_component)
    bounds = resolve_unknown_component_bounds(
        component_type=unknown_component_model.component_type,
        family=unknown_component_model.family,
        presence_state=unknown_component_model.presence_state,
        visible_amount=unknown_component_model.visible_amount,
        quantity_unit=unknown_component_model.quantity_unit,
        policy_path=policy_path,
    )
    return (
        QuantityRange(
            quantity_min=bounds.quantity_min,
            quantity_best=bounds.quantity_best,
            quantity_max=bounds.quantity_max,
            quantity_unit=bounds.quantity_unit,
            distribution_shape=bounds.distribution_shape,
            skew_hint=bounds.skew_hint,
        ),
        [bounds.policy_ref],
    )


def _coerce_unknown_component(
    unknown_component: UnknownComponentInput | Mapping[str, Any],
) -> UnknownComponentInput:
    if isinstance(unknown_component, UnknownComponentInput):
        return unknown_component
    if isinstance(unknown_component, UnknownComponentRequest):
        return UnknownComponentInput(
            component_type=unknown_component.component_type,
            family=unknown_component.family,
            presence_state=unknown_component.presence_state,
            visible_amount=unknown_component.visible_amount,
            quantity_unit=unknown_component.quantity_unit,
        )
    return UnknownComponentInput.model_validate(unknown_component)


def _coerce_quantity_range(
    portion_range: QuantityRange | PortionRange | Mapping[str, Any],
) -> QuantityRange:
    if isinstance(portion_range, QuantityRange):
        return portion_range
    if isinstance(portion_range, PortionRange):
        return QuantityRange(
            quantity_min=portion_range.quantity_min,
            quantity_best=portion_range.quantity_best,
            quantity_max=portion_range.quantity_max,
            quantity_unit=portion_range.quantity_unit,
        )

    payload = dict(portion_range)
    if "quantity_unit" not in payload:
        payload["quantity_unit"] = "g"
    return QuantityRange.model_validate(payload)


def _scaled_optional(value_per_100: float | None, multiplier: float) -> float | None:
    if value_per_100 is None:
        return None
    return value_per_100 * multiplier


def _sum_optional_field(
    components: Sequence[ComponentMacroEstimate],
    field_name: str,
) -> float | None:
    values = [getattr(component, field_name) for component in components]
    present_values = [value for value in values if value is not None]
    if not present_values:
        return None
    return sum(present_values)


def _default_uncertainty_drivers(
    components: Sequence[ComponentMacroEstimate],
) -> list[str]:
    drivers: list[str] = []
    for component in components:
        if component.distribution_shape == "right_skewed" and component.skew_hint:
            drivers.append(component.skew_hint)
    return drivers


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _validate_supported_quantity_unit(quantity_unit: str) -> None:
    if quantity_unit not in {"g", "ml"}:
        raise ValueError(
            "quantity_unit requires explicit gram-equivalent conversion before macro calculation"
        )


compute_component_interval = compute_component_macros
calculate_component_macros = compute_component_macros
aggregate_component_intervals = aggregate_meal_macros
relative_range_width = calculate_relative_range_width


__all__ = [
    "ComponentCalculationInput",
    "ComponentMacroEstimate",
    "DistributionShape",
    "MacroSource",
    "MealMacroEstimate",
    "QuantityRange",
    "UnknownComponentInput",
    "aggregate_component_intervals",
    "aggregate_meal_macros",
    "calculate_component_estimate",
    "calculate_component_macros",
    "calculate_meal_macros",
    "calculate_relative_range_width",
    "compute_component_interval",
    "compute_component_macros",
    "relative_range_width",
]
