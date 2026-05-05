from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, model_validator

from services.meal.takeoff.macro_quantity import ComponentMacroEstimate, MealMacroEstimate
from services.meal.takeoff.schemas import StrictModel

POLICY_DIR = Path(__file__).resolve().parents[1] / "policies"
DEFAULT_ENERGY_DENSITY_POLICY_PATH = POLICY_DIR / "energy_density_policy.yaml"

GateDecision = Literal["ACCEPT", "WARN", "CLARIFY", "BLOCK"]


class DensityBand(StrictModel):
    min: float = Field(ge=0)
    typical: float = Field(ge=0)
    max: float = Field(ge=0)

    @model_validator(mode="after")
    def _validate_band_order(self) -> DensityBand:
        if not self.min <= self.typical <= self.max:
            raise ValueError("density band must satisfy min <= typical <= max")
        return self


class EnergyDensityCheckResult(StrictModel):
    scope: Literal["component", "meal"]
    target_id: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    kcal_best: float | None = Field(default=None, ge=0)
    quantity_best: float | None = Field(default=None, ge=0)
    density_kcal_per_g: float | None = Field(default=None, ge=0)
    decision: GateDecision
    reason: str = Field(..., min_length=1)
    policy_ref: str = Field(..., min_length=1)
    suppressed: bool = False


class EnergyDensityPolicy(StrictModel):
    version: str = Field(..., min_length=1)
    per_component: dict[str, DensityBand]
    per_meal_aggregate: dict[str, DensityBand]
    outlier_decision: dict[str, float] = Field(default_factory=dict)


class EnergyDensityAuditResult(StrictModel):
    component_checks: list[EnergyDensityCheckResult] = Field(default_factory=list)
    meal_check: EnergyDensityCheckResult
    overall_decision: GateDecision


def load_energy_density_policy(
    path: Path | str = DEFAULT_ENERGY_DENSITY_POLICY_PATH,
) -> EnergyDensityPolicy:
    return EnergyDensityPolicy.model_validate(_load_yaml_mapping(path))


def evaluate_component_energy_density(
    component: ComponentMacroEstimate | Mapping[str, Any],
    *,
    policy_path: Path | str = DEFAULT_ENERGY_DENSITY_POLICY_PATH,
) -> EnergyDensityCheckResult:
    payload = _extract_component_payload(component)
    policy = load_energy_density_policy(policy_path)

    category = payload["category"]
    band = policy.per_component.get(category)
    if band is None:
        return EnergyDensityCheckResult(
            scope="component",
            target_id=payload["component_id"],
            category=category,
            kcal_best=payload["kcal_best"],
            quantity_best=payload["quantity_best"],
            density_kcal_per_g=None,
            decision="CLARIFY",
            reason="missing_component_density_band",
            policy_ref=f"{Path(policy_path).name}#per_component.{category}",
        )

    quantity_best = payload["quantity_best"]
    if quantity_best is None:
        return EnergyDensityCheckResult(
            scope="component",
            target_id=payload["component_id"],
            category=category,
            kcal_best=payload["kcal_best"],
            quantity_best=None,
            density_kcal_per_g=None,
            decision="CLARIFY",
            reason="missing_component_quantity",
            policy_ref=f"{Path(policy_path).name}#per_component.{category}",
        )
    if quantity_best <= 0:
        return EnergyDensityCheckResult(
            scope="component",
            target_id=payload["component_id"],
            category=category,
            kcal_best=payload["kcal_best"],
            quantity_best=quantity_best,
            density_kcal_per_g=None,
            decision="BLOCK",
            reason="invalid_component_quantity",
            policy_ref=f"{Path(policy_path).name}#per_component.{category}",
        )

    kcal_best = payload["kcal_best"]
    if kcal_best is None:
        return EnergyDensityCheckResult(
            scope="component",
            target_id=payload["component_id"],
            category=category,
            kcal_best=None,
            quantity_best=quantity_best,
            density_kcal_per_g=None,
            decision="CLARIFY",
            reason="missing_component_kcal_best",
            policy_ref=f"{Path(policy_path).name}#per_component.{category}",
        )

    density = kcal_best / quantity_best
    decision = _decision_for_density(
        density=density,
        band=band,
        outlier_decision=policy.outlier_decision,
    )
    reason = _density_reason(density=density, band=band, decision=decision)
    return EnergyDensityCheckResult(
        scope="component",
        target_id=payload["component_id"],
        category=category,
        kcal_best=kcal_best,
        quantity_best=quantity_best,
        density_kcal_per_g=density,
        decision=decision,
        reason=reason,
        policy_ref=f"{Path(policy_path).name}#per_component.{category}",
    )


