from __future__ import annotations

from pathlib import Path

import pytest

from services.meal.takeoff.trace import InMemoryTraceEmitter
from services.storage import (
    fetch_user_daily_totals,
    fetch_user_meal_history,
    initialize_sqlite_ledger,
    insert_user_nutrition_ledger_entry,
    prepare_healthkit_export,
)


def test_fetch_user_daily_totals_scopes_to_user_day_and_active_deterministic_rows(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    accepted_entry_id = insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-a",
        entry_kind="accepted",
        source="deterministic",
        local_date="2026-05-04",
        created_at="2026-05-04T07:00:00+12:00",
        entry_id="entry-a-accepted",
        kcal=400.0,
        protein_g=20.0,
        carbs_g=40.0,
        fat_g=10.0,
        sugar_g=5.0,
        sodium_mg=300.0,
        fiber_g=4.0,
    )
    assert accepted_entry_id == "entry-a-accepted"

    insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-a",
        entry_kind="corrected",
        source="deterministic",
        supersedes_entry_id=accepted_entry_id,
        local_date="2026-05-04",
        created_at="2026-05-04T07:05:00+12:00",
        entry_id="entry-a-corrected",
        kcal=500.0,
        protein_g=25.0,
        carbs_g=55.0,
        fat_g=15.0,
        sugar_g=8.0,
        sodium_mg=350.0,
        fiber_g=6.0,
    )
    insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-b",
        entry_kind="accepted",
        source="deterministic",
        local_date="2026-05-04",
        created_at="2026-05-04T12:00:00+12:00",
        entry_id="entry-b-accepted",
        kcal=250.0,
        protein_g=10.0,
        carbs_g=30.0,
        fat_g=8.0,
        sugar_g=12.0,
        sodium_mg=150.0,
        fiber_g=3.0,
    )
    insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-manual",
        entry_kind="accepted",
        source="manual_entry",
        local_date="2026-05-04",
        created_at="2026-05-04T12:30:00+12:00",
        entry_id="entry-manual",
        kcal=999.0,
        protein_g=99.0,
        carbs_g=99.0,
        fat_g=99.0,
        sugar_g=99.0,
        sodium_mg=990.0,
        fiber_g=99.0,
    )
    insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-b",
        meal_id="meal-other-user",
        entry_kind="accepted",
        source="deterministic",
        local_date="2026-05-04",
        created_at="2026-05-04T13:00:00+12:00",
        entry_id="entry-other-user",
        kcal=777.0,
        protein_g=77.0,
        carbs_g=77.0,
        fat_g=77.0,
        sugar_g=77.0,
        sodium_mg=770.0,
        fiber_g=77.0,
    )
    insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-other-day",
        entry_kind="accepted",
        source="deterministic",
        local_date="2026-05-05",
        created_at="2026-05-05T08:00:00+12:00",
        entry_id="entry-other-day",
        kcal=888.0,
        protein_g=88.0,
        carbs_g=88.0,
        fat_g=88.0,
        sugar_g=88.0,
        sodium_mg=880.0,
        fiber_g=88.0,
    )

    totals = fetch_user_daily_totals(
        db_path,
        user_id="user-a",
        local_date="2026-05-04",
    )

    assert totals.user_id == "user-a"
    assert totals.local_date == "2026-05-04"
    assert totals.meal_count == 2
    assert totals.active_entry_count == 2
    assert totals.kcal == pytest.approx(750.0)
    assert totals.protein_g == pytest.approx(35.0)
    assert totals.carbs_g == pytest.approx(85.0)
    assert totals.fat_g == pytest.approx(23.0)
    assert totals.sugar_g == pytest.approx(20.0)
    assert totals.sodium_mg == pytest.approx(500.0)
    assert totals.fiber_g == pytest.approx(9.0)


