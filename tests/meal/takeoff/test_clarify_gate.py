from __future__ import annotations

from typing import Literal

import pytest

from services.meal.takeoff.ledger_gate import (
    apply_ledger_gate,
    build_log_anyway_ledger_payload,
    load_range_decision_thresholds,
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
    result = apply_ledger_gate(
        kcal_min=60.0,
        kcal_best=100.0,
        kcal_max=130.0,
        log_anyway=True,
        user_decline_clarify_reason="in_a_hurry",
    )

    payload = build_log_anyway_ledger_payload(user_decline_clarify_reason="in_a_hurry")

    assert result.decision == "CLARIFY"
    assert result.should_write_ledger is True
    assert result.confidence_label == "low"
    assert result.user_accepted_wide_range is True
    assert result.user_decline_clarify_reason == "in_a_hurry"
    assert result.decision_reason.endswith(":log_anyway")
    assert payload["confidence_label"] == "low"
    assert payload["user_accepted_wide_range"] is True


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


def test_invalid_interval_contract_is_block_without_explicit_flag() -> None:
    result = apply_ledger_gate(
        kcal_min=120.0,
        kcal_best=100.0,
        kcal_max=130.0,
    )

    assert result.decision == "BLOCK"
    assert result.decision_reason == "contract_violation"
    assert result.should_write_ledger is False
