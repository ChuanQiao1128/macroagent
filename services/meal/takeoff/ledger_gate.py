from __future__ import annotations

import math
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from services.meal.takeoff.macro_quantity import MealMacroEstimate, calculate_relative_range_width
from services.meal.takeoff.portion_refiner import (
    DEFAULT_UNCERTAINTY_POLICY_PATH,
    load_uncertainty_policy,
)
from services.meal.takeoff.schemas import LOG_ANYWAY_REASON_VALUES, LogAnywayReason, StrictModel
from services.storage.ledger import AppendOnlyLedger, LedgerEntry, LedgerVersionMatrix

GateDecision = Literal["ACCEPT", "WARN", "CLARIFY", "BLOCK"]


class LedgerGateResult(StrictModel):
    decision: GateDecision
    decision_reason: str = Field(..., min_length=1)
    relative_range_width: float | None = Field(default=None, ge=0)
    should_write_ledger: bool
    ledger_entry_id: str | None = None
    confidence_label: Literal["high", "medium", "low"]
    user_accepted_wide_range: bool | None = None
    user_decline_clarify_reason: str | None = None
    policy_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_decline_reason_pairing(self) -> LedgerGateResult:
        if self.user_decline_clarify_reason:
            if self.decision != "CLARIFY":
                raise ValueError("user_decline_clarify_reason is only valid for CLARIFY")
            if self.user_accepted_wide_range is None:
                raise ValueError(
                    "user_decline_clarify_reason requires explicit user acceptance state"
                )
        return self


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
    ledger: AppendOnlyLedger | None = None,
    version_matrix: LedgerVersionMatrix | None = None,
    meal_id: str | None = None,
    user_id: str | None = None,
    trace_id: str | None = None,
    entry_id: str | None = None,
    top_uncertainty_drivers: Sequence[str] | None = None,
    meal_signature_hash: str | None = None,
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

    interval_contract_violation = _has_interval_contract_violation(
        kcal_min=resolved_kcal_min,
        kcal_best=resolved_kcal_best,
        kcal_max=resolved_kcal_max,
    )
    relative_width = calculate_relative_range_width(
        kcal_min=resolved_kcal_min,
        kcal_best=resolved_kcal_best,
        kcal_max=resolved_kcal_max,
    )

    if contract_violation or interval_contract_violation:
        return LedgerGateResult(
            decision="BLOCK",
            decision_reason="contract_violation",
            relative_range_width=relative_width,
            should_write_ledger=False,
            ledger_entry_id=None,
            confidence_label="low",
            policy_refs=[f"{Path(policy_path).name}#range_decision"],
        )

    decision, reason = _range_decision(
        relative_width=relative_width,
        thresholds=thresholds,
    )

    if decision == "CLARIFY":
        if not log_anyway:
            user_accepted_wide_range = False if user_decline_clarify_reason is not None else None
            return LedgerGateResult(
                decision=decision,
                decision_reason=reason,
                relative_range_width=relative_width,
                should_write_ledger=False,
                ledger_entry_id=None,
                confidence_label="low",
                user_accepted_wide_range=user_accepted_wide_range,
                user_decline_clarify_reason=user_decline_clarify_reason,
                policy_refs=[f"{Path(policy_path).name}#range_decision"],
            )

        _validate_log_anyway_reason(user_decline_clarify_reason)
        ledger_entry = None
        if ledger is not None:
            if version_matrix is None:
                raise ValueError("log-anyway ledger write requires version_matrix")
            if meal_id is None:
                raise ValueError("log-anyway ledger write requires meal_id")
            if user_id is None:
                raise ValueError("log-anyway ledger write requires user_id")
            if trace_id is None:
                raise ValueError("log-anyway ledger write requires trace_id")
            ledger_entry = create_log_anyway_ledger_entry(
                ledger=ledger,
                version_matrix=version_matrix,
                meal_id=meal_id,
                user_id=user_id,
                trace_id=trace_id,
                kcal_min=resolved_kcal_min,
                kcal_best=resolved_kcal_best,
                kcal_max=resolved_kcal_max,
                user_decline_clarify_reason=user_decline_clarify_reason,
                entry_id=entry_id,
                top_uncertainty_drivers=top_uncertainty_drivers,
                meal_signature_hash=meal_signature_hash,
            )

        return LedgerGateResult(
            decision=decision,
            decision_reason=f"{reason}:log_anyway",
            relative_range_width=relative_width,
            should_write_ledger=True,
            ledger_entry_id=ledger_entry.entry_id if ledger_entry is not None else None,
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
        ledger_entry_id=None,
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
    user_decline_clarify_reason: LogAnywayReason | None = None,
) -> dict[str, object]:
    """Build log-anyway metadata compatible with current ledger/trace pairing rules."""
    payload: dict[str, object] = {
        "confidence_label": "low",
        "user_accepted_wide_range": True,
    }
    if user_decline_clarify_reason is not None:
        payload["user_decline_clarify_reason"] = user_decline_clarify_reason
    return payload


def create_log_anyway_ledger_entry(
    *,
    ledger: AppendOnlyLedger,
    version_matrix: LedgerVersionMatrix,
    meal_id: str,
    user_id: str,
    trace_id: str,
    kcal_min: float,
    kcal_best: float,
    kcal_max: float,
    user_decline_clarify_reason: LogAnywayReason | None = None,
    entry_id: str | None = None,
    top_uncertainty_drivers: Sequence[str] | None = None,
    meal_signature_hash: str | None = None,
) -> LedgerEntry:
    """Append the low-confidence meal estimate created by the log-anyway path."""
    return ledger.append_meal_estimate(
        entry_id=entry_id or f"log-anyway:{uuid.uuid4()}",
        version_matrix=version_matrix,
        meal_id=meal_id,
        user_id=user_id,
        trace_id=trace_id,
        kcal_min=kcal_min,
        kcal_best=kcal_best,
        kcal_max=kcal_max,
        confidence_label="low",
        top_uncertainty_drivers=list(top_uncertainty_drivers or []),
        user_accepted_wide_range=True,
        user_decline_clarify_reason=user_decline_clarify_reason,
        meal_signature_hash=meal_signature_hash,
    )


def _has_interval_contract_violation(
    *,
    kcal_min: float | None,
    kcal_best: float | None,
    kcal_max: float | None,
) -> bool:
    if kcal_min is None or kcal_best is None or kcal_max is None:
        return True
    if not all(math.isfinite(value) for value in (kcal_min, kcal_best, kcal_max)):
        return True
    if kcal_min < 0 or kcal_best < 0 or kcal_max < 0:
        return True
    return not (kcal_min <= kcal_best <= kcal_max)


def _validate_log_anyway_reason(reason: str | None) -> None:
    if reason is not None and reason not in LOG_ANYWAY_REASON_VALUES:
        allowed = ", ".join(sorted(LOG_ANYWAY_REASON_VALUES))
        raise ValueError(f"invalid log-anyway reason {reason!r}; expected one of: {allowed}")


evaluate_ledger_gate = apply_ledger_gate
apply_clarify_gate = apply_ledger_gate


__all__ = [
    "GateDecision",
    "LedgerGateResult",
    "RangeDecisionThresholds",
    "apply_clarify_gate",
    "apply_ledger_gate",
    "build_log_anyway_ledger_payload",
    "create_log_anyway_ledger_entry",
    "evaluate_ledger_gate",
    "load_range_decision_thresholds",
]
