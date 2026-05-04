from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services.meal import analyze_meal_components
from services.storage import (
    build_portion_correction_prior_resolver,
    fetch_meal_by_id,
    fetch_portion_correction_by_id,
    fetch_portion_correction_priors,
    initialize_sqlite_ledger,
    insert_meal_estimate,
    insert_portion_correction,
)
from services.vision import FoodComponent


def _insert_seed_meal(db_path: Path) -> None:
    meal_estimate = analyze_meal_components(
        [FoodComponent(name="white rice", confidence=0.91, portion_hint="100 g")]
    )
    insert_meal_estimate(
        db_path,
        meal_estimate=meal_estimate,
        meal_id="meal-before-corrections",
        local_date="2026-05-04",
        created_at="2026-05-04T08:30:00+12:00",
    )


def test_portion_correction_migration_replay_preserves_existing_meal_data(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)
    _insert_seed_meal(db_path)
    before = fetch_meal_by_id(db_path, "meal-before-corrections")
    assert before is not None

    insert_portion_correction(
        db_path,
        component_name="white rice",
        selected_macro_entry_id="usda_seed_0001",
        selected_macro_entry_source="USDA",
        original_portion_grams_p10=90.0,
        original_portion_grams_p50=100.0,
        original_portion_grams_p90=110.0,
        corrected_grams=200.0,
        created_at="2026-05-04T09:00:00+12:00",
    )

    # Re-enter correction read path to ensure migration replay remains idempotent.
    priors = fetch_portion_correction_priors(
        db_path,
        component_name="white rice",
        selected_macro_entry_id="usda_seed_0001",
        selected_macro_entry_source="USDA",
        minimum_samples=3,
    )
    assert priors.macro_entry_prior is not None
    assert priors.applied_prior is None

    after = fetch_meal_by_id(db_path, "meal-before-corrections")
    assert after == before

    with sqlite3.connect(db_path) as connection:
        versions = connection.execute(
            "SELECT version, COUNT(*) FROM schema_migrations GROUP BY version ORDER BY version"
        ).fetchall()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    assert versions == [(1, 1), (2, 1)]
    assert "portion_corrections" in tables


