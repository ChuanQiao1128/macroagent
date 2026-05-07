from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.nutrition.src.portion_parser import PortionGramRange

VolumeEstimateMethod = Literal["arkit_depth_region", "manual_container", "recipe_template"]
DensityClass = Literal[
    "cooked_grain",
    "cooked_pasta",
    "leafy_salad",
    "beverage_or_soup",
    "protein_solid",
    "oil_or_fat",
    "bread_or_cake",
    "generic_mixed_food",
]


class VolumeEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    volume_ml_p10: float = Field(..., gt=0)
    volume_ml_p50: float = Field(..., gt=0)
    volume_ml_p90: float = Field(..., gt=0)
    confidence: float = Field(..., ge=0, le=1)
    method: VolumeEstimateMethod
    evidence_ids: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_volume_percentiles(self) -> VolumeEstimate:
        if not self.volume_ml_p10 <= self.volume_ml_p50 <= self.volume_ml_p90:
            raise ValueError("volume percentiles must satisfy p10 <= p50 <= p90")
        return self


class DensityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    density_class: DensityClass
    density_g_per_ml_p10: float = Field(..., gt=0)
    density_g_per_ml_p50: float = Field(..., gt=0)
    density_g_per_ml_p90: float = Field(..., gt=0)
    confidence_cap: float = Field(..., ge=0, le=1)
    reason: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_density_percentiles(self) -> DensityProfile:
        if not (
            self.density_g_per_ml_p10
            <= self.density_g_per_ml_p50
            <= self.density_g_per_ml_p90
        ):
            raise ValueError("density percentiles must satisfy p10 <= p50 <= p90")
        return self


_DENSITY_PROFILES: dict[DensityClass, DensityProfile] = {
    "cooked_grain": DensityProfile(
        density_class="cooked_grain",
        density_g_per_ml_p10=0.65,
        density_g_per_ml_p50=0.75,
        density_g_per_ml_p90=0.90,
        confidence_cap=0.82,
        reason="cooked grain density profile",
    ),
    "cooked_pasta": DensityProfile(
        density_class="cooked_pasta",
        density_g_per_ml_p10=0.45,
        density_g_per_ml_p50=0.60,
        density_g_per_ml_p90=0.75,
        confidence_cap=0.76,
        reason="cooked pasta/noodle density profile",
    ),
    "leafy_salad": DensityProfile(
        density_class="leafy_salad",
        density_g_per_ml_p10=0.05,
        density_g_per_ml_p50=0.12,
        density_g_per_ml_p90=0.25,
        confidence_cap=0.55,
        reason="leafy salad density profile",
    ),
    "beverage_or_soup": DensityProfile(
        density_class="beverage_or_soup",
        density_g_per_ml_p10=0.95,
        density_g_per_ml_p50=1.00,
        density_g_per_ml_p90=1.05,
        confidence_cap=0.88,
        reason="water-like beverage/soup density profile",
    ),
    "protein_solid": DensityProfile(
        density_class="protein_solid",
        density_g_per_ml_p10=0.80,
        density_g_per_ml_p50=0.95,
        density_g_per_ml_p90=1.10,
        confidence_cap=0.76,
        reason="solid protein density profile",
    ),
    "oil_or_fat": DensityProfile(
        density_class="oil_or_fat",
        density_g_per_ml_p10=0.88,
        density_g_per_ml_p50=0.92,
        density_g_per_ml_p90=0.96,
        confidence_cap=0.84,
        reason="oil/fat density profile",
    ),
    "bread_or_cake": DensityProfile(
        density_class="bread_or_cake",
        density_g_per_ml_p10=0.20,
        density_g_per_ml_p50=0.32,
        density_g_per_ml_p90=0.50,
        confidence_cap=0.62,
        reason="bread/cake density profile",
    ),
    "generic_mixed_food": DensityProfile(
        density_class="generic_mixed_food",
        density_g_per_ml_p10=0.30,
        density_g_per_ml_p50=0.65,
        density_g_per_ml_p90=1.05,
        confidence_cap=0.45,
        reason="generic mixed-food density fallback",
    ),
}