def evaluate_meal_energy_density(
    meal: MealMacroEstimate | Mapping[str, Any],
    *,
    component_checks: Sequence[EnergyDensityCheckResult] | None = None,
    policy_path: Path | str = DEFAULT_ENERGY_DENSITY_POLICY_PATH,
) -> EnergyDensityCheckResult:
    payload = _extract_meal_payload(meal)
    policy = load_energy_density_policy(policy_path)

    meal_type = _resolve_meal_density_category(payload)
    band = policy.per_meal_aggregate.get(meal_type)
    if band is None:
        return EnergyDensityCheckResult(
            scope="meal",
            target_id=payload["meal_id"],
            category=meal_type,
            kcal_best=payload["kcal_best"],
            quantity_best=payload["quantity_best"],
            density_kcal_per_g=None,
            decision="CLARIFY",
            reason="missing_meal_density_band",
            policy_ref=f"{Path(policy_path).name}#per_meal_aggregate.{meal_type}",
        )

    meal_quantity_best = payload["quantity_best"]
    if meal_quantity_best is None:
        return EnergyDensityCheckResult(
            scope="meal",
            target_id=payload["meal_id"],
            category=meal_type,
            kcal_best=payload["kcal_best"],
            quantity_best=None,
            density_kcal_per_g=None,
            decision="CLARIFY",
            reason="missing_meal_quantity",
            policy_ref=f"{Path(policy_path).name}#per_meal_aggregate.{meal_type}",
        )
    if meal_quantity_best <= 0:
        return EnergyDensityCheckResult(
            scope="meal",
            target_id=payload["meal_id"],
            category=meal_type,
            kcal_best=payload["kcal_best"],
            quantity_best=meal_quantity_best,
            density_kcal_per_g=None,
            decision="BLOCK",
            reason="invalid_meal_quantity",
            policy_ref=f"{Path(policy_path).name}#per_meal_aggregate.{meal_type}",
        )

    kcal_best = payload["kcal_best"]
    if kcal_best is None:
        return EnergyDensityCheckResult(
            scope="meal",
            target_id=payload["meal_id"],
            category=meal_type,
            kcal_best=None,
            quantity_best=meal_quantity_best,
            density_kcal_per_g=None,
            decision="CLARIFY",
            reason="missing_meal_kcal_best",
            policy_ref=f"{Path(policy_path).name}#per_meal_aggregate.{meal_type}",
        )

    density = kcal_best / meal_quantity_best
    decision = _decision_for_density(
        density=density,
        band=band,
        outlier_decision=policy.outlier_decision,
    )
    suppressed = False

    if decision != "ACCEPT" and _should_suppress_meal_outlier(
        meal_type=meal_type,
        component_checks=component_checks,
    ):
        decision = "ACCEPT"
        suppressed = True
        reason = "aggregate_outlier_suppressed_components_passed"
    else:
        reason = _density_reason(density=density, band=band, decision=decision)

    return EnergyDensityCheckResult(
        scope="meal",
        target_id=payload["meal_id"],
        category=meal_type,
        kcal_best=kcal_best,
        quantity_best=meal_quantity_best,
        density_kcal_per_g=density,
        decision=decision,
        reason=reason,
        policy_ref=f"{Path(policy_path).name}#per_meal_aggregate.{meal_type}",
        suppressed=suppressed,
    )


def run_energy_density_checks(
    *,
    components: Sequence[ComponentMacroEstimate | Mapping[str, Any]],
    meal: MealMacroEstimate | Mapping[str, Any],
    policy_path: Path | str = DEFAULT_ENERGY_DENSITY_POLICY_PATH,
) -> EnergyDensityAuditResult:
    component_results = [
        evaluate_component_energy_density(component, policy_path=policy_path)
        for component in components
    ]
    meal_result = evaluate_meal_energy_density(
        meal,
        component_checks=component_results,
        policy_path=policy_path,
    )
    overall_decision = _max_decision(
        [meal_result.decision, *[result.decision for result in component_results]]
    )
    return EnergyDensityAuditResult(
        component_checks=component_results,
        meal_check=meal_result,
        overall_decision=overall_decision,
    )


def compute_energy_density(
    *,
    kcal_best: float,
    quantity_best: float,
) -> float:
    if quantity_best <= 0:
        raise ValueError("quantity_best must be positive")
    return kcal_best / quantity_best


def _decision_for_density(
    *,
    density: float,
    band: DensityBand,
    outlier_decision: Mapping[str, float],
) -> GateDecision:
    if band.min <= density <= band.max:
        return "ACCEPT"

    ratio = _outlier_ratio(density=density, band=band)
    warn_ratio_max = float(outlier_decision.get("warn_ratio_max", 1.25))
    clarify_ratio_max = float(outlier_decision.get("clarify_ratio_max", 1.75))

    if ratio <= warn_ratio_max:
        return "WARN"
    if ratio <= clarify_ratio_max:
        return "CLARIFY"
    return "BLOCK"


def _density_reason(*, density: float, band: DensityBand, decision: GateDecision) -> str:
    if decision == "ACCEPT":
        return "density_within_expected_band"
    if density < band.min:
        return "density_below_expected_band"
    return "density_above_expected_band"


def _outlier_ratio(*, density: float, band: DensityBand) -> float:
    if band.min <= density <= band.max:
        return 1.0
    if density < band.min:
        if density == 0:
            return float("inf")
        return band.min / density
    return density / band.max