def test_corrected_entries_supersede_totals_and_keep_append_only_history(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    original_entry_id = insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-a",
        entry_kind="accepted",
        source="deterministic",
        local_date="2026-05-04",
        created_at="2026-05-04T08:00:00+12:00",
        entry_id="entry-original",
        kcal=420.0,
        protein_g=18.0,
        carbs_g=50.0,
        fat_g=11.0,
        sugar_g=6.0,
        sodium_mg=320.0,
        fiber_g=5.0,
    )
    corrected_entry_id = insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-a",
        entry_kind="corrected",
        source="deterministic",
        supersedes_entry_id=original_entry_id,
        local_date="2026-05-04",
        created_at="2026-05-04T08:15:00+12:00",
        entry_id="entry-corrected",
        kcal=510.0,
        protein_g=23.0,
        carbs_g=57.0,
        fat_g=16.0,
        sugar_g=9.0,
        sodium_mg=360.0,
        fiber_g=7.0,
    )
    assert corrected_entry_id == "entry-corrected"

    history_with_inactive = fetch_user_meal_history(
        db_path,
        user_id="user-a",
        local_date="2026-05-04",
        include_inactive=True,
    )
    assert tuple(entry.entry_id for entry in history_with_inactive) == (
        "entry-corrected",
        "entry-original",
    )

    corrected_row = history_with_inactive[0]
    original_row = history_with_inactive[1]
    assert corrected_row.active is True
    assert corrected_row.supersedes_entry_id == "entry-original"
    assert original_row.active is False
    assert original_row.supersedes_entry_id is None
    assert original_row.nutrition.kcal == pytest.approx(420.0)
    assert original_row.nutrition.protein_g == pytest.approx(18.0)
    assert original_row.nutrition.carbs_g == pytest.approx(50.0)
    assert original_row.nutrition.fat_g == pytest.approx(11.0)
    assert original_row.nutrition.sugar_g == pytest.approx(6.0)
    assert original_row.nutrition.sodium_mg == pytest.approx(320.0)
    assert original_row.nutrition.fiber_g == pytest.approx(5.0)

    active_history = fetch_user_meal_history(
        db_path,
        user_id="user-a",
        local_date="2026-05-04",
        include_inactive=False,
    )
    assert tuple(entry.entry_id for entry in active_history) == ("entry-corrected",)

    totals = fetch_user_daily_totals(
        db_path,
        user_id="user-a",
        local_date="2026-05-04",
    )
    assert totals.meal_count == 1
    assert totals.active_entry_count == 1
    assert totals.kcal == pytest.approx(510.0)
    assert totals.protein_g == pytest.approx(23.0)
    assert totals.carbs_g == pytest.approx(57.0)
    assert totals.fat_g == pytest.approx(16.0)
    assert totals.sugar_g == pytest.approx(9.0)
    assert totals.sodium_mg == pytest.approx(360.0)
    assert totals.fiber_g == pytest.approx(7.0)