def test_insert_and_fetch_portion_correction_round_trip_with_serving_label(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    correction_id = insert_portion_correction(
        db_path,
        correction_id="corr-001",
        component_name=" White   Rice ",
        selected_macro_entry_id="usda_seed_0001",
        selected_macro_entry_source="USDA",
        original_portion_grams_p10=90.0,
        original_portion_grams_p50=100.0,
        original_portion_grams_p90=110.0,
        corrected_serving_label=" 1 cup ",
        note="  user clarified full cup  ",
        created_at="2026-05-04T09:45:00+12:00",
    )

    assert correction_id == "corr-001"
    stored = fetch_portion_correction_by_id(db_path, correction_id)
    assert stored is not None
    assert stored.correction_id == "corr-001"
    assert stored.created_at == "2026-05-04T09:45:00+12:00"
    assert stored.component_name == "White   Rice"
    assert stored.component_name_normalized == "white rice"
    assert stored.selected_macro_entry_id == "usda_seed_0001"
    assert stored.selected_macro_entry_source == "USDA"
    assert stored.original_portion_grams_p10 == pytest.approx(90.0)
    assert stored.original_portion_grams_p50 == pytest.approx(100.0)
    assert stored.original_portion_grams_p90 == pytest.approx(110.0)
    assert stored.corrected_grams is None
    assert stored.corrected_serving_label == "1 cup"
    assert stored.corrected_grams_p50 == pytest.approx(190.0)
    assert stored.note == "user clarified full cup"


def test_fetch_portion_correction_priors_returns_macro_and_component_aggregates(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    for grams in (180.0, 200.0, 220.0):
        insert_portion_correction(
            db_path,
            component_name="white rice",
            selected_macro_entry_id="usda_seed_0001",
            selected_macro_entry_source="USDA",
            original_portion_grams_p10=90.0,
            original_portion_grams_p50=100.0,
            original_portion_grams_p90=110.0,
            corrected_grams=grams,
        )

    insert_portion_correction(
        db_path,
        component_name="white rice",
        original_portion_grams_p10=90.0,
        original_portion_grams_p50=100.0,
        original_portion_grams_p90=110.0,
        corrected_grams=240.0,
    )

    priors = fetch_portion_correction_priors(
        db_path,
        component_name="white rice",
        selected_macro_entry_id="usda_seed_0001",
        selected_macro_entry_source="USDA",
        minimum_samples=3,
    )

    assert priors.component_name_normalized == "white rice"
    assert priors.minimum_samples == 3
    assert priors.macro_entry_prior is not None
    assert priors.macro_entry_prior.strategy == "macro_entry"
    assert priors.macro_entry_prior.reference == "USDA:usda_seed_0001"
    assert priors.macro_entry_prior.sample_count == 3
    assert priors.macro_entry_prior.grams_p50 == pytest.approx(200.0)

    assert priors.normalized_component_prior is not None
    assert priors.normalized_component_prior.strategy == "normalized_component"
    assert priors.normalized_component_prior.reference == "white rice"
    assert priors.normalized_component_prior.sample_count == 4
    assert priors.normalized_component_prior.grams_p50 == pytest.approx(210.0)

    assert priors.applied_prior is not None
    assert priors.applied_prior.strategy == "macro_entry"
    assert priors.applied_prior.reference == "USDA:usda_seed_0001"
    assert priors.applied_prior.sample_count == 3
    assert priors.applied_prior.grams_p50 == pytest.approx(200.0)


def test_fetch_portion_correction_priors_falls_back_to_normalized_component_when_needed(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    for grams in (100.0, 120.0):
        insert_portion_correction(
            db_path,
            component_name="fried rice",
            selected_macro_entry_id="usda_seed_0001",
            selected_macro_entry_source="USDA",
            original_portion_grams_p10=90.0,
            original_portion_grams_p50=100.0,
            original_portion_grams_p90=110.0,
            corrected_grams=grams,
        )

    insert_portion_correction(
        db_path,
        component_name="fried rice",
        original_portion_grams_p10=90.0,
        original_portion_grams_p50=100.0,
        original_portion_grams_p90=110.0,
        corrected_grams=140.0,
    )

    priors = fetch_portion_correction_priors(
        db_path,
        component_name="fried rice",
        selected_macro_entry_id="usda_seed_0001",
        selected_macro_entry_source="USDA",
        minimum_samples=3,
    )

    assert priors.macro_entry_prior is not None
    assert priors.macro_entry_prior.sample_count == 2
    assert priors.macro_entry_prior.grams_p50 == pytest.approx(110.0)

    assert priors.normalized_component_prior is not None
    assert priors.normalized_component_prior.sample_count == 3
    assert priors.normalized_component_prior.grams_p50 == pytest.approx(120.0)

    assert priors.applied_prior is not None
    assert priors.applied_prior.strategy == "normalized_component"
    assert priors.applied_prior.reference == "fried rice"
    assert priors.applied_prior.sample_count == 3
    assert priors.applied_prior.grams_p50 == pytest.approx(120.0)


def test_sqlite_portion_prior_resolver_applies_persisted_prior_to_future_estimate(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    for grams in (180.0, 200.0, 220.0):
        insert_portion_correction(
            db_path,
            component_name="white rice",
            selected_macro_entry_id="usda_seed_0001",
            selected_macro_entry_source="USDA",
            original_portion_grams_p10=90.0,
            original_portion_grams_p50=100.0,
            original_portion_grams_p90=110.0,
            corrected_grams=grams,
        )

    resolver = build_portion_correction_prior_resolver(db_path, minimum_samples=3)
    meal = analyze_meal_components(
        [FoodComponent(name="white rice", confidence=0.91, portion_hint="100 g")],
        correction_prior_resolver=resolver,
        correction_prior_minimum_samples=3,
    )

    component = meal.component_estimates[0]
    assert component.portion_range.grams_p10 == 190.0
    assert component.portion_range.grams_p50 == pytest.approx(200.0)
    assert component.portion_range.grams_p90 == 210.0
    assert component.applied_portion_prior is not None
    assert component.applied_portion_prior.strategy == "macro_entry"
    assert component.applied_portion_prior.reference == "USDA:usda_seed_0001"
    assert component.applied_portion_prior.sample_count == 3
    assert component.applied_portion_prior.prior_grams_p50 == pytest.approx(200.0)
    assert component.applied_portion_prior.original_grams_p50 == 100.0
    assert component.applied_portion_prior.applied_grams_p50 == pytest.approx(200.0)


def test_fetch_portion_correction_priors_no_applied_prior_before_threshold(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    initialize_sqlite_ledger(db_path)

    for grams in (180.0, 200.0):
        insert_portion_correction(
            db_path,
            component_name="white rice",
            selected_macro_entry_id="usda_seed_0001",
            selected_macro_entry_source="USDA",
            original_portion_grams_p10=90.0,
            original_portion_grams_p50=100.0,
            original_portion_grams_p90=110.0,
            corrected_grams=grams,
        )

    priors = fetch_portion_correction_priors(
        db_path,
        component_name="white rice",
        selected_macro_entry_id="usda_seed_0001",
        selected_macro_entry_source="USDA",
        minimum_samples=3,
    )

    assert priors.macro_entry_prior is not None
    assert priors.macro_entry_prior.sample_count == 2
    assert priors.macro_entry_prior.grams_p50 == pytest.approx(190.0)

    assert priors.normalized_component_prior is not None
    assert priors.normalized_component_prior.sample_count == 2
    assert priors.normalized_component_prior.grams_p50 == pytest.approx(190.0)

    assert priors.applied_prior is None