def _should_suppress_meal_outlier(
    *,
    meal_type: str,
    component_checks: Sequence[EnergyDensityCheckResult] | None,
) -> bool:
    if component_checks is None:
        return False
    if not component_checks:
        return False
    if any(result.decision != "ACCEPT" for result in component_checks):
        return False
    return meal_type in {"mixed_bowl", "plated_meal", "recipe_like"}


def _resolve_meal_density_category(payload: Mapping[str, Any]) -> str:
    meal_type = str(payload.get("meal_type", "")).strip().lower()
    alias_map = {
        "plated_meal": "plated_meal",
        "mixed_bowl": "mixed_bowl",
        "fried_meal": "fried_meal",
        "soup": "soup",
        "drink": "drink",
        "recipe_like": "plated_meal",
        "single_visible_item": "plated_meal",
        "packaged_food": "plated_meal",
        "unclear": "plated_meal",
    }
    if meal_type in alias_map:
        return alias_map[meal_type]

    normalized = str(payload.get("meal_id", "")).lower()
    if "soup" in normalized:
        return "soup"
    if "drink" in normalized:
        return "drink"
    if "fried" in normalized:
        return "fried_meal"
    if "bowl" in normalized or "mixed" in normalized:
        return "mixed_bowl"
    return "plated_meal"


def _max_decision(decisions: Sequence[GateDecision]) -> GateDecision:
    severity = {"ACCEPT": 0, "WARN": 1, "CLARIFY": 2, "BLOCK": 3}
    return max(decisions, key=severity.get)


def _extract_component_payload(
    component: ComponentMacroEstimate | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(component, ComponentMacroEstimate):
        return {
            "component_id": component.component_id,
            "category": component.category,
            "kcal_best": component.kcal_best,
            "quantity_best": component.portion_range.quantity_best,
        }

    component_id = str(component.get("component_id") or component.get("name") or "component")
    category = str(
        component.get("category") or component.get("energy_density_category") or "unknown"
    )
    quantity_best = _component_quantity_best(component)
    return {
        "component_id": component_id,
        "category": category,
        "kcal_best": _coerce_float(component.get("kcal_best")),
        "quantity_best": quantity_best,
    }


def _extract_meal_payload(meal: MealMacroEstimate | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(meal, MealMacroEstimate):
        return {
            "meal_id": meal.meal_id,
            "meal_type": "",
            "kcal_best": meal.kcal_best,
            "quantity_best": _sum_component_quantities(meal.components),
        }

    meal_id = str(meal.get("meal_id") or "meal")
    quantity_best = _coerce_float(meal.get("quantity_best"))
    if quantity_best is None:
        quantity_best = _component_quantity_best(meal)
        if quantity_best is None:
            components = meal.get("components")
            if isinstance(components, Sequence):
                quantity_best = _sum_component_quantities(components)
    return {
        "meal_id": meal_id,
        "meal_type": meal.get("meal_type", ""),
        "kcal_best": _coerce_float(meal.get("kcal_best")),
        "quantity_best": quantity_best,
    }


def _component_quantity_best(payload: Mapping[str, Any]) -> float | None:
    direct = _coerce_float(payload.get("quantity_best"))
    if direct is not None:
        return direct

    portion_range = payload.get("portion_range")
    if isinstance(portion_range, Mapping):
        return _coerce_float(portion_range.get("quantity_best"))
    if hasattr(portion_range, "quantity_best"):
        return _coerce_float(portion_range.quantity_best)
    return None


def _sum_component_quantities(
    components: Sequence[object],
) -> float | None:
    total = 0.0
    found = False
    for component in components:
        quantity_best: float | None = None
        if isinstance(component, ComponentMacroEstimate):
            quantity_best = component.portion_range.quantity_best
        elif isinstance(component, Mapping):
            quantity_best = _component_quantity_best(component)
        elif hasattr(component, "portion_range"):
            portion_range = component.portion_range
            try:
                quantity_best = _coerce_float(portion_range.quantity_best)
            except AttributeError:
                quantity_best = None

        if quantity_best is None:
            continue
        total += quantity_best
        found = True
    return total if found else None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_yaml_mapping(path: Path | str) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as file_obj:
        loaded = yaml.safe_load(file_obj)
    if not isinstance(loaded, dict):
        raise ValueError(f"expected YAML mapping in {path}")
    return loaded


check_component_energy_density = evaluate_component_energy_density
check_meal_energy_density = evaluate_meal_energy_density


__all__ = [
    "DEFAULT_ENERGY_DENSITY_POLICY_PATH",
    "DensityBand",
    "EnergyDensityAuditResult",
    "EnergyDensityCheckResult",
    "EnergyDensityPolicy",
    "check_component_energy_density",
    "check_meal_energy_density",
    "compute_energy_density",
    "evaluate_component_energy_density",
    "evaluate_meal_energy_density",
    "load_energy_density_policy",
    "run_energy_density_checks",
]
