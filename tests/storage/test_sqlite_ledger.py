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
from services.meal import MealEstimate, analyze_meal_components
from services.storage import (
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