_DENSITY_KEYWORDS: tuple[tuple[DensityClass, tuple[str, ...]], ...] = (
    ("cooked_grain", ("rice", "grain", "quinoa", "barley", "couscous", "oatmeal")),
    ("cooked_pasta", ("pasta", "noodle", "spaghetti", "macaroni", "ramen", "udon")),
    ("leafy_salad", ("salad", "lettuce", "spinach", "arugula", "greens")),
    (
        "beverage_or_soup",
        ("coffee", "tea", "water", "drink", "juice", "milk", "soup", "broth", "stew"),
    ),
    (
        "protein_solid",
        (
            "chicken",
            "beef",
            "pork",
            "fish",
            "salmon",
            "tuna",
            "shrimp",
            "tofu",
            "egg",
        ),
    ),
    ("oil_or_fat", ("oil", "butter", "ghee", "cream", "dressing", "mayo", "mayonnaise")),
    ("bread_or_cake", ("bread", "cake", "muffin", "bagel", "toast", "croissant")),
)


def resolve_density_profile(
    component_name: str,
    *,
    category_hint: str | None = None,
) -> DensityProfile:
    """Resolve a deterministic density profile for volume-to-grams conversion."""
    text = " ".join(part for part in (component_name, category_hint or "") if part).casefold()
    tokens = set(text.replace("/", " ").replace("-", " ").split())
    for density_class, keywords in _DENSITY_KEYWORDS:
        if any(keyword in text or keyword in tokens for keyword in keywords):
            return _DENSITY_PROFILES[density_class]
    return _DENSITY_PROFILES["generic_mixed_food"]


def estimate_portion_from_volume(
    *,
    component_name: str,
    volume_estimate: VolumeEstimate,
    category_hint: str | None = None,
) -> PortionGramRange:
    """Convert a derived volume estimate into a deterministic gram interval."""
    density = resolve_density_profile(component_name, category_hint=category_hint)
    grams_p10 = _round_to_tenth(
        Decimal(str(volume_estimate.volume_ml_p10))
        * Decimal(str(density.density_g_per_ml_p10))
    )
    grams_p50 = _round_to_tenth(
        Decimal(str(volume_estimate.volume_ml_p50))
        * Decimal(str(density.density_g_per_ml_p50))
    )
    grams_p90 = _round_to_tenth(
        Decimal(str(volume_estimate.volume_ml_p90))
        * Decimal(str(density.density_g_per_ml_p90))
    )

    uncertainty_flags = ["volume_geometry_estimate", "volume_density_estimate"]
    if density.density_class == "generic_mixed_food":
        uncertainty_flags.append("generic_density_profile")

    return PortionGramRange(
        grams_min=grams_p10,
        grams_max=grams_p90,
        grams_p10=grams_p10,
        grams_p50=grams_p50,
        grams_p90=grams_p90,
        percentiles_available=True,
        confidence=min(volume_estimate.confidence, density.confidence_cap),
        source="volume_estimate_density_table",
        reason=(
            f"converted {volume_estimate.method} volume estimate to grams for "
            f"component '{component_name}' using {density.reason}"
        ),
        uncertainty_flags=tuple(uncertainty_flags),
    )


def parse_volume_portion_range(
    *,
    component_name: str,
    volume_estimate: VolumeEstimate,
    category_hint: str | None = None,
) -> PortionGramRange:
    """Compatibility alias for estimate_portion_from_volume()."""
    return estimate_portion_from_volume(
        component_name=component_name,
        volume_estimate=volume_estimate,
        category_hint=category_hint,
    )


def _round_to_tenth(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


__all__ = [
    "DensityClass",
    "DensityProfile",
    "VolumeEstimate",
    "VolumeEstimateMethod",
    "estimate_portion_from_volume",
    "parse_volume_portion_range",
    "resolve_density_profile",
]
