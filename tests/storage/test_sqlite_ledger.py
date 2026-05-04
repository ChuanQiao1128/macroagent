from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from services.accounting import (
    MacroRange,
    calculate_macro_best_estimate,
    calculate_meal_macro_best_estimate,
)
from services.meal import MealEstimate, PortionCorrectionPrior, analyze_meal_components
from services.storage import (
    export_ledger_backup,
    fetch_daily_totals,
    fetch_meal_by_id,
    initialize_sqlite_ledger,
    insert_meal_estimate,
)
from services.vision import FoodComponent


def _build_meal_estimate(components: list[FoodComponent]) -> MealEstimate:
    return analyze_meal_components(components)


def test_initialize_sqlite_ledger_migration_replay_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite3"

    initialize_sqlite_ledger(db_path)
    initialize_sqlite_ledger(db_path)

    with sqlite3.connect(db_path) as conn:
        table_names = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "schema_migrations" in table_names
        assert "meals" in table_names
        assert "meal_component_estimates" in table_names

        versions = conn.execute(
            "SELECT version, COUNT(*) FROM schema_migrations GROUP BY version ORDER BY version"
        ).fetchall()

    assert versions == [(1, 1)]


def test_insert_and_fetch_meal_round_trip_with_component_trace_storage(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    meal_estimate = _build_meal_estimate(
        [
            FoodComponent(name="white rice", confidence=0.91, portion_hint="100 g"),
            FoodComponent(name="mystery foam", confidence=0.50, portion_hint="some amount"),
        ]
    )

    meal_id = insert_meal_estimate(
        db_path,
        meal_estimate=meal_estimate,
        meal_id="meal-001",
        local_date="2026-05-04",
        created_at="2026-05-04T08:30:00+12:00",
    )

    assert meal_id == "meal-001"

    stored = fetch_meal_by_id(db_path, meal_id)
    assert stored is not None
    assert stored.meal_id == "meal-001"
    assert stored.local_date == "2026-05-04"
    assert stored.created_at == "2026-05-04T08:30:00+12:00"
    assert stored.meal_estimate == meal_estimate
    assert stored.macro_best_estimate == calculate_meal_macro_best_estimate(
        meal_estimate.macro_interval
    )

    with sqlite3.connect(db_path) as conn:
        meal_row = conn.execute(
            "SELECT source_traces_json, meal_estimate_json FROM meals WHERE meal_id = ?",
            (meal_id,),
        ).fetchone()
        assert meal_row is not None

        source_traces_payload = json.loads(meal_row[0])
        meal_payload = json.loads(meal_row[1])

        assert len(source_traces_payload) == len(meal_estimate.macro_interval.source_traces)
        assert meal_payload["matched_component_count"] == meal_estimate.matched_component_count
        assert meal_payload["unmatched_component_count"] == meal_estimate.unmatched_component_count

        component_rows = conn.execute(
            (
                "SELECT status, source_trace_json "
                "FROM meal_component_estimates "
                "WHERE meal_id = ? "
                "ORDER BY component_index"
            ),
            (meal_id,),
        ).fetchall()

    assert len(component_rows) == len(meal_estimate.component_estimates)
    assert any(status == "matched" for status, _ in component_rows)
    assert any(status == "unmatched" for status, _ in component_rows)
    assert all(
        trace_json is not None for status, trace_json in component_rows if status == "matched"
    )
    assert all(trace_json is None for status, trace_json in component_rows if status == "unmatched")


def test_insert_and_fetch_meal_round_trip_preserves_applied_portion_prior_trace(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    def correction_prior_resolver(
        _component_name: str,
        _selected_macro_entry_id: str | None,
        _selected_macro_entry_source: str | None,
    ) -> PortionCorrectionPrior:
        return PortionCorrectionPrior(
            strategy="macro_entry",
            reference="USDA:usda_seed_0001",
            sample_count=3,
            grams_p50=95.0,
        )

    meal_estimate = analyze_meal_components(
        [FoodComponent(name="white rice", confidence=0.91, portion_hint="100 g")],
        correction_prior_resolver=correction_prior_resolver,
        correction_prior_minimum_samples=3,
    )
    meal_id = insert_meal_estimate(
        db_path,
        meal_estimate=meal_estimate,
        meal_id="meal-prior-trace",
        local_date="2026-05-04",
        created_at="2026-05-04T09:30:00+12:00",
    )

    stored = fetch_meal_by_id(db_path, meal_id)
    assert stored is not None
    component = stored.meal_estimate.component_estimates[0]
    assert component.applied_portion_prior is not None
    assert component.applied_portion_prior.strategy == "macro_entry"
    assert component.applied_portion_prior.reference == "USDA:usda_seed_0001"
    assert component.applied_portion_prior.sample_count == 3
    assert component.applied_portion_prior.prior_grams_p50 == 95.0
    assert component.applied_portion_prior.original_grams_p50 == 100.0
    assert component.applied_portion_prior.applied_grams_p50 == 95.0


def test_fetch_daily_totals_aggregates_only_requested_local_date(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    first = _build_meal_estimate(
        [
            FoodComponent(name="white rice", confidence=0.91, portion_hint="100 g"),
        ]
    )
    second = _build_meal_estimate(
        [
            FoodComponent(name="banana", confidence=0.93, portion_hint="half cup"),
            FoodComponent(name="mystery foam", confidence=0.55, portion_hint="some amount"),
        ]
    )
    other_day = _build_meal_estimate(
        [
            FoodComponent(name="banana", confidence=0.93, portion_hint="half cup"),
        ]
    )

    insert_meal_estimate(
        db_path,
        meal_estimate=first,
        local_date="2026-05-04",
        meal_id="meal-day-1-a",
        created_at="2026-05-04T07:00:00+12:00",
    )
    insert_meal_estimate(
        db_path,
        meal_estimate=second,
        local_date="2026-05-04",
        meal_id="meal-day-1-b",
        created_at="2026-05-04T13:00:00+12:00",
    )
    insert_meal_estimate(
        db_path,
        meal_estimate=other_day,
        local_date="2026-05-05",
        meal_id="meal-day-2-a",
        created_at="2026-05-05T08:00:00+12:00",
    )

    totals = fetch_daily_totals(db_path, "2026-05-04")

    expected_kcal_min = first.macro_interval.kcal.min + second.macro_interval.kcal.min
    expected_kcal_max = first.macro_interval.kcal.max + second.macro_interval.kcal.max
    expected_protein_min = first.macro_interval.protein_g.min + second.macro_interval.protein_g.min
    expected_protein_max = first.macro_interval.protein_g.max + second.macro_interval.protein_g.max
    expected_carbs_min = first.macro_interval.carbs_g.min + second.macro_interval.carbs_g.min
    expected_carbs_max = first.macro_interval.carbs_g.max + second.macro_interval.carbs_g.max
    expected_fat_min = first.macro_interval.fat_g.min + second.macro_interval.fat_g.min
    expected_fat_max = first.macro_interval.fat_g.max + second.macro_interval.fat_g.max

    assert totals.local_date == "2026-05-04"
    assert totals.meal_count == 2
    assert (
        totals.matched_component_count
        == first.matched_component_count + second.matched_component_count
    )
    assert totals.unmatched_component_count == (
        first.unmatched_component_count + second.unmatched_component_count
    )

    assert totals.kcal.min == pytest.approx(expected_kcal_min)
    assert totals.kcal.max == pytest.approx(expected_kcal_max)
    assert totals.protein_g.min == pytest.approx(expected_protein_min)
    assert totals.protein_g.max == pytest.approx(expected_protein_max)
    assert totals.carbs_g.min == pytest.approx(expected_carbs_min)
    assert totals.carbs_g.max == pytest.approx(expected_carbs_max)
    assert totals.fat_g.min == pytest.approx(expected_fat_min)
    assert totals.fat_g.max == pytest.approx(expected_fat_max)

    expected_kcal_best = calculate_macro_best_estimate(
        MacroRange(min=expected_kcal_min, max=expected_kcal_max)
    )
    expected_protein_best = calculate_macro_best_estimate(
        MacroRange(min=expected_protein_min, max=expected_protein_max)
    )
    expected_carbs_best = calculate_macro_best_estimate(
        MacroRange(min=expected_carbs_min, max=expected_carbs_max)
    )
    expected_fat_best = calculate_macro_best_estimate(
        MacroRange(min=expected_fat_min, max=expected_fat_max)
    )

    assert totals.macro_best_estimate.kcal == expected_kcal_best
    assert totals.macro_best_estimate.protein_g == expected_protein_best
    assert totals.macro_best_estimate.carbs_g == expected_carbs_best
    assert totals.macro_best_estimate.fat_g == expected_fat_best


def test_fetch_daily_totals_empty_day_returns_zero_ranges_and_arithmetic_midpoints(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    totals = fetch_daily_totals(db_path, "2026-05-04")

    assert totals.local_date == "2026-05-04"
    assert totals.meal_count == 0
    assert totals.matched_component_count == 0
    assert totals.unmatched_component_count == 0
    assert totals.kcal.min == 0.0
    assert totals.kcal.max == 0.0
    assert totals.protein_g.min == 0.0
    assert totals.protein_g.max == 0.0
    assert totals.carbs_g.min == 0.0
    assert totals.carbs_g.max == 0.0
    assert totals.fat_g.min == 0.0
    assert totals.fat_g.max == 0.0
    assert totals.macro_best_estimate.kcal.value == 0.0
    assert totals.macro_best_estimate.protein_g.value == 0.0
    assert totals.macro_best_estimate.carbs_g.value == 0.0
    assert totals.macro_best_estimate.fat_g.value == 0.0
    assert totals.macro_best_estimate.kcal.method == "arithmetic_midpoint"
    assert totals.macro_best_estimate.protein_g.method == "arithmetic_midpoint"
    assert totals.macro_best_estimate.carbs_g.method == "arithmetic_midpoint"
    assert totals.macro_best_estimate.fat_g.method == "arithmetic_midpoint"


def test_insert_meal_estimate_repeated_same_payload_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    meal_estimate = _build_meal_estimate(
        [
            FoodComponent(name="white rice", confidence=0.90, portion_hint="100 g"),
        ]
    )

    first_meal_id = insert_meal_estimate(
        db_path,
        meal_estimate=meal_estimate,
        local_date="2026-05-04",
        meal_id="meal-duplicate-safe",
        created_at="2026-05-04T12:00:00+12:00",
    )
    second_meal_id = insert_meal_estimate(
        db_path,
        meal_estimate=meal_estimate,
        local_date="2026-05-04",
        meal_id="meal-duplicate-safe",
        created_at="2026-05-04T12:00:00+12:00",
    )

    assert first_meal_id == "meal-duplicate-safe"
    assert second_meal_id == "meal-duplicate-safe"

    with sqlite3.connect(db_path) as conn:
        meal_row_count = conn.execute(
            "SELECT COUNT(*) FROM meals WHERE meal_id = ?",
            ("meal-duplicate-safe",),
        ).fetchone()
        component_row_count = conn.execute(
            "SELECT COUNT(*) FROM meal_component_estimates WHERE meal_id = ?",
            ("meal-duplicate-safe",),
        ).fetchone()

    assert meal_row_count is not None
    assert component_row_count is not None
    assert meal_row_count[0] == 1
    assert component_row_count[0] == len(meal_estimate.component_estimates)


def test_insert_meal_estimate_duplicate_id_with_different_payload_raises_value_error(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    first_meal = _build_meal_estimate(
        [
            FoodComponent(name="white rice", confidence=0.90, portion_hint="100 g"),
        ]
    )
    second_meal = _build_meal_estimate(
        [
            FoodComponent(name="banana", confidence=0.95, portion_hint="half cup"),
        ]
    )

    insert_meal_estimate(
        db_path,
        meal_estimate=first_meal,
        local_date="2026-05-04",
        meal_id="meal-conflict",
        created_at="2026-05-04T12:00:00+12:00",
    )

    with pytest.raises(ValueError, match="meal_id already exists: meal-conflict"):
        insert_meal_estimate(
            db_path,
            meal_estimate=second_meal,
            local_date="2026-05-04",
            meal_id="meal-conflict",
            created_at="2026-05-04T12:00:00+12:00",
        )


def test_fetch_meal_by_id_returns_none_when_meal_does_not_exist(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    stored = fetch_meal_by_id(db_path, "missing-meal-id")

    assert stored is None


def test_export_ledger_backup_empty_db_has_metadata_and_no_meals(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    payload = export_ledger_backup(db_path)

    assert payload["format"] == "macroagent.sqlite_ledger_backup"
    assert payload["export_schema_version"] == 1
    assert payload["ledger_schema_version"] == 1
    assert payload["meal_count"] == 0
    assert payload["meals"] == []
    assert payload["schema_migrations"] == [
        {"version": 1, "applied_at": payload["schema_migrations"][0]["applied_at"]}
    ]


def test_export_ledger_backup_populated_includes_meals_components_and_traces(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    meal_estimate = _build_meal_estimate(
        [
            FoodComponent(name="white rice", confidence=0.91, portion_hint="100 g"),
            FoodComponent(name="mystery foam", confidence=0.50, portion_hint="some amount"),
        ]
    )
    meal_best = calculate_meal_macro_best_estimate(meal_estimate.macro_interval)

    insert_meal_estimate(
        db_path,
        meal_estimate=meal_estimate,
        meal_id="meal-export-001",
        local_date="2026-05-04",
        created_at="2026-05-04T08:30:00+12:00",
    )

    payload = export_ledger_backup(db_path)

    assert payload["meal_count"] == 1
    meals = payload["meals"]
    assert isinstance(meals, list)
    assert len(meals) == 1

    meal = meals[0]
    assert meal["meal_id"] == "meal-export-001"
    assert meal["local_date"] == "2026-05-04"
    assert meal["created_at"] == "2026-05-04T08:30:00+12:00"
    assert meal["matched_component_count"] == meal_estimate.matched_component_count
    assert meal["unmatched_component_count"] == meal_estimate.unmatched_component_count
    assert meal["component_count"] == len(meal_estimate.component_estimates)
    assert meal["meal_estimate"] == meal_estimate.model_dump(mode="json")
    assert len(meal["source_traces"]) == len(meal_estimate.macro_interval.source_traces)

    assert meal["macro_ranges"]["kcal"]["min"] == pytest.approx(
        meal_estimate.macro_interval.kcal.min
    )
    assert meal["macro_ranges"]["kcal"]["max"] == pytest.approx(
        meal_estimate.macro_interval.kcal.max
    )
    assert meal["macro_ranges"]["protein_g"]["min"] == pytest.approx(
        meal_estimate.macro_interval.protein_g.min
    )
    assert meal["macro_ranges"]["protein_g"]["max"] == pytest.approx(
        meal_estimate.macro_interval.protein_g.max
    )
    assert meal["macro_ranges"]["carbs_g"]["min"] == pytest.approx(
        meal_estimate.macro_interval.carbs_g.min
    )
    assert meal["macro_ranges"]["carbs_g"]["max"] == pytest.approx(
        meal_estimate.macro_interval.carbs_g.max
    )
    assert meal["macro_ranges"]["fat_g"]["min"] == pytest.approx(
        meal_estimate.macro_interval.fat_g.min
    )
    assert meal["macro_ranges"]["fat_g"]["max"] == pytest.approx(
        meal_estimate.macro_interval.fat_g.max
    )

    assert meal["macro_best_estimate"]["kcal"]["value"] == pytest.approx(meal_best.kcal.value)
    assert meal["macro_best_estimate"]["kcal"]["method"] == meal_best.kcal.method
    assert meal["macro_best_estimate"]["protein_g"]["value"] == pytest.approx(
        meal_best.protein_g.value
    )
    assert meal["macro_best_estimate"]["protein_g"]["method"] == meal_best.protein_g.method
    assert meal["macro_best_estimate"]["carbs_g"]["value"] == pytest.approx(meal_best.carbs_g.value)
    assert meal["macro_best_estimate"]["carbs_g"]["method"] == meal_best.carbs_g.method
    assert meal["macro_best_estimate"]["fat_g"]["value"] == pytest.approx(meal_best.fat_g.value)
    assert meal["macro_best_estimate"]["fat_g"]["method"] == meal_best.fat_g.method

    components = meal["components"]
    assert isinstance(components, list)
    assert len(components) == len(meal_estimate.component_estimates)
    assert [component["component_index"] for component in components] == [0, 1]
    assert all("component_estimate" in component for component in components)
    assert all("top_candidates" in component for component in components)

    matched_component = next(
        component for component in components if component["status"] == "matched"
    )
    assert matched_component["macro_ranges"] is not None
    assert matched_component["macro_best_estimate"] is not None
    assert matched_component["source_trace"] is not None
    assert matched_component["selected_macro_entry"] is not None

    unmatched_component = next(
        component for component in components if component["status"] == "unmatched"
    )
    assert unmatched_component["macro_ranges"] is None
    assert unmatched_component["macro_best_estimate"] is None
    assert unmatched_component["source_trace"] is None
    assert unmatched_component["selected_macro_entry"] is None


def test_export_ledger_backup_is_deterministic_and_sorted(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    meal_a = _build_meal_estimate(
        [FoodComponent(name="banana", confidence=0.95, portion_hint="half cup")]
    )
    meal_b = _build_meal_estimate(
        [FoodComponent(name="white rice", confidence=0.90, portion_hint="100 g")]
    )
    meal_c = _build_meal_estimate(
        [FoodComponent(name="banana", confidence=0.94, portion_hint="1 cup")]
    )

    insert_meal_estimate(
        db_path,
        meal_estimate=meal_b,
        meal_id="meal-b",
        local_date="2026-05-04",
        created_at="2026-05-04T11:00:00+12:00",
    )
    insert_meal_estimate(
        db_path,
        meal_estimate=meal_c,
        meal_id="meal-c",
        local_date="2026-05-05",
        created_at="2026-05-05T09:00:00+12:00",
    )
    insert_meal_estimate(
        db_path,
        meal_estimate=meal_a,
        meal_id="meal-a",
        local_date="2026-05-04",
        created_at="2026-05-04T11:00:00+12:00",
    )

    first_export = export_ledger_backup(db_path)
    second_export = export_ledger_backup(db_path)

    assert first_export == second_export
    assert [meal["meal_id"] for meal in first_export["meals"]] == [
        "meal-a",
        "meal-b",
        "meal-c",
    ]


def test_export_ledger_backup_payload_is_json_serializable(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)
    meal_estimate = _build_meal_estimate(
        [FoodComponent(name="white rice", confidence=0.90, portion_hint="100 g")]
    )
    insert_meal_estimate(
        db_path,
        meal_estimate=meal_estimate,
        meal_id="meal-json",
        local_date="2026-05-04",
        created_at="2026-05-04T12:00:00+12:00",
    )

    payload = export_ledger_backup(db_path)
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded == payload
