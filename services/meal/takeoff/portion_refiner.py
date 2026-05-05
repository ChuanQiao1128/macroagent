from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, model_validator

from services.meal.takeoff.schemas import PortionRange, QuantityUnit, StrictModel

POLICY_DIR = Path(__file__).resolve().parents[1] / "policies"
DEFAULT_UNCERTAINTY_POLICY_PATH = POLICY_DIR / "uncertainty_policy.yaml"

PresenceState = Literal[
    "visible",
    "visible_unknown",
    "visible_unknown_type",
    "suspected_hidden",
    "not_visible",
]
DistributionShape = Literal["symmetric", "right_skewed", "left_skewed", "unknown"]
VisibleAmount = Literal["light", "medium", "heavy"]


class UnknownComponentRequest(StrictModel):
    component_type: str = Field(..., min_length=1)
    family: str = Field(..., min_length=1)
    presence_state: PresenceState
    visible_amount: VisibleAmount | None = None
    quantity_unit: QuantityUnit = "ml"
    distribution_shape: DistributionShape = "unknown"
    skew_hint: str | None = None


class UnknownComponentBounds(StrictModel):
    component_type: str = Field(..., min_length=1)
    family: str = Field(..., min_length=1)
    presence_state: PresenceState
    quantity_unit: QuantityUnit
    quantity_min: float = Field(ge=0)
    quantity_best: float = Field(ge=0)
    quantity_max: float = Field(ge=0)
    distribution_shape: DistributionShape = "unknown"
    skew_hint: str | None = None
    policy_ref: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_quantity_order(self) -> UnknownComponentBounds:
        if not self.quantity_min <= self.quantity_best <= self.quantity_max:
            raise ValueError("unknown component bounds must satisfy min <= best <= max")
        return self


def load_uncertainty_policy(
    path: Path | str = DEFAULT_UNCERTAINTY_POLICY_PATH,
) -> dict[str, Any]:
    policy = _load_yaml_mapping(path)
    if "range_decision" not in policy:
        raise ValueError("uncertainty policy missing range_decision")
    if "unknown_components" not in policy:
        raise ValueError("uncertainty policy missing unknown_components")
    return policy


def resolve_unknown_component_bounds(
    *,
    component_type: str,
    family: str,
    presence_state: PresenceState,
    visible_amount: VisibleAmount | None = None,
    quantity_unit: QuantityUnit = "ml",
    distribution_shape: DistributionShape = "unknown",
    skew_hint: str | None = None,
    policy_path: Path | str = DEFAULT_UNCERTAINTY_POLICY_PATH,
) -> UnknownComponentBounds:
    """Resolve unknown-component default quantity bounds from policy.

    All default unknown-component quantity bounds are loaded from
    `uncertainty_policy.yaml` so calculators never hardcode this policy data.
    """
    policy = load_uncertainty_policy(policy_path)
    unknown_components = policy["unknown_components"]

    component_policy = unknown_components.get(component_type)
    if not isinstance(component_policy, dict):
        raise KeyError(f"unknown component_type in policy: {component_type!r}")

    families = component_policy.get("families")
    if not isinstance(families, dict):
        raise ValueError(f"unknown component policy for {component_type!r} missing families")

    family_policy = families.get(family)
    if not isinstance(family_policy, dict):
        raise KeyError(f"unknown family for {component_type!r}: {family!r}")

    presence_key = _normalize_presence_state(presence_state)
    quantity_key = _select_quantity_key(
        presence_state=presence_key,
        visible_amount=visible_amount,
        family_policy=family_policy,
    )

    quantity_mapping = family_policy.get("default_quantity_ml")
    if not isinstance(quantity_mapping, dict):
        raise ValueError(
            f"policy for {component_type!r}/{family!r} missing default_quantity_ml mapping"
        )

    selected = quantity_mapping.get(quantity_key)
    if not isinstance(selected, dict):
        raise KeyError(
            "no quantity range in policy for "
            f"{component_type!r}/{family!r}/{presence_key!r}"
        )

    quantity_min = float(selected["min"])
    quantity_best = float(selected["best"])
    quantity_max = float(selected["max"])

    presence_states = component_policy.get("presence_states", {})
    zero_allowed = bool(
        presence_states.get(presence_key, {}).get("lower_can_be_zero", False)
    )
    if not zero_allowed and quantity_min == 0:
        raise ValueError(
            "policy produced a zero lower bound for a visible state that disallows zero"
        )

    inferred_shape = (
        distribution_shape
        if distribution_shape != "unknown"
        else _infer_distribution_shape(quantity_min, quantity_best, quantity_max)
    )
    final_skew_hint = skew_hint
    if final_skew_hint is None and inferred_shape == "right_skewed":
        final_skew_hint = f"policy_upper_tail:{component_type}/{family}/{quantity_key}"

    return UnknownComponentBounds(
        component_type=component_type,
        family=family,
        presence_state=presence_state,
        quantity_unit=quantity_unit,
        quantity_min=quantity_min,
        quantity_best=quantity_best,
        quantity_max=quantity_max,
        distribution_shape=inferred_shape,
        skew_hint=final_skew_hint,
        policy_ref=f"{Path(policy_path).name}#unknown_components.{component_type}.families.{family}.{quantity_key}",
    )


