from __future__ import annotations

import pytest
from pydantic import ValidationError

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
        semantic_judge_version="judge-v1",
    )


def test_ledger_entry_requires_version_matrix() -> None:
    with pytest.raises(ValidationError):
        LedgerEntry(
            entry_id="entry-1",
            corrected_grams=120.0,
        )


def test_ledger_version_matrix_requires_non_empty_source_dataset_versions() -> None:
    with pytest.raises(ValidationError):
        LedgerVersionMatrix(
            calculator_version="calc-v1",
            uncertainty_policy_version="uncertainty-v1",
            energy_density_policy_version="energy-v1",
            scale_evidence_policy_version="scale-v1",
            contract_yaml_version="contract-v1",
            source_dataset_versions={},
            takeoff_pipeline_version="takeoff-v1",
        )


def test_append_only_correction_chain_marks_latest_active_and_keeps_history() -> None:
    ledger = AppendOnlyLedger()
    versions = _version_matrix()

    first = ledger.append_correction(
        entry_id="entry-1",
        corrected_grams=120.0,
        meal_id="meal-1",
        component_name="white rice",
        version_matrix=versions,
    )
    second = ledger.append_correction(
        entry_id="entry-2",
        corrected_grams=130.0,
        meal_id="meal-1",
        component_name="white rice",
        supersedes_id=first.entry_id,
        version_matrix=versions,
    )

    stored_first = ledger.get_entry(first.entry_id)
    stored_second = ledger.get_entry(second.entry_id)

    assert stored_first is not None
    assert stored_second is not None
    assert stored_first.active is False
    assert stored_second.active is True
    assert stored_second.supersedes_id == first.entry_id
    assert stored_second.version_matrix.calculator_version == "calc-v1"

    assert tuple(entry.entry_id for entry in ledger.list_entries(include_inactive=True)) == (
        "entry-1",
        "entry-2",
    )
    assert tuple(entry.entry_id for entry in ledger.list_entries(include_inactive=False)) == (
        "entry-2",
    )


def test_append_only_correction_chain_rejects_superseding_inactive_entry() -> None:
    ledger = AppendOnlyLedger()
    versions = _version_matrix()

    first = ledger.append_correction(
        entry_id="entry-1",
        corrected_grams=120.0,
        version_matrix=versions,
    )
    ledger.append_correction(
        entry_id="entry-2",
        corrected_grams=130.0,
        supersedes_id=first.entry_id,
        version_matrix=versions,
    )

    with pytest.raises(ValueError, match="not active"):
        ledger.append_correction(
            entry_id="entry-3",
            corrected_grams=140.0,
            supersedes_id=first.entry_id,
            version_matrix=versions,
        )


def test_ledger_entry_decline_reason_requires_wide_range_false() -> None:
    versions = _version_matrix()

    with pytest.raises(ValidationError):
        LedgerEntry(
            entry_id="entry-1",
            corrected_grams=120.0,
            version_matrix=versions,
            user_accepted_wide_range=True,
            user_decline_clarify_reason="declined_to_answer",
        )
