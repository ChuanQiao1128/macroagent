from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.nutrition import MacroEntry, PortionGramRange


class PortionGramBounds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    grams_min: float = Field(..., ge=0)
    grams_max: float = Field(..., ge=0)

    @model_validator(mode="after")
    def _validate_bounds(self) -> PortionGramBounds:
        if self.grams_min > self.grams_max:
            raise ValueError("grams_min must be less than or equal to grams_max")
        return self


class MacroRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    min: float = Field(..., ge=0)
    max: float = Field(..., ge=0)

    @model_validator(mode="after")
    def _validate_bounds(self) -> MacroRange:
        if self.min > self.max:
            raise ValueError("min must be less than or equal to max")
        return self


class MacroSourceTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    macro_entry_id: str = Field(..., min_length=1)
    macro_entry_name: str = Field(..., min_length=1)
    macro_entry_source: Literal["USDA", "PERSONAL"]
    grams_min: float = Field(..., ge=0)
    grams_max: float = Field(..., ge=0)

    @model_validator(mode="after")
    def _validate_bounds(self) -> MacroSourceTrace:
        if self.grams_min > self.grams_max:
            raise ValueError("grams_min must be less than or equal to grams_max")
        return self


class FoodMacroInterval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_trace: MacroSourceTrace
    kcal: MacroRange
    protein_g: MacroRange
    carbs_g: MacroRange
    fat_g: MacroRange


class MealMacroInterval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[FoodMacroInterval, ...] = Field(default_factory=tuple)
    source_traces: tuple[MacroSourceTrace, ...] = Field(default_factory=tuple)
    kcal: MacroRange
    protein_g: MacroRange
    carbs_g: MacroRange
    fat_g: MacroRange


class MacroBestEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: float = Field(..., ge=0)
    method: Literal["geometric_midpoint", "arithmetic_midpoint"]


class MacroBestEstimateSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kcal: MacroBestEstimate
    protein_g: MacroBestEstimate
    carbs_g: MacroBestEstimate
    fat_g: MacroBestEstimate


def calculate_food_macro_interval(
    entry: MacroEntry,
    gram_range: PortionGramRange | PortionGramBounds,
) -> FoodMacroInterval:
    """Compute deterministic macro ranges for one food entry and gram range."""
    normalized_range = _coerce_gram_bounds(gram_range)

    return FoodMacroInterval(
        source_trace=MacroSourceTrace(
            macro_entry_id=entry.id,
            macro_entry_name=entry.name,
            macro_entry_source=entry.source,
            grams_min=normalized_range.grams_min,
            grams_max=normalized_range.grams_max,
        ),
        kcal=_build_macro_range(
            entry.kcal_per_100g,
            normalized_range.grams_min,
            normalized_range.grams_max,
        ),
        protein_g=_build_macro_range(
            entry.protein_g_per_100g,
            normalized_range.grams_min,
            normalized_range.grams_max,
        ),
        carbs_g=_build_macro_range(
            entry.carbs_g_per_100g,
            normalized_range.grams_min,
            normalized_range.grams_max,
        ),
        fat_g=_build_macro_range(
            entry.fat_g_per_100g,
            normalized_range.grams_min,
            normalized_range.grams_max,
        ),
    )


def calculate_macro_interval(
    entry: MacroEntry,
    gram_range: PortionGramRange | PortionGramBounds,
) -> FoodMacroInterval:
    """Compatibility alias for calculate_food_macro_interval()."""
    return calculate_food_macro_interval(entry=entry, gram_range=gram_range)


def aggregate_meal_macro_interval(
    food_intervals: Sequence[FoodMacroInterval],
) -> MealMacroInterval:
    """Aggregate multiple per-food intervals into meal-level macro ranges."""
    items = tuple(food_intervals)
    return MealMacroInterval(
        items=items,
        source_traces=tuple(item.source_trace for item in items),
        kcal=MacroRange(
            min=_round_to_tenth(sum(item.kcal.min for item in items)),
            max=_round_to_tenth(sum(item.kcal.max for item in items)),
        ),
        protein_g=MacroRange(
            min=_round_to_tenth(sum(item.protein_g.min for item in items)),
            max=_round_to_tenth(sum(item.protein_g.max for item in items)),
        ),
        carbs_g=MacroRange(
            min=_round_to_tenth(sum(item.carbs_g.min for item in items)),
            max=_round_to_tenth(sum(item.carbs_g.max for item in items)),
        ),
        fat_g=MacroRange(
            min=_round_to_tenth(sum(item.fat_g.min for item in items)),
            max=_round_to_tenth(sum(item.fat_g.max for item in items)),
        ),
    )