def build_unknown_component_portion_range(
    *,
    component_id: str,
    component_type: str,
    family: str,
    presence_state: PresenceState,
    visible_amount: VisibleAmount | None = None,
    confidence_label: Literal["high", "medium", "low"] = "low",
    confidence_score: float = 0.40,
    policy_path: Path | str = DEFAULT_UNCERTAINTY_POLICY_PATH,
    distribution_shape: DistributionShape = "unknown",
    skew_hint: str | None = None,
) -> PortionRange:
    bounds = resolve_unknown_component_bounds(
        component_type=component_type,
        family=family,
        presence_state=presence_state,
        visible_amount=visible_amount,
        distribution_shape=distribution_shape,
        skew_hint=skew_hint,
        policy_path=policy_path,
    )
    return PortionRange(
        component_id=component_id,
        quantity_unit=bounds.quantity_unit,
        quantity_min=bounds.quantity_min,
        quantity_best=bounds.quantity_best,
        quantity_max=bounds.quantity_max,
        primary_basis="photo_only_heuristic",
        scale_evidence_ids=[],
        confidence_label=confidence_label,
        confidence_score=confidence_score,
        uncertainty_drivers=[f"unknown_{component_type}", bounds.policy_ref],
    )


def _select_quantity_key(
    *,
    presence_state: PresenceState,
    visible_amount: VisibleAmount | None,
    family_policy: dict[str, Any],
) -> str:
    default_quantity = family_policy.get("default_quantity_ml")
    if not isinstance(default_quantity, dict):
        raise ValueError("family policy missing default_quantity_ml")

    if (
        presence_state in {"suspected_hidden", "not_visible"}
        and "suspected_hidden" in default_quantity
    ):
        return "suspected_hidden"

    candidate_keys = []
    if presence_state in {"visible", "visible_unknown", "visible_unknown_type"}:
        if visible_amount is not None:
            candidate_keys.append(f"visible_{visible_amount}")
        candidate_keys.extend(("visible_medium", "visible_light", "visible_heavy"))

    if presence_state in {"suspected_hidden", "not_visible"}:
        candidate_keys.extend(("visible_light", "visible_medium", "visible_heavy"))

    for candidate in candidate_keys:
        if candidate in default_quantity:
            return candidate

    available = ", ".join(sorted(default_quantity))
    raise KeyError(
        "no compatible default_quantity_ml key for "
        f"presence_state={presence_state!r}; available={available}"
    )


def _normalize_presence_state(value: PresenceState) -> PresenceState:
    if value == "visible_unknown_type":
        return "visible_unknown"
    return value


def _infer_distribution_shape(
    quantity_min: float,
    quantity_best: float,
    quantity_max: float,
) -> DistributionShape:
    lower_span = quantity_best - quantity_min
    upper_span = quantity_max - quantity_best
    if lower_span < 0 or upper_span < 0:
        return "unknown"
    if upper_span > lower_span:
        return "right_skewed"
    if lower_span > upper_span:
        return "left_skewed"
    return "symmetric"


def _load_yaml_mapping(path: Path | str) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as file_obj:
        loaded = yaml.safe_load(file_obj)
    if not isinstance(loaded, dict):
        raise ValueError(f"expected YAML mapping in {path}")
    return loaded


refine_unknown_component_portion = resolve_unknown_component_bounds


__all__ = [
    "DEFAULT_UNCERTAINTY_POLICY_PATH",
    "DistributionShape",
    "UnknownComponentBounds",
    "UnknownComponentRequest",
    "build_unknown_component_portion_range",
    "load_uncertainty_policy",
    "refine_unknown_component_portion",
    "resolve_unknown_component_bounds",
]
