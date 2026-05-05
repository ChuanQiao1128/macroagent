from __future__ import annotations

from typing import Literal

import pytest
from pydantic import ValidationError

from services.meal.takeoff.ledger_gate import (
    apply_ledger_gate,
    build_log_anyway_ledger_payload,
    load_range_decision_thresholds,
)
from services.meal.takeoff.schemas import TraceEvent
from services.storage.ledger import AppendOnlyLedger, LedgerEntry, LedgerVersionMatrix


def _version_matrix() -> LedgerVersionMatrix:
    return LedgerVersionMatrix(
        calculator_version="calc-v1",
        uncertainty_policy_version="uncertainty-v1",
        energy_density_policy_version="energy-v1",
        scale_evidence_policy_version="scale-v1",
        contract_yaml_version="contract-v1",
        source_dataset_versions={"usda": "2026.05"},
        takeoff_pipeline_version="takeoff-v1",
    )


@pytest.mark.parametrize(
    ("kcal_min", "kcal_best", "kcal_max", "expected_decision"),
    [
        (80.0, 100.0, 115.0, "ACCEPT"),
        (70.0, 100.0, 130.0, "WARN"),
        (69.9, 100.0, 130.1, "CLARIFY"),
    ],
)
def test_relative_range_width_threshold_policy(
    kcal_min: float,
    kcal_best: float,
    kcal_max: float,
    expected_decision: Literal["ACCEPT", "WARN", "CLARIFY"],
) -> None:
    thresholds = load_range_decision_thresholds()
    result = apply_ledger_gate(
        kcal_min=kcal_min,
        kcal_best=kcal_best,
        kcal_max=kcal_max,
    )

    assert thresholds.accept_relative_width_max == pytest.approx(0.35)
    assert thresholds.warn_relative_width_max == pytest.approx(0.60)
    assert result.decision == expected_decision


def test_clarify_does_not_auto_write_ledger_without_log_anyway() -> None:
    result = apply_ledger_gate(
        kcal_min=60.0,
        kcal_best=100.0,
        kcal_max=130.0,
        log_anyway=False,
    )

    assert result.decision == "CLARIFY"
    assert result.relative_range_width == pytest.approx(0.70)
    assert result.should_write_ledger is False
    assert result.user_accepted_wide_range is None


def test_log_anyway_writes_low_confidence_with_user_acceptance_flag() -> None:
    ledger = AppendOnlyLedger()
    versions = _version_matrix()

    result = apply_ledger_gate(
        kcal_min=60.0,
        kcal_best=100.0,
        kcal_max=130.0,
        log_anyway=True,
        user_decline_clarify_reason="in_a_hurry",
        ledger=ledger,
        version_matrix=versions,
        meal_id="meal-1",
        user_id="user-1",
        trace_id="trace-1",
        entry_id="entry-log-anyway",
        top_uncertainty_drivers=["wide portion range"],
    )

    payload = build_log_anyway_ledger_payload(user_decline_clarify_reason="in_a_hurry")
    ledger_entry = ledger.get_entry("entry-log-anyway")

    assert result.decision == "CLARIFY"
    assert result.should_write_ledger is True
    assert result.ledger_entry_id == "entry-log-anyway"
    assert result.confidence_label == "low"
    assert result.user_accepted_wide_range is True
    assert result.user_decline_clarify_reason == "in_a_hurry"
    assert result.decision_reason.endswith(":log_anyway")
    assert payload["confidence_label"] == "low"
    assert payload["user_accepted_wide_range"] is True
    assert payload["user_decline_clarify_reason"] == "in_a_hurry"

    assert ledger_entry is not None
    assert ledger_entry.kcal_min == pytest.approx(60.0)
    assert ledger_entry.kcal_best == pytest.approx(100.0)
    assert ledger_entry.kcal_max == pytest.approx(130.0)
    assert ledger_entry.confidence_label == "low"
    assert ledger_entry.user_accepted_wide_range is True
    assert ledger_entry.user_decline_clarify_reason == "in_a_hurry"
    assert ledger_entry.top_uncertainty_drivers == ["wide portion range"]

    trace_event = TraceEvent(
        trace_id="trace-1",
        stage="ledger_gate",
        event_name="log_anyway",
        user_accepted_wide_range=ledger_entry.user_accepted_wide_range,
        user_decline_clarify_reason=ledger_entry.user_decline_clarify_reason,
    )
    assert trace_event.user_decline_clarify_reason == "in_a_hurry"


def test_log_anyway_rejects_reason_not_supported_by_trace_or_ledger() -> None:
    with pytest.raises(ValueError, match="invalid log-anyway reason"):
        apply_ledger_gate(
            kcal_min=60.0,
            kcal_best=100.0,
            kcal_max=130.0,
            log_anyway=True,
            user_decline_clarify_reason="need_fast_logging",
        )


def test_clarify_decline_reason_without_log_anyway_does_not_write_ledger() -> None:
    result = apply_ledger_gate(
        kcal_min=60.0,
        kcal_best=100.0,
        kcal_max=130.0,
        log_anyway=False,
        user_decline_clarify_reason="need_fast_logging",
    )

    assert result.decision == "CLARIFY"
    assert result.should_write_ledger is False
    assert result.user_accepted_wide_range is False
    assert result.user_decline_clarify_reason == "need_fast_logging"


def test_contract_violation_is_block_and_never_writes() -> None:
    result = apply_ledger_gate(
        kcal_min=80.0,
        kcal_best=100.0,
        kcal_max=115.0,
        contract_violation=True,
        log_anyway=True,
    )

    assert result.decision == "BLOCK"
    assert result.decision_reason == "contract_violation"
    assert result.should_write_ledger is False
    assert result.confidence_label == "low"


def test_missing_kcal_interval_contract_is_block_even_with_log_anyway() -> None:
    result = apply_ledger_gate(log_anyway=True)

    assert result.decision == "BLOCK"
    assert result.decision_reason == "contract_violation"
    assert result.should_write_ledger is False
    assert result.ledger_entry_id is None


def test_invalid_interval_contract_is_block_without_explicit_flag() -> None:
    result = apply_ledger_gate(
        kcal_min=120.0,
        kcal_best=100.0,
        kcal_max=130.0,
    )

    assert result.decision == "BLOCK"
    assert result.decision_reason == "contract_violation"
    assert result.should_write_ledger is False


def test_macro_ledger_entry_accepts_source_backed_estimate_without_correction_fields() -> None:
    entry = LedgerEntry(
        entry_id="entry-meal",
        meal_id="meal-1",
        user_id="user-1",
        trace_id="trace-1",
        kcal_min=60.0,
        kcal_best=100.0,
        kcal_max=130.0,
        confidence_label="low",
        user_accepted_wide_range=True,
        user_decline_clarify_reason="no_reference_available",
        version_matrix=_version_matrix(),
    )

    assert entry.corrected_grams is None
    assert entry.kcal_best == pytest.approx(100.0)


def test_macro_ledger_entry_rejects_unsupported_log_anyway_reason() -> None:
    with pytest.raises(ValidationError):
        LedgerEntry(
            entry_id="entry-meal",
            meal_id="meal-1",
            user_id="user-1",
            trace_id="trace-1",
            kcal_min=60.0,
            kcal_best=100.0,
            kcal_max=130.0,
            confidence_label="low",
            user_accepted_wide_range=True,
            user_decline_clarify_reason="need_fast_logging",
            version_matrix=_version_matrix(),
        )
