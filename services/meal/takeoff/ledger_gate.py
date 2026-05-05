from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from services.meal.takeoff.macro_quantity import MealMacroEstimate, calculate_relative_range_width
from services.meal.takeoff.portion_refiner import (
    DEFAULT_UNCERTAINTY_POLICY_PATH,
    load_uncertainty_policy,
)
from services.meal.takeoff.schemas import StrictModel

GateDecision = Literal["ACCEPT", "WARN", "CLARIFY", "BLOCK"]


class LedgerGateResult(StrictModel):
    decision: GateDecision
    decision_reason: str = Field(..., min_length=1)
    relative_range_width: float | None = Field(default=None, ge=0)
    should_write_ledger: bool
    confidence_label: Literal["high", "medium", "low"]
    user_accepted_wide_range: bool | None = None
    user_decline_clarify_reason: str | None = None
    policy_refs: list[str] = Field(default_factory=list)


class RangeDecisionThresholds(StrictModel):
    accept_relative_width_max: float = Field(ge=0)
    warn_relative_width_max: float = Field(ge=0)
    clarify_relative_width_min: float = Field(ge=0)


def load_range_decision_thresholds(
    path: Path | str = DEFAULT_UNCERTAINTY_POLICY_PATH,
) -> RangeDecisionThresholds:
    policy = load_uncertainty_policy(path)
    range_decision = policy.get("range_decision")
    if not isinstance(range_decision, dict):
        raise ValueError("uncertainty policy missing range_decision mapping")
    return RangeDecisionThresholds.model_validate(range_decision)


def apply_ledger_gate(
    meal: MealMacroEstimate | dict[str, Any] | None = None,
    *,
    kcal_min: float | None = None,
    kcal_best: float | None = None,
    kcal_max: float | None = None,
    contract_violation: bool = False,
    log_anyway: bool = False,
    user_decline_clarify_reason: str | None = None,
    policy_path: Path | str = DEFAULT_UNCERTAINTY_POLICY_PATH,
) -> LedgerGateResult:
    """Apply deterministic range/clarify gate and ledger write behavior."""
    thresholds = load_range_decision_thresholds(policy_path)

    resolved_kcal_min = (
        kcal_min if kcal_min is not None else _extract_meal_value(meal, "kcal_min")
    )
    resolved_kcal_best = (
        kcal_best if kcal_best is not None else _extract_meal_value(meal, "kcal_best")
    )
    resolved_kcal_max = (
        kcal_max if kcal_max is not None else _extract_meal_value(meal, "kcal_max")
    )

    relative_width = calculate_relative_range_width(
        kcal_min=resolved_kcal_min,
        kcal_best=resolved_kcal_best,
        kcal_max=resolved_kcal_max,
    )

    if contract_violation:
        return LedgerGateResult(
            decision="BLOCK",
            decision_reason="contract_violation",
            relative_range_width=relative_width,
            should_write_ledger=False,
            confidence_label="low",
            policy_refs=[f"{Path(policy_path).name}#range_decision"],
        )

    decision, reason = _range_decision(
        relative_width=relative_width,
        thresholds=thresholds,
    )

    if decision == "CLARIFY":
        if not log_anyway:
            return LedgerGateResult(
                decision=decision,
                decision_reason=reason,
                relative_range_width=relative_width,
                should_write_ledger=False,
                confidence_label="low",
                policy_refs=[f"{Path(policy_path).name}#range_decision"],
            )

        return LedgerGateResult(
            decision=decision,
            decision_reason=f"{reason}:log_anyway",
            relative_range_width=relative_width,
            should_write_ledger=True,
            confidence_label="low",
            user_accepted_wide_range=True,
            user_decline_clarify_reason=user_decline_clarify_reason,
            policy_refs=[f"{Path(policy_path).name}#range_decision"],
        )

    return LedgerGateResult(
        decision=decision,
        decision_reason=reason,
        relative_range_width=relative_width,
        should_write_ledger=True,
        confidence_label="high" if decision == "ACCEPT" else "medium",
        policy_refs=[f"{Path(policy_path).name}#range_decision"],
    )


def _range_decision(
    *,
    relative_width: float | None,
    thresholds: RangeDecisionThresholds,
) -> tuple[GateDecision, str]:
    if relative_width is None:
        return "CLARIFY", "missing_range_width"

    if relative_width > thresholds.warn_relative_width_max:
        return "CLARIFY", "range_width_gt_warn_max"
    if relative_width > thresholds.accept_relative_width_max:
        return "WARN", "range_width_gt_accept_max"
    return "ACCEPT", "range_width_within_accept"


def _extract_meal_value(
    meal: MealMacroEstimate | dict[str, Any] | None,
    field_name: str,
) -> float | None:
    if meal is None:
        return None
    if isinstance(meal, MealMacroEstimate):
        return _coerce_float(getattr(meal, field_name, None))
    return _coerce_float(meal.get(field_name))


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_log_anyway_ledger_payload(
    *,
    user_decline_clarify_reason: str | None = None,
) -> dict[str, object]:
    return {
        "confidence_label": "low",
        "user_accepted_wide_range": True,
        "user_decline_clarify_reason": user_decline_clarify_reason,
    }


evaluate_ledger_gate = apply_ledger_gate
apply_clarify_gate = apply_ledger_gate


__all__ = [
    "GateDecision",
    "LedgerGateResult",
    "RangeDecisionThresholds",
    "apply_clarify_gate",
    "apply_ledger_gate",
    "build_log_anyway_ledger_payload",
    "evaluate_ledger_gate",
    "load_range_decision_thresholds",
]
