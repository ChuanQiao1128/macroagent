from __future__ import annotations

from pathlib import Path

import pytest

from services.cli.benchmark_report import generate_benchmark_report
from services.meal import (
    V0_3_REQUIRED_FIXTURE_IDS,
    build_fixture_group_index,
    load_fixture_results_jsonl,
)

FIXTURE_RESULTS_PATH = Path("evals/fixtures/benchmark_v0_3/task_036_fixture_results.jsonl")

EXPECTED_SCALE_EVIDENCE_FIXTURE_IDS = {
    "no_reference_low_impact",
    "no_reference_high_impact_bowl",
    "spoon_visible_near_plate",
    "fork_visible_far_from_plate",
    "saved_bowl_detected",
    "barcode_packaged_food",
    "card_like_object_with_pii",
    "plate_visible_unknown_size",
}

EXPECTED_ENERGY_DENSITY_FIXTURE_IDS = {
    "cooked_rice_correct_density",
    "dry_rice_incorrectly_used_for_cooked_rice",
    "sauce_mapped_to_oil",
    "mixed_bowl_aggregate_passes_component_fails",
}

EXPECTED_EVIDENCE_ARBITRATION_FIXTURE_IDS = {
    "compatible_portion_ranges_merge",
    "incompatible_macro_values_conflict",
    "user_correction_beats_default_prior",
    "llm_raw_macro_blocks",
}


@pytest.fixture(scope="module")
def fixture_rows() -> list[dict[str, object]]:
    assert FIXTURE_RESULTS_PATH.exists(), (
        f"Missing TASK-036 fixture results: {FIXTURE_RESULTS_PATH}"
    )
    return load_fixture_results_jsonl(FIXTURE_RESULTS_PATH)


def test_task_036_fixture_results_cover_all_required_fixture_ids(
    fixture_rows: list[dict[str, object]],
) -> None:
    expected_ids = set(V0_3_REQUIRED_FIXTURE_IDS)
    seen_ids = {
        row.get("fixture_id")
        for row in fixture_rows
        if isinstance(row.get("fixture_id"), str)
    }

    assert seen_ids == expected_ids
    assert len(fixture_rows) == len(expected_ids)


def test_task_036_fixture_groups_include_required_groups() -> None:
    groups = build_fixture_group_index()

    for required_group in (
        "friendly",
        "regression",
        "adversarial",
        "scale_evidence",
        "cross_cultural",
        "barcode_label_stub",
    ):
        assert required_group in groups

    assert set(groups["barcode_label_stub"]) == {
        "barcode_packaged_food",
        "card_like_object_with_pii",
    }


def test_task_036_fixture_groups_cover_required_v0_3_gate_fixtures() -> None:
    groups = build_fixture_group_index()

    assert set(groups["scale_evidence"]) == EXPECTED_SCALE_EVIDENCE_FIXTURE_IDS
    assert set(groups["cross_cultural"]) == (
        EXPECTED_ENERGY_DENSITY_FIXTURE_IDS | EXPECTED_EVIDENCE_ARBITRATION_FIXTURE_IDS
    )


def test_task_036_fixture_catalog_covers_required_v0_3_gate_fixtures() -> None:
    expected_ids = (
        EXPECTED_SCALE_EVIDENCE_FIXTURE_IDS
        | EXPECTED_ENERGY_DENSITY_FIXTURE_IDS
        | EXPECTED_EVIDENCE_ARBITRATION_FIXTURE_IDS
    )
    assert set(V0_3_REQUIRED_FIXTURE_IDS) == expected_ids


def test_task_036_benchmark_report_separates_segments_and_measures_conflict_rates() -> None:
    report = generate_benchmark_report(FIXTURE_RESULTS_PATH)

    assert report["missing_required_fixture_ids"] == []
    assert set(report["segments"]) == {"friendly", "regression", "adversarial"}

    segments = report["segments"]
    assert segments["friendly"]["rows"] == 7
    assert segments["regression"]["rows"] == 5
    assert segments["adversarial"]["rows"] == 4

    assert report["silent_high_conflict_rate"] == pytest.approx(1 / 16)
    assert report["overall"]["silent_high_conflict_rate"] == pytest.approx(1 / 16)


def test_task_036_benchmark_report_emits_clarify_trigger_distribution() -> None:
    report = generate_benchmark_report(FIXTURE_RESULTS_PATH)

    distribution = report["clarify_trigger_distribution"]
    assert set(distribution) == {"overall", "friendly", "regression", "adversarial"}

    assert distribution["overall"]["rows"] == 16
    assert distribution["overall"]["triggered"] == 3
    assert distribution["overall"]["trigger_rate"] == pytest.approx(3 / 16)

    assert distribution["friendly"]["triggered"] == 0
    assert distribution["regression"]["triggered"] == 3
    assert distribution["adversarial"]["triggered"] == 0
