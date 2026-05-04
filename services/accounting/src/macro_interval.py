from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.nutrition import MacroEntry, PortionGramRange


class PortionGramBounds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    grams_min: float | None = Field(default=None, ge=0)
    grams_max: float | None = Field(default=None, ge=0)
    grams_p10: float | None = Field(default=None, ge=0)
    grams_p50: float | None = Field(default=None, ge=0)
    grams_p90: float | None = Field(default=None, ge=0)
    percentiles_available: bool = False

    @model_validator(mode="before")
    @classmethod
    def _hydrate_bounds_and_percentiles(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        grams_min = payload.get("grams_min")
        grams_max = payload.get("grams_max")
        grams_p10 = payload.get("grams_p10")
        grams_p50 = payload.get("grams_p50")
        grams_p90 = payload.get("grams_p90")

        if grams_p10 is None and grams_min is not None:
            payload["grams_p10"] = grams_min
        if grams_p90 is None and grams_max is not None:
            payload["grams_p90"] = grams_max
        if grams_min is None and grams_p10 is not None:
            payload["grams_min"] = grams_p10
        if grams_max is None and grams_p90 is not None:
            payload["grams_max"] = grams_p90

        grams_p10 = payload.get("grams_p10")
        grams_p90 = payload.get("grams_p90")
        if grams_p50 is None and grams_p10 is not None and grams_p90 is not None:
            payload["grams_p50"] = _round_to_tenth((float(grams_p10) + float(grams_p90)) / 2.0)

        return payload

    @model_validator(mode="after")
    def _validate_bounds(self) -> PortionGramBounds:
        if self.grams_min is None or self.grams_max is None:
            raise ValueError("grams_min and grams_max must be provided")
        if self.grams_p10 is None or self.grams_p50 is None or self.grams_p90 is None:
            raise ValueError("grams_p10, grams_p50, and grams_p90 must be provided")
        if self.grams_min > self.grams_max:
            raise ValueError("grams_min must be less than or equal to grams_max")
        if not self.grams_p10 <= self.grams_p50 <= self.grams_p90:
            raise ValueError("grams_p10 must be less than or equal to grams_p50 and grams_p90")
        if self.grams_min != self.grams_p10 or self.grams_max != self.grams_p90:
            raise ValueError("grams_min/grams_max must align with grams_p10/grams_p90")
        return self


class MacroRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    min: float | None = Field(default=None, ge=0)
    max: float | None = Field(default=None, ge=0)
    p10: float | None = Field(default=None, ge=0)
    p50: float | None = Field(default=None, ge=0)
    p90: float | None = Field(default=None, ge=0)
    percentiles_available: bool = False

    @model_validator(mode="before")
    @classmethod
    def _hydrate_bounds_and_percentiles(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        min_value = payload.get("min")
        max_value = payload.get("max")
        p10 = payload.get("p10")
        p50 = payload.get("p50")
        p90 = payload.get("p90")

        if p10 is None and min_value is not None:
            payload["p10"] = min_value
        if p90 is None and max_value is not None:
            payload["p90"] = max_value
        if min_value is None and p10 is not None:
            payload["min"] = p10
        if max_value is None and p90 is not None:
            payload["max"] = p90

        p10 = payload.get("p10")
        p90 = payload.get("p90")
        if p50 is None and p10 is not None and p90 is not None:
            payload["p50"] = _round_to_tenth((float(p10) + float(p90)) / 2.0)

        return payload

    @model_validator(mode="after")
    def _validate_bounds(self) -> MacroRange:
        if self.min is None or self.max is None:
            raise ValueError("min and max must be provided")
        if self.p10 is None or self.p50 is None or self.p90 is None:
            raise ValueError("p10, p50, and p90 must be provided")
        if self.min > self.max:
            raise ValueError("min must be less than or equal to max")
        if not self.p10 <= self.p50 <= self.p90:
            raise ValueError("p10 must be less than or equal to p50 and p90")
        if self.min != self.p10 or self.max != self.p90:
            raise ValueError("min/max must align with p10/p90")
        return self


class MacroSourceTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    macro_entry_id: str = Field(..., min_length=1)
    macro_entry_name: str = Field(..., min_length=1)
    macro_entry_source: Literal["USDA", "PERSONAL"]
    grams_min: float = Field(..., ge=0)
    grams_max: float = Field(..., ge=0)
    grams_p10: float = Field(..., ge=0)
    grams_p50: float = Field(..., ge=0)
    grams_p90: float = Field(..., ge=0)
    percentiles_available: bool = False

    @model_validator(mode="after")
    def _validate_bounds(self) -> MacroSourceTrace:
        if self.grams_min > self.grams_max:
            raise ValueError("grams_min must be less than or equal to grams_max")
        if not self.grams_p10 <= self.grams_p50 <= self.grams_p90:
            raise ValueError("grams_p10 must be less than or equal to grams_p50 and grams_p90")
        if self.grams_min != self.grams_p10 or self.grams_max != self.grams_p90:
            raise ValueError("grams_min/grams_max must align with grams_p10/grams_p90")
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
    method: Literal["percentile_p50", "geometric_midpoint", "arithmetic_midpoint"]


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
            grams_p10=normalized_range.grams_p10,
            grams_p50=normalized_range.grams_p50,
            grams_p90=normalized_range.grams_p90,
            percentiles_available=normalized_range.percentiles_available,
        ),
        kcal=_build_macro_range(
            entry.kcal_per_100g,
            normalized_range.grams_min,
            normalized_range.grams_max,
            normalized_range.grams_p10,
            normalized_range.grams_p50,
            normalized_range.grams_p90,
            percentiles_available=normalized_range.percentiles_available,
        ),
        protein_g=_build_macro_range(
            entry.protein_g_per_100g,
            normalized_range.grams_min,
            normalized_range.grams_max,
            normalized_range.grams_p10,
            normalized_range.grams_p50,
            normalized_range.grams_p90,
            percentiles_available=normalized_range.percentiles_available,
        ),
        carbs_g=_build_macro_range(
            entry.carbs_g_per_100g,
            normalized_range.grams_min,
            normalized_range.grams_max,
            normalized_range.grams_p10,
            normalized_range.grams_p50,
            normalized_range.grams_p90,
            percentiles_available=normalized_range.percentiles_available,
        ),
        fat_g=_build_macro_range(
            entry.fat_g_per_100g,
            normalized_range.grams_min,
            normalized_range.grams_max,
            normalized_range.grams_p10,
            normalized_range.grams_p50,
            normalized_range.grams_p90,
            percentiles_available=normalized_range.percentiles_available,
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
    percentile_support = bool(items) and all(
        item.kcal.percentiles_available
        and item.protein_g.percentiles_available
        and item.carbs_g.percentiles_available
        and item.fat_g.percentiles_available
        for item in items
    )
    return MealMacroInterval(
        items=items,
        source_traces=tuple(item.source_trace for item in items),
        kcal=MacroRange(
            min=_round_to_tenth(sum(item.kcal.min for item in items)),
            max=_round_to_tenth(sum(item.kcal.max for item in items)),
            p10=_round_to_tenth(sum(item.kcal.p10 for item in items)),
            p50=_round_to_tenth(sum(item.kcal.p50 for item in items)),
            p90=_round_to_tenth(sum(item.kcal.p90 for item in items)),
            percentiles_available=percentile_support,
        ),
        protein_g=MacroRange(
            min=_round_to_tenth(sum(item.protein_g.min for item in items)),
            max=_round_to_tenth(sum(item.protein_g.max for item in items)),
            p10=_round_to_tenth(sum(item.protein_g.p10 for item in items)),
            p50=_round_to_tenth(sum(item.protein_g.p50 for item in items)),
            p90=_round_to_tenth(sum(item.protein_g.p90 for item in items)),
            percentiles_available=percentile_support,
        ),
        carbs_g=MacroRange(
            min=_round_to_tenth(sum(item.carbs_g.min for item in items)),
            max=_round_to_tenth(sum(item.carbs_g.max for item in items)),
            p10=_round_to_tenth(sum(item.carbs_g.p10 for item in items)),
            p50=_round_to_tenth(sum(item.carbs_g.p50 for item in items)),
            p90=_round_to_tenth(sum(item.carbs_g.p90 for item in items)),
            percentiles_available=percentile_support,
        ),
        fat_g=MacroRange(
            min=_round_to_tenth(sum(item.fat_g.min for item in items)),
            max=_round_to_tenth(sum(item.fat_g.max for item in items)),
            p10=_round_to_tenth(sum(item.fat_g.p10 for item in items)),
            p50=_round_to_tenth(sum(item.fat_g.p50 for item in items)),
            p90=_round_to_tenth(sum(item.fat_g.p90 for item in items)),
            percentiles_available=percentile_support,
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
    if macro_range.percentiles_available:
        return MacroBestEstimate(value=_round_to_tenth(macro_range.p50), method="percentile_p50")

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
        grams_p10=gram_range.grams_p10,
        grams_p50=gram_range.grams_p50,
        grams_p90=gram_range.grams_p90,
        percentiles_available=gram_range.percentiles_available,
    )


def _build_macro_range(
    per_100g_value: float,
    grams_min: float,
    grams_max: float,
    grams_p10: float,
    grams_p50: float,
    grams_p90: float,
    *,
    percentiles_available: bool,
) -> MacroRange:
    return MacroRange(
        min=_round_to_tenth(_calculate_macro_value(per_100g_value, grams_min)),
        max=_round_to_tenth(_calculate_macro_value(per_100g_value, grams_max)),
        p10=_round_to_tenth(_calculate_macro_value(per_100g_value, grams_p10)),
        p50=_round_to_tenth(_calculate_macro_value(per_100g_value, grams_p50)),
        p90=_round_to_tenth(_calculate_macro_value(per_100g_value, grams_p90)),
        percentiles_available=percentiles_available,
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
