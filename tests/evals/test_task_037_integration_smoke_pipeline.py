from __future__ import annotations

from services.meal.src.integration_smoke_pipeline import run_integration_smoke_pipeline


def _results_by_fixture():
    result = run_integration_smoke_pipeline()
    return {fixture.fixture_id: fixture for fixture in result.fixtures}


def test_task_037_fixtures_run_end_to_end_with_expected_decisions():
    by_id = _results_by_fixture()

    assert by_id["accept_fixture"].decision == "ACCEPT"
    assert by_id["warn_fixture"].decision == "WARN"
    assert by_id["clarify_fixture"].decision == "CLARIFY"
    assert by_id["block_fixture"].decision == "BLOCK"


def test_task_037_all_stages_emit_trace_events():
    by_id = _results_by_fixture()

    # Pipeline stages in TASK-037:
    # MealCase -> ComponentTakeoff -> SourceSeed -> SourceCritic ->
    # ScaleEvidenceResolution -> PortionRange -> MacroQuantity ->
    # EvidenceArbitration -> LedgerGate -> TraceStore -> LedgerEntry
    expected_stage_count = 11

    assert by_id["accept_fixture"].trace_event_count == expected_stage_count
    assert by_id["warn_fixture"].trace_event_count == expected_stage_count
    assert by_id["clarify_fixture"].trace_event_count == expected_stage_count
    assert by_id["block_fixture"].trace_event_count == expected_stage_count


def test_task_037_clarify_supports_log_anyway_and_writes_ledger():
    fixture = _results_by_fixture()["clarify_fixture"]

    assert fixture.decision == "CLARIFY"
    assert fixture.ledger_written is True
    assert fixture.ledger_entry is not None
    assert fixture.ledger_entry.user_accepted_wide_range is True
    assert fixture.ledger_entry.user_decline_clarify_reason == "trusts_estimate"
    assert fixture.ledger_entry.confidence_label == "low"


def test_task_037_block_fixture_rejects_unsupported_llm_macro():
    fixture = _results_by_fixture()["block_fixture"]

    assert fixture.decision == "BLOCK"
    assert fixture.contract_violation is True
    assert fixture.ledger_written is False
    assert fixture.ledger_entry is None


def test_task_037_written_ledger_entries_include_version_matrix():
    by_id = _results_by_fixture()

    for fixture_id in ("accept_fixture", "warn_fixture", "clarify_fixture"):
        fixture = by_id[fixture_id]
        assert fixture.ledger_entry is not None
        assert fixture.ledger_entry.version_matrix is not None
        assert (
            fixture.ledger_entry.version_matrix.takeoff_pipeline_version
            == "integration_smoke_v0.1"
        )