def calculate_meal_macro_interval(
    items: Sequence[tuple[MacroEntry, PortionGramRange | PortionGramBounds]],
) -> MealMacroInterval:
    """Compute and aggregate macro intervals for a meal."""
    food_intervals = tuple(
        calculate_food_macro_interval(entry=entry, gram_range=_coerce_gram_bounds(gram_range))
        for entry, gram_range in items
    )
    return aggregate_meal_macro_interval(food_intervals)


def calculate_macro_best_estimate(macro_range: MacroRange) -> MacroBestEstimate:
    """Convert one macro range into a deterministic best estimate."""
    min_value = Decimal(str(macro_range.min))
    max_value = Decimal(str(macro_range.max))
    if min_value > 0 and max_value > 0:
        midpoint = (min_value * max_value).sqrt()
        method: Literal["geometric_midpoint", "arithmetic_midpoint"] = "geometric_midpoint"
    else:
        midpoint = (min_value + max_value) / Decimal("2")
        method = "arithmetic_midpoint"

    return MacroBestEstimate(
        value=_round_to_tenth(midpoint),
        method=method,
    )


def calculate_food_macro_best_estimate(
    food_interval: FoodMacroInterval,
) -> MacroBestEstimateSet:
    """Convert a per-food macro interval into per-macro best estimates."""
    return MacroBestEstimateSet(
        kcal=calculate_macro_best_estimate(food_interval.kcal),
        protein_g=calculate_macro_best_estimate(food_interval.protein_g),
        carbs_g=calculate_macro_best_estimate(food_interval.carbs_g),
        fat_g=calculate_macro_best_estimate(food_interval.fat_g),
    )


def calculate_meal_macro_best_estimate(
    meal_interval: MealMacroInterval,
) -> MacroBestEstimateSet:
    """Convert a meal macro interval into per-macro best estimates."""
    return MacroBestEstimateSet(
        kcal=calculate_macro_best_estimate(meal_interval.kcal),
        protein_g=calculate_macro_best_estimate(meal_interval.protein_g),
        carbs_g=calculate_macro_best_estimate(meal_interval.carbs_g),
        fat_g=calculate_macro_best_estimate(meal_interval.fat_g),
    )


def _coerce_gram_bounds(
    gram_range: PortionGramRange | PortionGramBounds,
) -> PortionGramBounds:
    if isinstance(gram_range, PortionGramBounds):
        return gram_range
    return PortionGramBounds(
        grams_min=gram_range.grams_min,
        grams_max=gram_range.grams_max,
    )


def _build_macro_range(
    per_100g_value: float,
    grams_min: float,
    grams_max: float,
) -> MacroRange:
    return MacroRange(
        min=_round_to_tenth(_calculate_macro_value(per_100g_value, grams_min)),
        max=_round_to_tenth(_calculate_macro_value(per_100g_value, grams_max)),
    )


def _calculate_macro_value(per_100g_value: float, grams: float) -> Decimal:
    return (Decimal(str(per_100g_value)) * Decimal(str(grams))) / Decimal("100")


def _round_to_tenth(value: float | Decimal) -> float:
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    return float(decimal_value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


__all__ = [
    "FoodMacroInterval",
    "MacroBestEstimate",
    "MacroBestEstimateSet",
    "MacroRange",
    "MacroSourceTrace",
    "MealMacroInterval",
    "PortionGramBounds",
    "aggregate_meal_macro_interval",
    "calculate_food_macro_best_estimate",
    "calculate_food_macro_interval",
    "calculate_macro_best_estimate",
    "calculate_meal_macro_interval",
    "calculate_meal_macro_best_estimate",
    "calculate_macro_interval",
]