def test_prepare_healthkit_export_maps_all_supported_quantities_and_marks_skips(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-all-values",
        entry_kind="accepted",
        source="deterministic",
        local_date="2026-05-04",
        created_at="2026-05-04T08:00:00+12:00",
        entry_id="entry-all-values",
        kcal=610.0,
        protein_g=31.0,
        carbs_g=72.0,
        fat_g=22.0,
        sugar_g=14.0,
        sodium_mg=410.0,
        fiber_g=11.0,
    )
    superseded_entry_id = insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-partial-values",
        entry_kind="accepted",
        source="deterministic",
        local_date="2026-05-04",
        created_at="2026-05-04T08:05:00+12:00",
        entry_id="entry-partial-superseded",
        kcal=111.0,
    )
    insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-partial-values",
        entry_kind="corrected",
        source="deterministic",
        supersedes_entry_id=superseded_entry_id,
        local_date="2026-05-04",
        created_at="2026-05-04T08:06:00+12:00",
        entry_id="entry-partial-active",
        carbs_g=24.0,
        sodium_mg=120.0,
    )
    insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-manual",
        entry_kind="accepted",
        source="manual_entry",
        local_date="2026-05-04",
        created_at="2026-05-04T08:10:00+12:00",
        entry_id="entry-manual",
        kcal=1000.0,
    )
    insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-b",
        meal_id="meal-other-user",
        entry_kind="accepted",
        source="deterministic",
        local_date="2026-05-04",
        created_at="2026-05-04T08:20:00+12:00",
        entry_id="entry-other-user",
        kcal=200.0,
    )
    insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-other-day",
        entry_kind="accepted",
        source="deterministic",
        local_date="2026-05-05",
        created_at="2026-05-05T08:00:00+12:00",
        entry_id="entry-other-day",
        kcal=300.0,
    )

    emitter = InMemoryTraceEmitter()
    preparation = prepare_healthkit_export(
        db_path,
        user_id="user-a",
        local_date="2026-05-04",
        emitter=emitter,
    )

    assert preparation.user_id == "user-a"
    assert preparation.local_date == "2026-05-04"
    assert preparation.entry_count == 2
    assert tuple(entry.entry_id for entry in preparation.entries) == (
        "entry-all-values",
        "entry-partial-active",
    )

    expected_quantity_rows = (
        ("kcal", "HKQuantityTypeIdentifierDietaryEnergyConsumed", "kcal"),
        ("protein_g", "HKQuantityTypeIdentifierDietaryProtein", "g"),
        ("carbs_g", "HKQuantityTypeIdentifierDietaryCarbohydrates", "g"),
        ("fat_g", "HKQuantityTypeIdentifierDietaryFatTotal", "g"),
        ("sugar_g", "HKQuantityTypeIdentifierDietarySugar", "g"),
        ("sodium_mg", "HKQuantityTypeIdentifierDietarySodium", "mg"),
        ("fiber_g", "HKQuantityTypeIdentifierDietaryFiber", "g"),
    )

    complete_entry = preparation.entries[0]
    assert len(complete_entry.quantities) == 7
    for quantity, (metric_key, identifier, unit) in zip(
        complete_entry.quantities,
        expected_quantity_rows,
        strict=True,
    ):
        assert quantity.metric_key == metric_key
        assert quantity.healthkit_identifier == identifier
        assert quantity.unit == unit
        assert quantity.status == "ready"
        assert quantity.value is not None
        assert quantity.skip_reason is None

    partial_entry = preparation.entries[1]
    assert len(partial_entry.quantities) == 7
    partial_by_key = {quantity.metric_key: quantity for quantity in partial_entry.quantities}
    assert partial_by_key["carbs_g"].status == "ready"
    assert partial_by_key["carbs_g"].value == pytest.approx(24.0)
    assert partial_by_key["carbs_g"].skip_reason is None
    assert partial_by_key["sodium_mg"].status == "ready"
    assert partial_by_key["sodium_mg"].value == pytest.approx(120.0)
    assert partial_by_key["sodium_mg"].skip_reason is None

    skipped_metric_keys = ("kcal", "protein_g", "fat_g", "sugar_g", "fiber_g")
    for metric_key in skipped_metric_keys:
        skipped = partial_by_key[metric_key]
        assert skipped.status == "skipped"
        assert skipped.value is None
        assert skipped.skip_reason == "value_unavailable"

    assert len(emitter.events) == 1
    trace_event = emitter.events[0]
    assert trace_event.stage == "HealthKitExportPreparation"
    assert trace_event.event_name == "healthkit.export_prepared"
    assert trace_event.trace_id == "healthkit-export:user-a:2026-05-04"
    assert trace_event.payload == {
        "entry_count": 2,
        "ready_quantity_count": 9,
        "skipped_quantity_count": 5,
        "supported_quantity_count": 7,
    }


def test_history_and_daily_totals_emit_ledger_history_trace_events(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    insert_user_nutrition_ledger_entry(
        db_path,
        user_id="user-a",
        meal_id="meal-a",
        entry_kind="accepted",
        source="deterministic",
        local_date="2026-05-04",
        created_at="2026-05-04T10:00:00+12:00",
        entry_id="entry-a",
        kcal=100.0,
    )

    emitter = InMemoryTraceEmitter()
    history = fetch_user_meal_history(
        db_path,
        user_id="user-a",
        local_date="2026-05-04",
        include_inactive=True,
        limit=5,
        emitter=emitter,
    )
    totals = fetch_user_daily_totals(
        db_path,
        user_id="user-a",
        local_date="2026-05-04",
        emitter=emitter,
    )
    assert len(history) == 1
    assert totals.active_entry_count == 1

    assert len(emitter.events) == 2
    history_event = emitter.events[0]
    totals_event = emitter.events[1]

    assert history_event.stage == "LedgerHistory"
    assert history_event.event_name == "ledger.to_history"
    assert history_event.trace_id == "ledger-history:user-a:2026-05-04"
    assert history_event.payload == {
        "user_id": "user-a",
        "local_date": "2026-05-04",
        "history_entry_count": 1,
        "include_inactive": True,
        "limit": 5,
    }

    assert totals_event.stage == "LedgerHistory"
    assert totals_event.event_name == "ledger.daily_totals_prepared"
    assert totals_event.trace_id == "ledger-history:user-a:2026-05-04"
    assert totals_event.payload == {
        "user_id": "user-a",
        "local_date": "2026-05-04",
        "active_entry_count": 1,
        "meal_count": 1,
        "kcal": 100.0,
        "protein_g": 0.0,
        "carbs_g": 0.0,
        "fat_g": 0.0,
        "sugar_g": 0.0,
        "sodium_mg": 0.0,
        "fiber_g": 0.0,
    }
