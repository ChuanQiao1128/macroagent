from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.accounting import (
    MacroBestEstimate,
    MacroBestEstimateSet,
    MacroRange,
    MealMacroInterval,
    calculate_food_macro_best_estimate,
    calculate_macro_best_estimate,
    calculate_meal_macro_best_estimate,
)
from services.meal import (
    MealComponentEstimate,
    MealEstimate,
    PortionPriorResolver,
)
from services.meal import (
    PortionCorrectionPrior as MealPortionCorrectionPrior,
)
from services.meal.takeoff.trace import TraceEmitter, emit_stage_event
from services.nutrition import parse_portion_range
from services.nutrition.src.version_metadata import LEDGER_SCHEMA_VERSION

EntryKind = Literal["accepted", "corrected"]
EntrySource = Literal["deterministic", "manual_entry"]


class StoredMealEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    meal_id: str = Field(..., min_length=1)
    local_date: str = Field(..., min_length=10)
    created_at: str = Field(..., min_length=1)
    meal_estimate: MealEstimate
    macro_best_estimate: MacroBestEstimateSet


class DailyLedgerTotals(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    local_date: str = Field(..., min_length=10)
    meal_count: int = Field(..., ge=0)
    matched_component_count: int = Field(..., ge=0)
    unmatched_component_count: int = Field(..., ge=0)
    kcal: MacroRange
    protein_g: MacroRange
    carbs_g: MacroRange
    fat_g: MacroRange
    sugar_g: MacroRange
    sodium_mg: MacroRange
    fiber_g: MacroRange
    macro_best_estimate: MacroBestEstimateSet


class UserNutritionValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kcal: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    sugar_g: float | None = Field(default=None, ge=0)
    sodium_mg: float | None = Field(default=None, ge=0)
    fiber_g: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_has_metric(self) -> UserNutritionValues:
        if (
            self.kcal is None
            and self.protein_g is None
            and self.carbs_g is None
            and self.fat_g is None
            and self.sugar_g is None
            and self.sodium_mg is None
            and self.fiber_g is None
        ):
            raise ValueError("at least one nutrition metric is required")
        return self


class UserNutritionLedgerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_id: str = Field(..., min_length=1)
    created_at: str = Field(..., min_length=1)
    local_date: str = Field(..., min_length=10)
    user_id: str = Field(..., min_length=1)
    meal_id: str = Field(..., min_length=1)
    entry_kind: EntryKind
    source: EntrySource
    supersedes_entry_id: str | None = None
    active: bool
    trace_id: str | None = None
    note: str | None = None
    nutrition: UserNutritionValues


class UserDailyNutritionTotals(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str = Field(..., min_length=1)
    local_date: str = Field(..., min_length=10)
    meal_count: int = Field(..., ge=0)
    active_entry_count: int = Field(..., ge=0)
    kcal: float = Field(..., ge=0)
    protein_g: float = Field(..., ge=0)
    carbs_g: float = Field(..., ge=0)
    fat_g: float = Field(..., ge=0)
    sugar_g: float = Field(..., ge=0)
    sodium_mg: float = Field(..., ge=0)
    fiber_g: float = Field(..., ge=0)


class HealthKitPreparedQuantity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric_key: Literal[
        "kcal",
        "protein_g",
        "carbs_g",
        "fat_g",
        "sugar_g",
        "sodium_mg",
        "fiber_g",
    ]
    healthkit_identifier: str = Field(..., min_length=1)
    unit: str = Field(..., min_length=1)
    status: Literal["ready", "skipped"]
    value: float | None = Field(default=None, ge=0)
    skip_reason: Literal["value_unavailable"] | None = None

    @model_validator(mode="after")
    def _validate_status_pairing(self) -> HealthKitPreparedQuantity:
        if self.status == "ready":
            if self.value is None:
                raise ValueError("ready quantity requires value")
            if self.skip_reason is not None:
                raise ValueError("ready quantity must not include skip_reason")
            return self
        if self.skip_reason is None:
            raise ValueError("skipped quantity requires skip_reason")
        if self.value is not None:
            raise ValueError("skipped quantity must not include value")
        return self


class HealthKitPreparedEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_id: str = Field(..., min_length=1)
    meal_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    local_date: str = Field(..., min_length=10)
    created_at: str = Field(..., min_length=1)
    quantities: list[HealthKitPreparedQuantity] = Field(min_length=1)


class HealthKitExportPreparation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str = Field(..., min_length=1)
    local_date: str = Field(..., min_length=10)
    prepared_at: str = Field(..., min_length=1)
    entry_count: int = Field(..., ge=0)
    entries: list[HealthKitPreparedEntry] = Field(default_factory=list)


class PortionCorrectionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    correction_id: str = Field(..., min_length=1)
    created_at: str = Field(..., min_length=1)
    component_name: str = Field(..., min_length=1)
    component_name_normalized: str = Field(..., min_length=1)
    selected_macro_entry_id: str | None = None
    selected_macro_entry_source: Literal["USDA", "PERSONAL"] | None = None
    original_portion_grams_p10: float = Field(..., ge=0)
    original_portion_grams_p50: float = Field(..., ge=0)
    original_portion_grams_p90: float = Field(..., ge=0)
    corrected_grams: float | None = Field(default=None, gt=0)
    corrected_serving_label: str | None = None
    corrected_grams_p50: float = Field(..., gt=0)
    note: str | None = None

    @model_validator(mode="after")
    def _validate_fields(self) -> PortionCorrectionRecord:
        if self.original_portion_grams_p10 > self.original_portion_grams_p50:
            raise ValueError("original_portion_grams_p10 must be <= original_portion_grams_p50")
        if self.original_portion_grams_p50 > self.original_portion_grams_p90:
            raise ValueError("original_portion_grams_p50 must be <= original_portion_grams_p90")
        if bool(self.selected_macro_entry_id) != bool(self.selected_macro_entry_source):
            raise ValueError(
                "selected_macro_entry_id and selected_macro_entry_source must be set together"
            )
        if self.corrected_grams is None and not self.corrected_serving_label:
            raise ValueError("either corrected_grams or corrected_serving_label is required")
        if self.corrected_serving_label is not None and not self.corrected_serving_label.strip():
            raise ValueError("corrected_serving_label must not be empty")
        return self


class PortionCorrectionPrior(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: Literal["macro_entry", "normalized_component"]
    reference: str = Field(..., min_length=1)
    sample_count: int = Field(..., ge=1)
    grams_p50: float = Field(..., gt=0)


class PortionCorrectionPriors(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    component_name_normalized: str = Field(..., min_length=1)
    minimum_samples: int = Field(..., ge=1)
    macro_entry_prior: PortionCorrectionPrior | None = None
    normalized_component_prior: PortionCorrectionPrior | None = None
    applied_prior: PortionCorrectionPrior | None = None


@dataclass(frozen=True)
class _SchemaMigration:
    version: int
    sql: str


_MIGRATIONS: tuple[_SchemaMigration, ...] = (
    _SchemaMigration(
        version=1,
        sql="""
        CREATE TABLE IF NOT EXISTS meals (
            meal_id TEXT PRIMARY KEY,
            local_date TEXT NOT NULL,
            created_at TEXT NOT NULL,
            matched_component_count INTEGER NOT NULL,
            unmatched_component_count INTEGER NOT NULL,
            component_count INTEGER NOT NULL,
            kcal_min REAL NOT NULL,
            kcal_max REAL NOT NULL,
            protein_g_min REAL NOT NULL,
            protein_g_max REAL NOT NULL,
            carbs_g_min REAL NOT NULL,
            carbs_g_max REAL NOT NULL,
            fat_g_min REAL NOT NULL,
            fat_g_max REAL NOT NULL,
            best_kcal REAL NOT NULL,
            best_kcal_method TEXT NOT NULL,
            best_protein_g REAL NOT NULL,
            best_protein_g_method TEXT NOT NULL,
            best_carbs_g REAL NOT NULL,
            best_carbs_g_method TEXT NOT NULL,
            best_fat_g REAL NOT NULL,
            best_fat_g_method TEXT NOT NULL,
            source_traces_json TEXT NOT NULL,
            meal_estimate_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_meals_local_date
            ON meals(local_date);

        CREATE TABLE IF NOT EXISTS meal_component_estimates (
            meal_id TEXT NOT NULL,
            component_index INTEGER NOT NULL,
            component_name TEXT NOT NULL,
            component_confidence REAL NOT NULL,
            portion_hint TEXT,
            status TEXT NOT NULL CHECK (status IN ('matched', 'unmatched')),
            top_candidates_json TEXT NOT NULL,
            selected_macro_entry_id TEXT,
            selected_macro_entry_name TEXT,
            selected_macro_entry_source TEXT,
            selected_match_score REAL,
            portion_grams_min REAL NOT NULL,
            portion_grams_max REAL NOT NULL,
            portion_confidence REAL NOT NULL,
            portion_source TEXT NOT NULL,
            portion_reason TEXT NOT NULL,
            unmatched_reason TEXT,
            kcal_min REAL,
            kcal_max REAL,
            protein_g_min REAL,
            protein_g_max REAL,
            carbs_g_min REAL,
            carbs_g_max REAL,
            fat_g_min REAL,
            fat_g_max REAL,
            best_kcal REAL,
            best_kcal_method TEXT,
            best_protein_g REAL,
            best_protein_g_method TEXT,
            best_carbs_g REAL,
            best_carbs_g_method TEXT,
            best_fat_g REAL,
            best_fat_g_method TEXT,
            source_trace_json TEXT,
            component_estimate_json TEXT NOT NULL,
            PRIMARY KEY (meal_id, component_index),
            FOREIGN KEY (meal_id) REFERENCES meals (meal_id) ON DELETE CASCADE
        );
        """,
    ),
    _SchemaMigration(
        version=2,
        sql="""
        CREATE TABLE IF NOT EXISTS portion_corrections (
            correction_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            component_name TEXT NOT NULL,
            component_name_normalized TEXT NOT NULL,
            selected_macro_entry_id TEXT,
            selected_macro_entry_source TEXT
                CHECK (selected_macro_entry_source IN ('USDA', 'PERSONAL')),
            original_portion_grams_p10 REAL NOT NULL,
            original_portion_grams_p50 REAL NOT NULL,
            original_portion_grams_p90 REAL NOT NULL,
            corrected_grams REAL,
            corrected_serving_label TEXT,
            corrected_grams_p50 REAL NOT NULL,
            note TEXT,
            CHECK (
                corrected_grams IS NOT NULL
                OR corrected_serving_label IS NOT NULL
            ),
            CHECK (
                selected_macro_entry_id IS NULL
                OR selected_macro_entry_source IS NOT NULL
            ),
            CHECK (
                selected_macro_entry_source IS NULL
                OR selected_macro_entry_id IS NOT NULL
            )
        );

        CREATE INDEX IF NOT EXISTS idx_portion_corrections_macro_entry
            ON portion_corrections(selected_macro_entry_id, selected_macro_entry_source);

        CREATE INDEX IF NOT EXISTS idx_portion_corrections_component
            ON portion_corrections(component_name_normalized);
        """,
    ),
    _SchemaMigration(
        version=3,
        sql="""
        ALTER TABLE meals ADD COLUMN sugar_g_min REAL NOT NULL DEFAULT 0;
        ALTER TABLE meals ADD COLUMN sugar_g_max REAL NOT NULL DEFAULT 0;
        ALTER TABLE meals ADD COLUMN sodium_mg_min REAL NOT NULL DEFAULT 0;
        ALTER TABLE meals ADD COLUMN sodium_mg_max REAL NOT NULL DEFAULT 0;
        ALTER TABLE meals ADD COLUMN fiber_g_min REAL NOT NULL DEFAULT 0;
        ALTER TABLE meals ADD COLUMN fiber_g_max REAL NOT NULL DEFAULT 0;
        ALTER TABLE meals ADD COLUMN best_sugar_g REAL NOT NULL DEFAULT 0;
        ALTER TABLE meals
            ADD COLUMN best_sugar_g_method TEXT NOT NULL DEFAULT 'arithmetic_midpoint';
        ALTER TABLE meals ADD COLUMN best_sodium_mg REAL NOT NULL DEFAULT 0;
        ALTER TABLE meals
            ADD COLUMN best_sodium_mg_method TEXT NOT NULL DEFAULT 'arithmetic_midpoint';
        ALTER TABLE meals ADD COLUMN best_fiber_g REAL NOT NULL DEFAULT 0;
        ALTER TABLE meals
            ADD COLUMN best_fiber_g_method TEXT NOT NULL DEFAULT 'arithmetic_midpoint';

        ALTER TABLE meal_component_estimates ADD COLUMN sugar_g_min REAL;
        ALTER TABLE meal_component_estimates ADD COLUMN sugar_g_max REAL;
        ALTER TABLE meal_component_estimates ADD COLUMN sodium_mg_min REAL;
        ALTER TABLE meal_component_estimates ADD COLUMN sodium_mg_max REAL;
        ALTER TABLE meal_component_estimates ADD COLUMN fiber_g_min REAL;
        ALTER TABLE meal_component_estimates ADD COLUMN fiber_g_max REAL;
        ALTER TABLE meal_component_estimates ADD COLUMN best_sugar_g REAL;
        ALTER TABLE meal_component_estimates ADD COLUMN best_sugar_g_method TEXT;
        ALTER TABLE meal_component_estimates ADD COLUMN best_sodium_mg REAL;
        ALTER TABLE meal_component_estimates ADD COLUMN best_sodium_mg_method TEXT;
        ALTER TABLE meal_component_estimates ADD COLUMN best_fiber_g REAL;
        ALTER TABLE meal_component_estimates ADD COLUMN best_fiber_g_method TEXT;
        """,
    ),
    _SchemaMigration(
        version=4,
        sql="""
        CREATE TABLE IF NOT EXISTS user_nutrition_ledger_entries (
            entry_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            local_date TEXT NOT NULL,
            user_id TEXT NOT NULL,
            meal_id TEXT NOT NULL,
            entry_kind TEXT NOT NULL
                CHECK (entry_kind IN ('accepted', 'corrected')),
            source TEXT NOT NULL
                CHECK (source IN ('deterministic', 'manual_entry')),
            supersedes_entry_id TEXT,
            active INTEGER NOT NULL CHECK (active IN (0, 1)),
            trace_id TEXT,
            note TEXT,
            kcal REAL CHECK (kcal IS NULL OR kcal >= 0),
            protein_g REAL CHECK (protein_g IS NULL OR protein_g >= 0),
            carbs_g REAL CHECK (carbs_g IS NULL OR carbs_g >= 0),
            fat_g REAL CHECK (fat_g IS NULL OR fat_g >= 0),
            sugar_g REAL CHECK (sugar_g IS NULL OR sugar_g >= 0),
            sodium_mg REAL CHECK (sodium_mg IS NULL OR sodium_mg >= 0),
            fiber_g REAL CHECK (fiber_g IS NULL OR fiber_g >= 0),
            CHECK (
                kcal IS NOT NULL
                OR protein_g IS NOT NULL
                OR carbs_g IS NOT NULL
                OR fat_g IS NOT NULL
                OR sugar_g IS NOT NULL
                OR sodium_mg IS NOT NULL
                OR fiber_g IS NOT NULL
            ),
            FOREIGN KEY (supersedes_entry_id)
                REFERENCES user_nutrition_ledger_entries(entry_id)
        );

        CREATE INDEX IF NOT EXISTS idx_user_nutrition_entries_user_date
            ON user_nutrition_ledger_entries(user_id, local_date, created_at, entry_id);

        CREATE INDEX IF NOT EXISTS idx_user_nutrition_entries_active
            ON user_nutrition_ledger_entries(user_id, local_date, active);

        CREATE INDEX IF NOT EXISTS idx_user_nutrition_entries_supersedes
            ON user_nutrition_ledger_entries(supersedes_entry_id);
        """,
    ),
)

_EXPORT_FORMAT = "macroagent.sqlite_ledger_backup"
_EXPORT_SCHEMA_VERSION = LEDGER_SCHEMA_VERSION
_LATEST_SCHEMA_VERSION = _MIGRATIONS[-1].version if _MIGRATIONS else 0
_USER_HISTORY_TRACE_STAGE = "LedgerHistory"
_HEALTHKIT_PREP_TRACE_STAGE = "HealthKitExportPreparation"
_HEALTHKIT_QUANTITY_MAPPINGS: tuple[tuple[str, str, str], ...] = (
    ("kcal", "HKQuantityTypeIdentifierDietaryEnergyConsumed", "kcal"),
    ("protein_g", "HKQuantityTypeIdentifierDietaryProtein", "g"),
    ("carbs_g", "HKQuantityTypeIdentifierDietaryCarbohydrates", "g"),
    ("fat_g", "HKQuantityTypeIdentifierDietaryFatTotal", "g"),
    ("sugar_g", "HKQuantityTypeIdentifierDietarySugar", "g"),
    ("sodium_mg", "HKQuantityTypeIdentifierDietarySodium", "mg"),
    ("fiber_g", "HKQuantityTypeIdentifierDietaryFiber", "g"),
)


def initialize_sqlite_ledger(database_path: str | Path) -> None:
    """Create or migrate the local SQLite ledger schema."""
    db_target = _normalize_database_path(database_path)
    if db_target != ":memory:":
        Path(db_target).parent.mkdir(parents=True, exist_ok=True)

    with _connect(db_target) as connection:
        _apply_migrations(connection)


def insert_meal_estimate(
    database_path: str | Path,
    *,
    meal_estimate: MealEstimate,
    local_date: str | None = None,
    meal_id: str | None = None,
    created_at: str | datetime | None = None,
) -> str:
    """
    Persist one meal estimate and return its meal_id.

    `local_date` must be YYYY-MM-DD. When omitted, it is derived from `created_at`.
    """
    created_dt = _coerce_created_at(created_at)
    created_at_iso = created_dt.isoformat(timespec="seconds")
    resolved_local_date = _validate_local_date(local_date or created_dt.date().isoformat())
    resolved_meal_id = meal_id or str(uuid.uuid4())

    meal_macro_best = calculate_meal_macro_best_estimate(meal_estimate.macro_interval)
    macro_interval = meal_estimate.macro_interval
    source_traces_json = _json_dumps(
        [trace.model_dump(mode="json") for trace in macro_interval.source_traces]
    )
    meal_estimate_json = _json_dumps(meal_estimate.model_dump(mode="json"))

    with _connect(_normalize_database_path(database_path)) as connection:
        _apply_migrations(connection)
        try:
            connection.execute(
                """
                INSERT INTO meals (
                    meal_id,
                    local_date,
                    created_at,
                    matched_component_count,
                    unmatched_component_count,
                    component_count,
                    kcal_min,
                    kcal_max,
                    protein_g_min,
                    protein_g_max,
                    carbs_g_min,
                    carbs_g_max,
                    fat_g_min,
                    fat_g_max,
                    sugar_g_min,
                    sugar_g_max,
                    sodium_mg_min,
                    sodium_mg_max,
                    fiber_g_min,
                    fiber_g_max,
                    best_kcal,
                    best_kcal_method,
                    best_protein_g,
                    best_protein_g_method,
                    best_carbs_g,
                    best_carbs_g_method,
                    best_fat_g,
                    best_fat_g_method,
                    best_sugar_g,
                    best_sugar_g_method,
                    best_sodium_mg,
                    best_sodium_mg_method,
                    best_fiber_g,
                    best_fiber_g_method,
                    source_traces_json,
                    meal_estimate_json
                ) VALUES (
                    :meal_id,
                    :local_date,
                    :created_at,
                    :matched_component_count,
                    :unmatched_component_count,
                    :component_count,
                    :kcal_min,
                    :kcal_max,
                    :protein_g_min,
                    :protein_g_max,
                    :carbs_g_min,
                    :carbs_g_max,
                    :fat_g_min,
                    :fat_g_max,
                    :sugar_g_min,
                    :sugar_g_max,
                    :sodium_mg_min,
                    :sodium_mg_max,
                    :fiber_g_min,
                    :fiber_g_max,
                    :best_kcal,
                    :best_kcal_method,
                    :best_protein_g,
                    :best_protein_g_method,
                    :best_carbs_g,
                    :best_carbs_g_method,
                    :best_fat_g,
                    :best_fat_g_method,
                    :best_sugar_g,
                    :best_sugar_g_method,
                    :best_sodium_mg,
                    :best_sodium_mg_method,
                    :best_fiber_g,
                    :best_fiber_g_method,
                    :source_traces_json,
                    :meal_estimate_json
                )
                """,
                {
                    "meal_id": resolved_meal_id,
                    "local_date": resolved_local_date,
                    "created_at": created_at_iso,
                    "matched_component_count": meal_estimate.matched_component_count,
                    "unmatched_component_count": meal_estimate.unmatched_component_count,
                    "component_count": len(meal_estimate.component_estimates),
                    "kcal_min": macro_interval.kcal.min,
                    "kcal_max": macro_interval.kcal.max,
                    "protein_g_min": macro_interval.protein_g.min,
                    "protein_g_max": macro_interval.protein_g.max,
                    "carbs_g_min": macro_interval.carbs_g.min,
                    "carbs_g_max": macro_interval.carbs_g.max,
                    "fat_g_min": macro_interval.fat_g.min,
                    "fat_g_max": macro_interval.fat_g.max,
                    "sugar_g_min": macro_interval.sugar_g.min,
                    "sugar_g_max": macro_interval.sugar_g.max,
                    "sodium_mg_min": macro_interval.sodium_mg.min,
                    "sodium_mg_max": macro_interval.sodium_mg.max,
                    "fiber_g_min": macro_interval.fiber_g.min,
                    "fiber_g_max": macro_interval.fiber_g.max,
                    "best_kcal": meal_macro_best.kcal.value,
                    "best_kcal_method": meal_macro_best.kcal.method,
                    "best_protein_g": meal_macro_best.protein_g.value,
                    "best_protein_g_method": meal_macro_best.protein_g.method,
                    "best_carbs_g": meal_macro_best.carbs_g.value,
                    "best_carbs_g_method": meal_macro_best.carbs_g.method,
                    "best_fat_g": meal_macro_best.fat_g.value,
                    "best_fat_g_method": meal_macro_best.fat_g.method,
                    "best_sugar_g": meal_macro_best.sugar_g.value,
                    "best_sugar_g_method": meal_macro_best.sugar_g.method,
                    "best_sodium_mg": meal_macro_best.sodium_mg.value,
                    "best_sodium_mg_method": meal_macro_best.sodium_mg.method,
                    "best_fiber_g": meal_macro_best.fiber_g.value,
                    "best_fiber_g_method": meal_macro_best.fiber_g.method,
                    "source_traces_json": source_traces_json,
                    "meal_estimate_json": meal_estimate_json,
                },
            )
        except sqlite3.IntegrityError as exc:
            if _is_existing_meal_idempotent(
                connection=connection,
                meal_id=resolved_meal_id,
                local_date=resolved_local_date,
                created_at=created_at_iso,
                matched_component_count=meal_estimate.matched_component_count,
                unmatched_component_count=meal_estimate.unmatched_component_count,
                component_count=len(meal_estimate.component_estimates),
                macro_interval=macro_interval,
                meal_macro_best=meal_macro_best,
                source_traces_json=source_traces_json,
                meal_estimate_json=meal_estimate_json,
            ):
                return resolved_meal_id
            raise ValueError(f"meal_id already exists: {resolved_meal_id}") from exc

        for component_index, component in enumerate(meal_estimate.component_estimates):
            _insert_component_row(
                connection=connection,
                meal_id=resolved_meal_id,
                component_index=component_index,
                component=component,
            )

    return resolved_meal_id


def insert_portion_correction(
    database_path: str | Path,
    *,
    component_name: str,
    selected_macro_entry_id: str | None = None,
    selected_macro_entry_source: Literal["USDA", "PERSONAL"] | None = None,
    original_portion_grams_p10: float,
    original_portion_grams_p50: float,
    original_portion_grams_p90: float,
    corrected_grams: float | None = None,
    corrected_serving_label: str | None = None,
    note: str | None = None,
    correction_id: str | None = None,
    created_at: str | datetime | None = None,
) -> str:
    """
    Persist one local user portion correction and return its correction_id.

    Corrections are used to derive deterministic portion priors for future estimates.
    """
    normalized_component_name = _normalize_component_name(component_name)
    if not normalized_component_name:
        raise ValueError("component_name must include at least one alphanumeric token")
    if bool(selected_macro_entry_id) != bool(selected_macro_entry_source):
        raise ValueError(
            "selected_macro_entry_id and selected_macro_entry_source must be set together"
        )
    if original_portion_grams_p10 < 0:
        raise ValueError("original_portion_grams_p10 must be >= 0")
    if original_portion_grams_p50 < 0:
        raise ValueError("original_portion_grams_p50 must be >= 0")
    if original_portion_grams_p90 < 0:
        raise ValueError("original_portion_grams_p90 must be >= 0")
    if original_portion_grams_p10 > original_portion_grams_p50:
        raise ValueError("original_portion_grams_p10 must be <= original_portion_grams_p50")
    if original_portion_grams_p50 > original_portion_grams_p90:
        raise ValueError("original_portion_grams_p50 must be <= original_portion_grams_p90")

    resolved_correction_id = correction_id or str(uuid.uuid4())
    created_dt = _coerce_created_at(created_at)
    created_at_iso = created_dt.isoformat(timespec="seconds")
    resolved_corrected_serving_label = (
        corrected_serving_label.strip()
        if corrected_serving_label is not None and corrected_serving_label.strip()
        else None
    )
    resolved_note = note.strip() if note is not None and note.strip() else None
    corrected_grams_p50 = _resolve_corrected_grams_p50(
        component_name=component_name,
        corrected_grams=corrected_grams,
        corrected_serving_label=resolved_corrected_serving_label,
    )

    with _connect(_normalize_database_path(database_path)) as connection:
        _apply_migrations(connection, target_version=_LATEST_SCHEMA_VERSION)
        try:
            connection.execute(
                """
                INSERT INTO portion_corrections (
                    correction_id,
                    created_at,
                    component_name,
                    component_name_normalized,
                    selected_macro_entry_id,
                    selected_macro_entry_source,
                    original_portion_grams_p10,
                    original_portion_grams_p50,
                    original_portion_grams_p90,
                    corrected_grams,
                    corrected_serving_label,
                    corrected_grams_p50,
                    note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_correction_id,
                    created_at_iso,
                    component_name.strip(),
                    normalized_component_name,
                    selected_macro_entry_id,
                    selected_macro_entry_source,
                    original_portion_grams_p10,
                    original_portion_grams_p50,
                    original_portion_grams_p90,
                    corrected_grams,
                    resolved_corrected_serving_label,
                    corrected_grams_p50,
                    resolved_note,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"correction_id already exists: {resolved_correction_id}") from exc

    return resolved_correction_id


def fetch_portion_correction_by_id(
    database_path: str | Path,
    correction_id: str,
) -> PortionCorrectionRecord | None:
    """Return one correction by id, or None if it does not exist."""
    with _connect(_normalize_database_path(database_path)) as connection:
        _apply_migrations(connection, target_version=_LATEST_SCHEMA_VERSION)
        row = connection.execute(
            """
            SELECT
                correction_id,
                created_at,
                component_name,
                component_name_normalized,
                selected_macro_entry_id,
                selected_macro_entry_source,
                original_portion_grams_p10,
                original_portion_grams_p50,
                original_portion_grams_p90,
                corrected_grams,
                corrected_serving_label,
                corrected_grams_p50,
                note
            FROM portion_corrections
            WHERE correction_id = ?
            """,
            (correction_id,),
        ).fetchone()
    if row is None:
        return None
    return _build_portion_correction_record(row)


def fetch_portion_correction_priors(
    database_path: str | Path,
    *,
    component_name: str,
    selected_macro_entry_id: str | None = None,
    selected_macro_entry_source: Literal["USDA", "PERSONAL"] | None = None,
    minimum_samples: int = 3,
) -> PortionCorrectionPriors:
    """
    Fetch correction-derived priors for one component.

    Prior selection order is deterministic: macro entry first, then normalized component.
    """
    if minimum_samples <= 0:
        raise ValueError("minimum_samples must be greater than 0")
    if bool(selected_macro_entry_id) != bool(selected_macro_entry_source):
        raise ValueError(
            "selected_macro_entry_id and selected_macro_entry_source must be set together"
        )

    component_name_normalized = _normalize_component_name(component_name)
    if not component_name_normalized:
        raise ValueError("component_name must include at least one alphanumeric token")

    with _connect(_normalize_database_path(database_path)) as connection:
        _apply_migrations(connection, target_version=_LATEST_SCHEMA_VERSION)
        macro_row = None
        if selected_macro_entry_id is not None and selected_macro_entry_source is not None:
            macro_row = connection.execute(
                """
                SELECT
                    COUNT(*) AS sample_count,
                    AVG(corrected_grams_p50) AS grams_p50
                FROM portion_corrections
                WHERE selected_macro_entry_id = ?
                  AND selected_macro_entry_source = ?
                """,
                (selected_macro_entry_id, selected_macro_entry_source),
            ).fetchone()

        component_row = connection.execute(
            """
            SELECT
                COUNT(*) AS sample_count,
                AVG(corrected_grams_p50) AS grams_p50
            FROM portion_corrections
            WHERE component_name_normalized = ?
            """,
            (component_name_normalized,),
        ).fetchone()

    macro_entry_prior = _build_prior_from_row(
        strategy="macro_entry",
        reference=(
            f"{selected_macro_entry_source}:{selected_macro_entry_id}"
            if selected_macro_entry_id is not None and selected_macro_entry_source is not None
            else ""
        ),
        row=macro_row,
    )
    normalized_component_prior = _build_prior_from_row(
        strategy="normalized_component",
        reference=component_name_normalized,
        row=component_row,
    )
    applied_prior: PortionCorrectionPrior | None = None
    if macro_entry_prior is not None and macro_entry_prior.sample_count >= minimum_samples:
        applied_prior = macro_entry_prior
    elif (
        normalized_component_prior is not None
        and normalized_component_prior.sample_count >= minimum_samples
    ):
        applied_prior = normalized_component_prior

    return PortionCorrectionPriors(
        component_name_normalized=component_name_normalized,
        minimum_samples=minimum_samples,
        macro_entry_prior=macro_entry_prior,
        normalized_component_prior=normalized_component_prior,
        applied_prior=applied_prior,
    )


def build_portion_correction_prior_resolver(
    database_path: str | Path,
    *,
    minimum_samples: int = 3,
) -> PortionPriorResolver:
    """Build a SQLite-backed portion prior resolver for meal analysis."""
    if minimum_samples <= 0:
        raise ValueError("minimum_samples must be greater than 0")

    normalized_db_path = _normalize_database_path(database_path)

    def _resolve(
        component_name: str,
        selected_macro_entry_id: str | None,
        selected_macro_entry_source: Literal["USDA", "PERSONAL"] | None,
    ) -> MealPortionCorrectionPrior | None:
        priors = fetch_portion_correction_priors(
            normalized_db_path,
            component_name=component_name,
            selected_macro_entry_id=selected_macro_entry_id,
            selected_macro_entry_source=selected_macro_entry_source,
            minimum_samples=minimum_samples,
        )
        applied_prior = priors.applied_prior
        if applied_prior is None:
            return None
        return MealPortionCorrectionPrior(
            strategy=applied_prior.strategy,
            reference=applied_prior.reference,
            sample_count=applied_prior.sample_count,
            grams_p50=applied_prior.grams_p50,
        )

    return _resolve


def fetch_meal_by_id(database_path: str | Path, meal_id: str) -> StoredMealEstimate | None:
    """Return one persisted meal by id, or None when it does not exist."""
    with _connect(_normalize_database_path(database_path)) as connection:
        _apply_migrations(connection)
        row = connection.execute(
            """
            SELECT
                meal_id,
                local_date,
                created_at,
                meal_estimate_json,
                best_kcal,
                best_kcal_method,
                best_protein_g,
                best_protein_g_method,
                best_carbs_g,
                best_carbs_g_method,
                best_fat_g,
                best_fat_g_method,
                best_sugar_g,
                best_sugar_g_method,
                best_sodium_mg,
                best_sodium_mg_method,
                best_fiber_g,
                best_fiber_g_method
            FROM meals
            WHERE meal_id = ?
            """,
            (meal_id,),
        ).fetchone()
    if row is None:
        return None

    return StoredMealEstimate(
        meal_id=str(row["meal_id"]),
        local_date=str(row["local_date"]),
        created_at=str(row["created_at"]),
        meal_estimate=MealEstimate.model_validate_json(str(row["meal_estimate_json"])),
        macro_best_estimate=_build_best_estimate_set_from_row(row),
    )


def fetch_daily_totals(database_path: str | Path, local_date: str) -> DailyLedgerTotals:
    """Aggregate all meals for one local date (YYYY-MM-DD)."""
    resolved_local_date = _validate_local_date(local_date)

    with _connect(_normalize_database_path(database_path)) as connection:
        _apply_migrations(connection)
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS meal_count,
                COALESCE(SUM(matched_component_count), 0) AS matched_component_count,
                COALESCE(SUM(unmatched_component_count), 0) AS unmatched_component_count,
                COALESCE(SUM(kcal_min), 0) AS kcal_min,
                COALESCE(SUM(kcal_max), 0) AS kcal_max,
                COALESCE(SUM(protein_g_min), 0) AS protein_g_min,
                COALESCE(SUM(protein_g_max), 0) AS protein_g_max,
                COALESCE(SUM(carbs_g_min), 0) AS carbs_g_min,
                COALESCE(SUM(carbs_g_max), 0) AS carbs_g_max,
                COALESCE(SUM(fat_g_min), 0) AS fat_g_min,
                COALESCE(SUM(fat_g_max), 0) AS fat_g_max,
                COALESCE(SUM(sugar_g_min), 0) AS sugar_g_min,
                COALESCE(SUM(sugar_g_max), 0) AS sugar_g_max,
                COALESCE(SUM(sodium_mg_min), 0) AS sodium_mg_min,
                COALESCE(SUM(sodium_mg_max), 0) AS sodium_mg_max,
                COALESCE(SUM(fiber_g_min), 0) AS fiber_g_min,
                COALESCE(SUM(fiber_g_max), 0) AS fiber_g_max
            FROM meals
            WHERE local_date = ?
            """,
            (resolved_local_date,),
        ).fetchone()

    totals = DailyLedgerTotals(
        local_date=resolved_local_date,
        meal_count=int(row["meal_count"]) if row is not None else 0,
        matched_component_count=int(row["matched_component_count"]) if row is not None else 0,
        unmatched_component_count=int(row["unmatched_component_count"]) if row is not None else 0,
        kcal=MacroRange(
            min=float(row["kcal_min"]) if row is not None else 0.0,
            max=float(row["kcal_max"]) if row is not None else 0.0,
        ),
        protein_g=MacroRange(
            min=float(row["protein_g_min"]) if row is not None else 0.0,
            max=float(row["protein_g_max"]) if row is not None else 0.0,
        ),
        carbs_g=MacroRange(
            min=float(row["carbs_g_min"]) if row is not None else 0.0,
            max=float(row["carbs_g_max"]) if row is not None else 0.0,
        ),
        fat_g=MacroRange(
            min=float(row["fat_g_min"]) if row is not None else 0.0,
            max=float(row["fat_g_max"]) if row is not None else 0.0,
        ),
        sugar_g=MacroRange(
            min=float(row["sugar_g_min"]) if row is not None else 0.0,
            max=float(row["sugar_g_max"]) if row is not None else 0.0,
        ),
        sodium_mg=MacroRange(
            min=float(row["sodium_mg_min"]) if row is not None else 0.0,
            max=float(row["sodium_mg_max"]) if row is not None else 0.0,
        ),
        fiber_g=MacroRange(
            min=float(row["fiber_g_min"]) if row is not None else 0.0,
            max=float(row["fiber_g_max"]) if row is not None else 0.0,
        ),
        macro_best_estimate=MacroBestEstimateSet(
            kcal=calculate_macro_best_estimate(
                MacroRange(
                    min=float(row["kcal_min"]) if row is not None else 0.0,
                    max=float(row["kcal_max"]) if row is not None else 0.0,
                )
            ),
            protein_g=calculate_macro_best_estimate(
                MacroRange(
                    min=float(row["protein_g_min"]) if row is not None else 0.0,
                    max=float(row["protein_g_max"]) if row is not None else 0.0,
                )
            ),
            carbs_g=calculate_macro_best_estimate(
                MacroRange(
                    min=float(row["carbs_g_min"]) if row is not None else 0.0,
                    max=float(row["carbs_g_max"]) if row is not None else 0.0,
                )
            ),
            fat_g=calculate_macro_best_estimate(
                MacroRange(
                    min=float(row["fat_g_min"]) if row is not None else 0.0,
                    max=float(row["fat_g_max"]) if row is not None else 0.0,
                )
            ),
            sugar_g=calculate_macro_best_estimate(
                MacroRange(
                    min=float(row["sugar_g_min"]) if row is not None else 0.0,
                    max=float(row["sugar_g_max"]) if row is not None else 0.0,
                )
            ),
            sodium_mg=calculate_macro_best_estimate(
                MacroRange(
                    min=float(row["sodium_mg_min"]) if row is not None else 0.0,
                    max=float(row["sodium_mg_max"]) if row is not None else 0.0,
                )
            ),
            fiber_g=calculate_macro_best_estimate(
                MacroRange(
                    min=float(row["fiber_g_min"]) if row is not None else 0.0,
                    max=float(row["fiber_g_max"]) if row is not None else 0.0,
                )
            ),
        ),
    )
    return totals


def insert_user_nutrition_ledger_entry(
    database_path: str | Path,
    *,
    user_id: str,
    meal_id: str,
    entry_kind: EntryKind,
    source: EntrySource = "deterministic",
    local_date: str | None = None,
    created_at: str | datetime | None = None,
    supersedes_entry_id: str | None = None,
    trace_id: str | None = None,
    note: str | None = None,
    kcal: float | None = None,
    protein_g: float | None = None,
    carbs_g: float | None = None,
    fat_g: float | None = None,
    sugar_g: float | None = None,
    sodium_mg: float | None = None,
    fiber_g: float | None = None,
    entry_id: str | None = None,
) -> str:
    """Append one user nutrition ledger row and return its entry_id."""
    resolved_user_id = _require_non_empty_text("user_id", user_id)
    resolved_meal_id = _require_non_empty_text("meal_id", meal_id)
    resolved_trace_id = _optional_non_empty_text(trace_id)
    resolved_note = _optional_non_empty_text(note)
    resolved_supersedes_entry_id = _optional_non_empty_text(supersedes_entry_id)
    resolved_local_date_input = _validate_local_date(local_date) if local_date is not None else None

    created_dt = _coerce_created_at(created_at)
    created_at_iso = created_dt.isoformat(timespec="seconds")
    resolved_entry_id = (
        _require_non_empty_text("entry_id", entry_id)
        if entry_id
        else str(uuid.uuid4())
    )

    nutrition = UserNutritionValues(
        kcal=kcal,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        sugar_g=sugar_g,
        sodium_mg=sodium_mg,
        fiber_g=fiber_g,
    )

    if resolved_supersedes_entry_id is not None and entry_kind != "corrected":
        raise ValueError("supersedes_entry_id requires entry_kind='corrected'")
    if resolved_supersedes_entry_id is None and entry_kind == "corrected":
        raise ValueError("entry_kind='corrected' requires supersedes_entry_id")

    resolved_local_date = resolved_local_date_input or created_dt.date().isoformat()

    with _connect(_normalize_database_path(database_path)) as connection:
        _apply_migrations(connection, target_version=_LATEST_SCHEMA_VERSION)

        if resolved_supersedes_entry_id is not None:
            superseded_row = connection.execute(
                """
                SELECT
                    candidate.user_id,
                    candidate.meal_id,
                    candidate.local_date,
                    CASE
                        WHEN EXISTS (
                            SELECT 1
                            FROM user_nutrition_ledger_entries AS superseding
                            WHERE superseding.supersedes_entry_id = candidate.entry_id
                        )
                        THEN 0
                        ELSE 1
                    END AS active
                FROM user_nutrition_ledger_entries AS candidate
                WHERE candidate.entry_id = ?
                """,
                (resolved_supersedes_entry_id,),
            ).fetchone()
            if superseded_row is None:
                raise ValueError(f"supersedes_entry_id not found: {resolved_supersedes_entry_id}")
            if str(superseded_row["user_id"]) != resolved_user_id:
                raise ValueError("supersedes_entry_id belongs to a different user_id")
            if int(superseded_row["active"]) != 1:
                raise ValueError(
                    f"supersedes_entry_id is not active: {resolved_supersedes_entry_id}"
                )
            superseded_meal_id = str(superseded_row["meal_id"])
            if superseded_meal_id != resolved_meal_id:
                raise ValueError("corrected entry meal_id must match superseded entry meal_id")
            superseded_local_date = str(superseded_row["local_date"])
            if resolved_local_date_input is None:
                resolved_local_date = superseded_local_date
            elif resolved_local_date_input != superseded_local_date:
                raise ValueError(
                    "corrected entry local_date must match superseded entry local_date"
                )

        try:
            connection.execute(
                """
                INSERT INTO user_nutrition_ledger_entries (
                    entry_id,
                    created_at,
                    local_date,
                    user_id,
                    meal_id,
                    entry_kind,
                    source,
                    supersedes_entry_id,
                    active,
                    trace_id,
                    note,
                    kcal,
                    protein_g,
                    carbs_g,
                    fat_g,
                    sugar_g,
                    sodium_mg,
                    fiber_g
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_entry_id,
                    created_at_iso,
                    resolved_local_date,
                    resolved_user_id,
                    resolved_meal_id,
                    entry_kind,
                    source,
                    resolved_supersedes_entry_id,
                    1,
                    resolved_trace_id,
                    resolved_note,
                    nutrition.kcal,
                    nutrition.protein_g,
                    nutrition.carbs_g,
                    nutrition.fat_g,
                    nutrition.sugar_g,
                    nutrition.sodium_mg,
                    nutrition.fiber_g,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"entry_id already exists: {resolved_entry_id}") from exc

    return resolved_entry_id


def fetch_user_meal_history(
    database_path: str | Path,
    *,
    user_id: str,
    local_date: str | None = None,
    include_inactive: bool = False,
    limit: int = 100,
    emitter: TraceEmitter | None = None,
) -> tuple[UserNutritionLedgerEntry, ...]:
    """Fetch user-scoped meal history rows with deterministic ordering."""
    resolved_user_id = _require_non_empty_text("user_id", user_id)
    resolved_local_date = _validate_local_date(local_date) if local_date is not None else None
    if limit <= 0:
        raise ValueError("limit must be greater than 0")

    where_clauses = ["user_id = ?"]
    params: list[object] = [resolved_user_id]
    if resolved_local_date is not None:
        where_clauses.append("local_date = ?")
        params.append(resolved_local_date)
    if not include_inactive:
        where_clauses.append(
            """
            NOT EXISTS (
                SELECT 1
                FROM user_nutrition_ledger_entries AS superseding
                WHERE superseding.supersedes_entry_id = entries.entry_id
            )
            """
        )
    params.append(limit)

    query = f"""
        SELECT
            entries.entry_id,
            entries.created_at,
            entries.local_date,
            entries.user_id,
            entries.meal_id,
            entries.entry_kind,
            entries.source,
            entries.supersedes_entry_id,
            CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM user_nutrition_ledger_entries AS superseding
                    WHERE superseding.supersedes_entry_id = entries.entry_id
                )
                THEN 0
                ELSE 1
            END AS active,
            entries.trace_id,
            entries.note,
            entries.kcal,
            entries.protein_g,
            entries.carbs_g,
            entries.fat_g,
            entries.sugar_g,
            entries.sodium_mg,
            entries.fiber_g
        FROM user_nutrition_ledger_entries AS entries
        WHERE {" AND ".join(where_clauses)}
        ORDER BY entries.created_at DESC, entries.entry_id DESC
        LIMIT ?
    """

    with _connect(_normalize_database_path(database_path)) as connection:
        _apply_migrations(connection, target_version=_LATEST_SCHEMA_VERSION)
        rows = connection.execute(query, params).fetchall()

    history = tuple(_build_user_nutrition_entry(row) for row in rows)
    _emit_ledger_to_history_event(
        emitter=emitter,
        user_id=resolved_user_id,
        local_date=resolved_local_date,
        event_name="ledger.to_history",
        payload={
            "history_entry_count": len(history),
            "include_inactive": include_inactive,
            "limit": limit,
        },
    )
    return history


def fetch_user_daily_totals(
    database_path: str | Path,
    *,
    user_id: str,
    local_date: str,
    emitter: TraceEmitter | None = None,
) -> UserDailyNutritionTotals:
    """Aggregate one user's daily totals from active deterministic ledger rows only."""
    resolved_user_id = _require_non_empty_text("user_id", user_id)
    resolved_local_date = _validate_local_date(local_date)

    with _connect(_normalize_database_path(database_path)) as connection:
        _apply_migrations(connection, target_version=_LATEST_SCHEMA_VERSION)
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS active_entry_count,
                COUNT(DISTINCT meal_id) AS meal_count,
                COALESCE(SUM(kcal), 0) AS kcal,
                COALESCE(SUM(protein_g), 0) AS protein_g,
                COALESCE(SUM(carbs_g), 0) AS carbs_g,
                COALESCE(SUM(fat_g), 0) AS fat_g,
                COALESCE(SUM(sugar_g), 0) AS sugar_g,
                COALESCE(SUM(sodium_mg), 0) AS sodium_mg,
                COALESCE(SUM(fiber_g), 0) AS fiber_g
            FROM user_nutrition_ledger_entries AS entries
            WHERE entries.user_id = ?
              AND entries.local_date = ?
              AND entries.source = 'deterministic'
              AND entries.entry_kind IN ('accepted', 'corrected')
              AND NOT EXISTS (
                  SELECT 1
                  FROM user_nutrition_ledger_entries AS superseding
                  WHERE superseding.supersedes_entry_id = entries.entry_id
              )
            """,
            (resolved_user_id, resolved_local_date),
        ).fetchone()

    totals = UserDailyNutritionTotals(
        user_id=resolved_user_id,
        local_date=resolved_local_date,
        meal_count=int(row["meal_count"]) if row is not None else 0,
        active_entry_count=int(row["active_entry_count"]) if row is not None else 0,
        kcal=float(row["kcal"]) if row is not None else 0.0,
        protein_g=float(row["protein_g"]) if row is not None else 0.0,
        carbs_g=float(row["carbs_g"]) if row is not None else 0.0,
        fat_g=float(row["fat_g"]) if row is not None else 0.0,
        sugar_g=float(row["sugar_g"]) if row is not None else 0.0,
        sodium_mg=float(row["sodium_mg"]) if row is not None else 0.0,
        fiber_g=float(row["fiber_g"]) if row is not None else 0.0,
    )
    _emit_ledger_to_history_event(
        emitter=emitter,
        user_id=resolved_user_id,
        local_date=resolved_local_date,
        event_name="ledger.daily_totals_prepared",
        payload={
            "active_entry_count": totals.active_entry_count,
            "meal_count": totals.meal_count,
            "kcal": totals.kcal,
            "protein_g": totals.protein_g,
            "carbs_g": totals.carbs_g,
            "fat_g": totals.fat_g,
            "sugar_g": totals.sugar_g,
            "sodium_mg": totals.sodium_mg,
            "fiber_g": totals.fiber_g,
        },
    )
    return totals


def prepare_healthkit_export(
    database_path: str | Path,
    *,
    user_id: str,
    local_date: str,
    emitter: TraceEmitter | None = None,
) -> HealthKitExportPreparation:
    """Prepare user/day deterministic ledger rows for HealthKit export."""
    resolved_user_id = _require_non_empty_text("user_id", user_id)
    resolved_local_date = _validate_local_date(local_date)

    with _connect(_normalize_database_path(database_path)) as connection:
        _apply_migrations(connection, target_version=_LATEST_SCHEMA_VERSION)
        rows = connection.execute(
            """
            SELECT
                entries.entry_id,
                entries.created_at,
                entries.local_date,
                entries.user_id,
                entries.meal_id,
                entries.entry_kind,
                entries.source,
                entries.supersedes_entry_id,
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM user_nutrition_ledger_entries AS superseding
                        WHERE superseding.supersedes_entry_id = entries.entry_id
                    )
                    THEN 0
                    ELSE 1
                END AS active,
                entries.trace_id,
                entries.note,
                entries.kcal,
                entries.protein_g,
                entries.carbs_g,
                entries.fat_g,
                entries.sugar_g,
                entries.sodium_mg,
                entries.fiber_g
            FROM user_nutrition_ledger_entries AS entries
            WHERE entries.user_id = ?
              AND entries.local_date = ?
              AND entries.source = 'deterministic'
              AND entries.entry_kind IN ('accepted', 'corrected')
              AND NOT EXISTS (
                  SELECT 1
                  FROM user_nutrition_ledger_entries AS superseding
                  WHERE superseding.supersedes_entry_id = entries.entry_id
              )
            ORDER BY entries.created_at ASC, entries.entry_id ASC
            """,
            (resolved_user_id, resolved_local_date),
        ).fetchall()

    ready_count = 0
    skipped_count = 0
    prepared_entries: list[HealthKitPreparedEntry] = []
    for row in rows:
        history_entry = _build_user_nutrition_entry(row)
        quantities: list[HealthKitPreparedQuantity] = []
        for metric_key, identifier, unit in _HEALTHKIT_QUANTITY_MAPPINGS:
            metric_value = getattr(history_entry.nutrition, metric_key)
            if metric_value is None:
                skipped_count += 1
                quantities.append(
                    HealthKitPreparedQuantity(
                        metric_key=metric_key,
                        healthkit_identifier=identifier,
                        unit=unit,
                        status="skipped",
                        value=None,
                        skip_reason="value_unavailable",
                    )
                )
            else:
                ready_count += 1
                quantities.append(
                    HealthKitPreparedQuantity(
                        metric_key=metric_key,
                        healthkit_identifier=identifier,
                        unit=unit,
                        status="ready",
                        value=metric_value,
                        skip_reason=None,
                    )
                )
        prepared_entries.append(
            HealthKitPreparedEntry(
                entry_id=history_entry.entry_id,
                meal_id=history_entry.meal_id,
                user_id=history_entry.user_id,
                local_date=history_entry.local_date,
                created_at=history_entry.created_at,
                quantities=quantities,
            )
        )

    preparation = HealthKitExportPreparation(
        user_id=resolved_user_id,
        local_date=resolved_local_date,
        prepared_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        entry_count=len(prepared_entries),
        entries=prepared_entries,
    )

    if emitter is not None:
        emit_stage_event(
            emitter,
            trace_id=f"healthkit-export:{resolved_user_id}:{resolved_local_date}",
            stage=_HEALTHKIT_PREP_TRACE_STAGE,
            event_name="healthkit.export_prepared",
            payload={
                "entry_count": preparation.entry_count,
                "ready_quantity_count": ready_count,
                "skipped_quantity_count": skipped_count,
                "supported_quantity_count": len(_HEALTHKIT_QUANTITY_MAPPINGS),
            },
        )

    return preparation


def export_ledger_backup(database_path: str | Path) -> dict[str, object]:
    """Export full ledger contents as a deterministic JSON-safe dictionary.

    Backup support is intentionally export-only for now; there is no public
    restore API until atomic restore semantics are defined and tested.
    """
    with _connect(_normalize_database_path(database_path)) as connection:
        _apply_migrations(connection, target_version=_LATEST_SCHEMA_VERSION)
        schema_rows = connection.execute(
            """
            SELECT version, applied_at
            FROM schema_migrations
            ORDER BY version ASC
            """
        ).fetchall()
        meal_rows = connection.execute(
            """
            SELECT
                meal_id,
                local_date,
                created_at,
                matched_component_count,
                unmatched_component_count,
                component_count,
                kcal_min,
                kcal_max,
                protein_g_min,
                protein_g_max,
                carbs_g_min,
                carbs_g_max,
                fat_g_min,
                fat_g_max,
                sugar_g_min,
                sugar_g_max,
                sodium_mg_min,
                sodium_mg_max,
                fiber_g_min,
                fiber_g_max,
                best_kcal,
                best_kcal_method,
                best_protein_g,
                best_protein_g_method,
                best_carbs_g,
                best_carbs_g_method,
                best_fat_g,
                best_fat_g_method,
                best_sugar_g,
                best_sugar_g_method,
                best_sodium_mg,
                best_sodium_mg_method,
                best_fiber_g,
                best_fiber_g_method,
                source_traces_json,
                meal_estimate_json
            FROM meals
            ORDER BY local_date ASC, created_at ASC, meal_id ASC
            """
        ).fetchall()
        component_rows = connection.execute(
            """
            SELECT
                meal_id,
                component_index,
                component_name,
                component_confidence,
                portion_hint,
                status,
                top_candidates_json,
                selected_macro_entry_id,
                selected_macro_entry_name,
                selected_macro_entry_source,
                selected_match_score,
                portion_grams_min,
                portion_grams_max,
                portion_confidence,
                portion_source,
                portion_reason,
                unmatched_reason,
                kcal_min,
                kcal_max,
                protein_g_min,
                protein_g_max,
                carbs_g_min,
                carbs_g_max,
                fat_g_min,
                fat_g_max,
                sugar_g_min,
                sugar_g_max,
                sodium_mg_min,
                sodium_mg_max,
                fiber_g_min,
                fiber_g_max,
                best_kcal,
                best_kcal_method,
                best_protein_g,
                best_protein_g_method,
                best_carbs_g,
                best_carbs_g_method,
                best_fat_g,
                best_fat_g_method,
                best_sugar_g,
                best_sugar_g_method,
                best_sodium_mg,
                best_sodium_mg_method,
                best_fiber_g,
                best_fiber_g_method,
                source_trace_json,
                component_estimate_json
            FROM meal_component_estimates
            ORDER BY meal_id ASC, component_index ASC
            """
        ).fetchall()
        correction_rows = connection.execute(
            """
            SELECT
                correction_id,
                created_at,
                component_name,
                component_name_normalized,
                selected_macro_entry_id,
                selected_macro_entry_source,
                original_portion_grams_p10,
                original_portion_grams_p50,
                original_portion_grams_p90,
                corrected_grams,
                corrected_serving_label,
                corrected_grams_p50,
                note
            FROM portion_corrections
            ORDER BY created_at ASC, correction_id ASC
            """
        ).fetchall()
        user_nutrition_rows = connection.execute(
            """
            SELECT
                entries.entry_id,
                entries.created_at,
                entries.local_date,
                entries.user_id,
                entries.meal_id,
                entries.entry_kind,
                entries.source,
                entries.supersedes_entry_id,
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM user_nutrition_ledger_entries AS superseding
                        WHERE superseding.supersedes_entry_id = entries.entry_id
                    )
                    THEN 0
                    ELSE 1
                END AS active,
                entries.trace_id,
                entries.note,
                entries.kcal,
                entries.protein_g,
                entries.carbs_g,
                entries.fat_g,
                entries.sugar_g,
                entries.sodium_mg,
                entries.fiber_g
            FROM user_nutrition_ledger_entries AS entries
            ORDER BY
                entries.user_id ASC,
                entries.local_date ASC,
                entries.created_at ASC,
                entries.entry_id ASC
            """
        ).fetchall()

    ledger_schema_version = max((int(row["version"]) for row in schema_rows), default=0)

    components_by_meal: dict[str, list[dict[str, object]]] = {}
    for row in component_rows:
        meal_id = str(row["meal_id"])
        components_by_meal.setdefault(meal_id, []).append(_build_component_backup_row(row))

    meals_payload: list[dict[str, object]] = []
    for row in meal_rows:
        meal_id = str(row["meal_id"])
        meals_payload.append(
            _build_meal_backup_row(
                row=row,
                components=components_by_meal.get(meal_id, []),
            )
        )

    portion_corrections_payload = [
        _build_portion_correction_record(row).model_dump(mode="json")
        for row in correction_rows
    ]
    user_nutrition_payload = [
        _build_user_nutrition_entry(row).model_dump(mode="json") for row in user_nutrition_rows
    ]

    return {
        "format": _EXPORT_FORMAT,
        "export_schema_version": _EXPORT_SCHEMA_VERSION,
        "ledger_schema_version": ledger_schema_version,
        "schema_migrations": [
            {
                "version": int(row["version"]),
                "applied_at": str(row["applied_at"]),
            }
            for row in schema_rows
        ],
        "portion_correction_count": len(portion_corrections_payload),
        "portion_corrections": portion_corrections_payload,
        "user_nutrition_ledger_entry_count": len(user_nutrition_payload),
        "user_nutrition_ledger_entries": user_nutrition_payload,
        "meal_count": len(meals_payload),
        "meals": meals_payload,
    }


def _insert_component_row(
    *,
    connection: sqlite3.Connection,
    meal_id: str,
    component_index: int,
    component: MealComponentEstimate,
) -> None:
    macro_interval = component.macro_interval
    component_best = (
        calculate_food_macro_best_estimate(macro_interval) if macro_interval is not None else None
    )
    top_candidates_payload = [
        candidate.model_dump(mode="json") for candidate in component.top_candidates
    ]

    connection.execute(
        """
        INSERT INTO meal_component_estimates (
            meal_id,
            component_index,
            component_name,
            component_confidence,
            portion_hint,
            status,
            top_candidates_json,
            selected_macro_entry_id,
            selected_macro_entry_name,
            selected_macro_entry_source,
            selected_match_score,
            portion_grams_min,
            portion_grams_max,
            portion_confidence,
            portion_source,
            portion_reason,
            unmatched_reason,
            kcal_min,
            kcal_max,
            protein_g_min,
            protein_g_max,
            carbs_g_min,
            carbs_g_max,
            fat_g_min,
            fat_g_max,
            sugar_g_min,
            sugar_g_max,
            sodium_mg_min,
            sodium_mg_max,
            fiber_g_min,
            fiber_g_max,
            best_kcal,
            best_kcal_method,
            best_protein_g,
            best_protein_g_method,
            best_carbs_g,
            best_carbs_g_method,
            best_fat_g,
            best_fat_g_method,
            best_sugar_g,
            best_sugar_g_method,
            best_sodium_mg,
            best_sodium_mg_method,
            best_fiber_g,
            best_fiber_g_method,
            source_trace_json,
            component_estimate_json
        ) VALUES (
            :meal_id,
            :component_index,
            :component_name,
            :component_confidence,
            :portion_hint,
            :status,
            :top_candidates_json,
            :selected_macro_entry_id,
            :selected_macro_entry_name,
            :selected_macro_entry_source,
            :selected_match_score,
            :portion_grams_min,
            :portion_grams_max,
            :portion_confidence,
            :portion_source,
            :portion_reason,
            :unmatched_reason,
            :kcal_min,
            :kcal_max,
            :protein_g_min,
            :protein_g_max,
            :carbs_g_min,
            :carbs_g_max,
            :fat_g_min,
            :fat_g_max,
            :sugar_g_min,
            :sugar_g_max,
            :sodium_mg_min,
            :sodium_mg_max,
            :fiber_g_min,
            :fiber_g_max,
            :best_kcal,
            :best_kcal_method,
            :best_protein_g,
            :best_protein_g_method,
            :best_carbs_g,
            :best_carbs_g_method,
            :best_fat_g,
            :best_fat_g_method,
            :best_sugar_g,
            :best_sugar_g_method,
            :best_sodium_mg,
            :best_sodium_mg_method,
            :best_fiber_g,
            :best_fiber_g_method,
            :source_trace_json,
            :component_estimate_json
        )
        """,
        {
            "meal_id": meal_id,
            "component_index": component_index,
            "component_name": component.component_name,
            "component_confidence": component.component_confidence,
            "portion_hint": component.portion_hint,
            "status": component.status,
            "top_candidates_json": _json_dumps(top_candidates_payload),
            "selected_macro_entry_id": component.selected_macro_entry_id,
            "selected_macro_entry_name": component.selected_macro_entry_name,
            "selected_macro_entry_source": component.selected_macro_entry_source,
            "selected_match_score": component.selected_match_score,
            "portion_grams_min": component.portion_range.grams_min,
            "portion_grams_max": component.portion_range.grams_max,
            "portion_confidence": component.portion_range.confidence,
            "portion_source": component.portion_range.source,
            "portion_reason": component.portion_range.reason,
            "unmatched_reason": component.unmatched_reason,
            "kcal_min": macro_interval.kcal.min if macro_interval is not None else None,
            "kcal_max": macro_interval.kcal.max if macro_interval is not None else None,
            "protein_g_min": (
                macro_interval.protein_g.min if macro_interval is not None else None
            ),
            "protein_g_max": (
                macro_interval.protein_g.max if macro_interval is not None else None
            ),
            "carbs_g_min": macro_interval.carbs_g.min if macro_interval is not None else None,
            "carbs_g_max": macro_interval.carbs_g.max if macro_interval is not None else None,
            "fat_g_min": macro_interval.fat_g.min if macro_interval is not None else None,
            "fat_g_max": macro_interval.fat_g.max if macro_interval is not None else None,
            "sugar_g_min": macro_interval.sugar_g.min if macro_interval is not None else None,
            "sugar_g_max": macro_interval.sugar_g.max if macro_interval is not None else None,
            "sodium_mg_min": (
                macro_interval.sodium_mg.min if macro_interval is not None else None
            ),
            "sodium_mg_max": (
                macro_interval.sodium_mg.max if macro_interval is not None else None
            ),
            "fiber_g_min": macro_interval.fiber_g.min if macro_interval is not None else None,
            "fiber_g_max": macro_interval.fiber_g.max if macro_interval is not None else None,
            "best_kcal": component_best.kcal.value if component_best is not None else None,
            "best_kcal_method": (
                component_best.kcal.method if component_best is not None else None
            ),
            "best_protein_g": (
                component_best.protein_g.value if component_best is not None else None
            ),
            "best_protein_g_method": (
                component_best.protein_g.method if component_best is not None else None
            ),
            "best_carbs_g": (
                component_best.carbs_g.value if component_best is not None else None
            ),
            "best_carbs_g_method": (
                component_best.carbs_g.method if component_best is not None else None
            ),
            "best_fat_g": component_best.fat_g.value if component_best is not None else None,
            "best_fat_g_method": (
                component_best.fat_g.method if component_best is not None else None
            ),
            "best_sugar_g": (
                component_best.sugar_g.value if component_best is not None else None
            ),
            "best_sugar_g_method": (
                component_best.sugar_g.method if component_best is not None else None
            ),
            "best_sodium_mg": (
                component_best.sodium_mg.value if component_best is not None else None
            ),
            "best_sodium_mg_method": (
                component_best.sodium_mg.method if component_best is not None else None
            ),
            "best_fiber_g": (
                component_best.fiber_g.value if component_best is not None else None
            ),
            "best_fiber_g_method": (
                component_best.fiber_g.method if component_best is not None else None
            ),
            "source_trace_json": (
                _json_dumps(macro_interval.source_trace.model_dump(mode="json"))
                if macro_interval is not None
                else None
            ),
            "component_estimate_json": _json_dumps(component.model_dump(mode="json")),
        },
    )


def _apply_migrations(
    connection: sqlite3.Connection,
    *,
    target_version: int | None = None,
) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    resolved_target_version = _LATEST_SCHEMA_VERSION if target_version is None else target_version
    if resolved_target_version <= 0:
        return

    applied_versions = {
        int(row["version"]) for row in connection.execute("SELECT version FROM schema_migrations")
    }

    for migration in _MIGRATIONS:
        if migration.version > resolved_target_version:
            break
        if migration.version in applied_versions:
            continue
        connection.executescript(migration.sql)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (migration.version, datetime.now().astimezone().isoformat(timespec="seconds")),
        )


def _build_best_estimate_set_from_row(row: sqlite3.Row) -> MacroBestEstimateSet:
    return MacroBestEstimateSet(
        kcal=MacroBestEstimate(
            value=float(row["best_kcal"]),
            method=str(row["best_kcal_method"]),
        ),
        protein_g=MacroBestEstimate(
            value=float(row["best_protein_g"]),
            method=str(row["best_protein_g_method"]),
        ),
        carbs_g=MacroBestEstimate(
            value=float(row["best_carbs_g"]),
            method=str(row["best_carbs_g_method"]),
        ),
        fat_g=MacroBestEstimate(
            value=float(row["best_fat_g"]),
            method=str(row["best_fat_g_method"]),
        ),
        sugar_g=MacroBestEstimate(
            value=float(row["best_sugar_g"]),
            method=str(row["best_sugar_g_method"]),
        ),
        sodium_mg=MacroBestEstimate(
            value=float(row["best_sodium_mg"]),
            method=str(row["best_sodium_mg_method"]),
        ),
        fiber_g=MacroBestEstimate(
            value=float(row["best_fiber_g"]),
            method=str(row["best_fiber_g_method"]),
        ),
    )


def _build_meal_backup_row(
    *,
    row: sqlite3.Row,
    components: list[dict[str, object]],
) -> dict[str, object]:
    meal_estimate_payload = _json_loads(str(row["meal_estimate_json"]))
    trace_versions_payload: object | None = None
    if isinstance(meal_estimate_payload, dict):
        trace_versions_payload = meal_estimate_payload.get("trace_versions")

    return {
        "meal_id": str(row["meal_id"]),
        "local_date": str(row["local_date"]),
        "created_at": str(row["created_at"]),
        "matched_component_count": int(row["matched_component_count"]),
        "unmatched_component_count": int(row["unmatched_component_count"]),
        "component_count": int(row["component_count"]),
        "macro_ranges": {
            "kcal": {
                "min": float(row["kcal_min"]),
                "max": float(row["kcal_max"]),
            },
            "protein_g": {
                "min": float(row["protein_g_min"]),
                "max": float(row["protein_g_max"]),
            },
            "carbs_g": {
                "min": float(row["carbs_g_min"]),
                "max": float(row["carbs_g_max"]),
            },
            "fat_g": {
                "min": float(row["fat_g_min"]),
                "max": float(row["fat_g_max"]),
            },
            "sugar_g": {
                "min": float(row["sugar_g_min"]),
                "max": float(row["sugar_g_max"]),
            },
            "sodium_mg": {
                "min": float(row["sodium_mg_min"]),
                "max": float(row["sodium_mg_max"]),
            },
            "fiber_g": {
                "min": float(row["fiber_g_min"]),
                "max": float(row["fiber_g_max"]),
            },
        },
        "macro_best_estimate": {
            "kcal": {
                "value": float(row["best_kcal"]),
                "method": str(row["best_kcal_method"]),
            },
            "protein_g": {
                "value": float(row["best_protein_g"]),
                "method": str(row["best_protein_g_method"]),
            },
            "carbs_g": {
                "value": float(row["best_carbs_g"]),
                "method": str(row["best_carbs_g_method"]),
            },
            "fat_g": {
                "value": float(row["best_fat_g"]),
                "method": str(row["best_fat_g_method"]),
            },
            "sugar_g": {
                "value": float(row["best_sugar_g"]),
                "method": str(row["best_sugar_g_method"]),
            },
            "sodium_mg": {
                "value": float(row["best_sodium_mg"]),
                "method": str(row["best_sodium_mg_method"]),
            },
            "fiber_g": {
                "value": float(row["best_fiber_g"]),
                "method": str(row["best_fiber_g_method"]),
            },
        },
        "source_traces": _json_loads(str(row["source_traces_json"])),
        "meal_estimate": meal_estimate_payload,
        "trace_versions": trace_versions_payload,
        "components": components,
    }


def _build_component_backup_row(row: sqlite3.Row) -> dict[str, object]:
    selected_macro_entry: dict[str, object] | None
    if row["selected_macro_entry_id"] is None:
        selected_macro_entry = None
    else:
        selected_macro_entry = {
            "id": str(row["selected_macro_entry_id"]),
            "name": str(row["selected_macro_entry_name"]),
            "source": str(row["selected_macro_entry_source"]),
            "match_score": float(row["selected_match_score"]),
        }

    macro_ranges: dict[str, object] | None
    macro_best_estimate: dict[str, object] | None
    if row["kcal_min"] is None:
        macro_ranges = None
        macro_best_estimate = None
    else:
        macro_ranges = {
            "kcal": {
                "min": float(row["kcal_min"]),
                "max": float(row["kcal_max"]),
            },
            "protein_g": {
                "min": float(row["protein_g_min"]),
                "max": float(row["protein_g_max"]),
            },
            "carbs_g": {
                "min": float(row["carbs_g_min"]),
                "max": float(row["carbs_g_max"]),
            },
            "fat_g": {
                "min": float(row["fat_g_min"]),
                "max": float(row["fat_g_max"]),
            },
            "sugar_g": {
                "min": float(row["sugar_g_min"]),
                "max": float(row["sugar_g_max"]),
            },
            "sodium_mg": {
                "min": float(row["sodium_mg_min"]),
                "max": float(row["sodium_mg_max"]),
            },
            "fiber_g": {
                "min": float(row["fiber_g_min"]),
                "max": float(row["fiber_g_max"]),
            },
        }
        macro_best_estimate = {
            "kcal": {
                "value": float(row["best_kcal"]),
                "method": str(row["best_kcal_method"]),
            },
            "protein_g": {
                "value": float(row["best_protein_g"]),
                "method": str(row["best_protein_g_method"]),
            },
            "carbs_g": {
                "value": float(row["best_carbs_g"]),
                "method": str(row["best_carbs_g_method"]),
            },
            "fat_g": {
                "value": float(row["best_fat_g"]),
                "method": str(row["best_fat_g_method"]),
            },
            "sugar_g": {
                "value": float(row["best_sugar_g"]),
                "method": str(row["best_sugar_g_method"]),
            },
            "sodium_mg": {
                "value": float(row["best_sodium_mg"]),
                "method": str(row["best_sodium_mg_method"]),
            },
            "fiber_g": {
                "value": float(row["best_fiber_g"]),
                "method": str(row["best_fiber_g_method"]),
            },
        }

    return {
        "component_index": int(row["component_index"]),
        "component_name": str(row["component_name"]),
        "component_confidence": float(row["component_confidence"]),
        "portion_hint": str(row["portion_hint"]) if row["portion_hint"] is not None else None,
        "status": str(row["status"]),
        "top_candidates": _json_loads(str(row["top_candidates_json"])),
        "selected_macro_entry": selected_macro_entry,
        "portion_range": {
            "grams_min": float(row["portion_grams_min"]),
            "grams_max": float(row["portion_grams_max"]),
            "confidence": float(row["portion_confidence"]),
            "source": str(row["portion_source"]),
            "reason": str(row["portion_reason"]),
        },
        "unmatched_reason": (
            str(row["unmatched_reason"]) if row["unmatched_reason"] is not None else None
        ),
        "macro_ranges": macro_ranges,
        "macro_best_estimate": macro_best_estimate,
        "source_trace": (
            _json_loads(str(row["source_trace_json"]))
            if row["source_trace_json"] is not None
            else None
        ),
        "component_estimate": _json_loads(str(row["component_estimate_json"])),
    }


def _build_portion_correction_record(row: sqlite3.Row) -> PortionCorrectionRecord:
    return PortionCorrectionRecord(
        correction_id=str(row["correction_id"]),
        created_at=str(row["created_at"]),
        component_name=str(row["component_name"]),
        component_name_normalized=str(row["component_name_normalized"]),
        selected_macro_entry_id=(
            str(row["selected_macro_entry_id"])
            if row["selected_macro_entry_id"] is not None
            else None
        ),
        selected_macro_entry_source=(
            str(row["selected_macro_entry_source"])
            if row["selected_macro_entry_source"] is not None
            else None
        ),
        original_portion_grams_p10=float(row["original_portion_grams_p10"]),
        original_portion_grams_p50=float(row["original_portion_grams_p50"]),
        original_portion_grams_p90=float(row["original_portion_grams_p90"]),
        corrected_grams=(
            float(row["corrected_grams"]) if row["corrected_grams"] is not None else None
        ),
        corrected_serving_label=(
            str(row["corrected_serving_label"])
            if row["corrected_serving_label"] is not None
            else None
        ),
        corrected_grams_p50=float(row["corrected_grams_p50"]),
        note=str(row["note"]) if row["note"] is not None else None,
    )


def _build_user_nutrition_entry(row: sqlite3.Row) -> UserNutritionLedgerEntry:
    return UserNutritionLedgerEntry(
        entry_id=str(row["entry_id"]),
        created_at=str(row["created_at"]),
        local_date=str(row["local_date"]),
        user_id=str(row["user_id"]),
        meal_id=str(row["meal_id"]),
        entry_kind=str(row["entry_kind"]),
        source=str(row["source"]),
        supersedes_entry_id=(
            str(row["supersedes_entry_id"])
            if row["supersedes_entry_id"] is not None
            else None
        ),
        active=bool(int(row["active"])),
        trace_id=str(row["trace_id"]) if row["trace_id"] is not None else None,
        note=str(row["note"]) if row["note"] is not None else None,
        nutrition=UserNutritionValues(
            kcal=float(row["kcal"]) if row["kcal"] is not None else None,
            protein_g=float(row["protein_g"]) if row["protein_g"] is not None else None,
            carbs_g=float(row["carbs_g"]) if row["carbs_g"] is not None else None,
            fat_g=float(row["fat_g"]) if row["fat_g"] is not None else None,
            sugar_g=float(row["sugar_g"]) if row["sugar_g"] is not None else None,
            sodium_mg=float(row["sodium_mg"]) if row["sodium_mg"] is not None else None,
            fiber_g=float(row["fiber_g"]) if row["fiber_g"] is not None else None,
        ),
    )


def _build_prior_from_row(
    *,
    strategy: Literal["macro_entry", "normalized_component"],
    reference: str,
    row: sqlite3.Row | None,
) -> PortionCorrectionPrior | None:
    if row is None:
        return None
    sample_count = int(row["sample_count"])
    grams_p50 = row["grams_p50"]
    if sample_count <= 0 or grams_p50 is None:
        return None
    return PortionCorrectionPrior(
        strategy=strategy,
        reference=reference,
        sample_count=sample_count,
        grams_p50=_round_to_tenth(float(grams_p50)),
    )


def _normalize_database_path(database_path: str | Path) -> str:
    return str(database_path)


def _require_non_empty_text(name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    return normalized


def _optional_non_empty_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _coerce_created_at(value: str | datetime | None) -> datetime:
    if value is None:
        return datetime.now().astimezone()

    if isinstance(value, datetime):
        dt_value = value
    else:
        try:
            dt_value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("created_at must be an ISO timestamp string") from exc

    if dt_value.tzinfo is None:
        return dt_value.astimezone()
    return dt_value


def _is_existing_meal_idempotent(
    *,
    connection: sqlite3.Connection,
    meal_id: str,
    local_date: str,
    created_at: str,
    matched_component_count: int,
    unmatched_component_count: int,
    component_count: int,
    macro_interval: MealMacroInterval,
    meal_macro_best: MacroBestEstimateSet,
    source_traces_json: str,
    meal_estimate_json: str,
) -> bool:
    row = connection.execute(
        """
        SELECT
            local_date,
            created_at,
            matched_component_count,
            unmatched_component_count,
            component_count,
            kcal_min,
            kcal_max,
            protein_g_min,
            protein_g_max,
            carbs_g_min,
            carbs_g_max,
            fat_g_min,
            fat_g_max,
            sugar_g_min,
            sugar_g_max,
            sodium_mg_min,
            sodium_mg_max,
            fiber_g_min,
            fiber_g_max,
            best_kcal,
            best_kcal_method,
            best_protein_g,
            best_protein_g_method,
            best_carbs_g,
            best_carbs_g_method,
            best_fat_g,
            best_fat_g_method,
            best_sugar_g,
            best_sugar_g_method,
            best_sodium_mg,
            best_sodium_mg_method,
            best_fiber_g,
            best_fiber_g_method,
            source_traces_json,
            meal_estimate_json
        FROM meals
        WHERE meal_id = ?
        """,
        (meal_id,),
    ).fetchone()
    if row is None:
        return False

    return (
        str(row["local_date"]) == local_date
        and str(row["created_at"]) == created_at
        and int(row["matched_component_count"]) == matched_component_count
        and int(row["unmatched_component_count"]) == unmatched_component_count
        and int(row["component_count"]) == component_count
        and float(row["kcal_min"]) == macro_interval.kcal.min
        and float(row["kcal_max"]) == macro_interval.kcal.max
        and float(row["protein_g_min"]) == macro_interval.protein_g.min
        and float(row["protein_g_max"]) == macro_interval.protein_g.max
        and float(row["carbs_g_min"]) == macro_interval.carbs_g.min
        and float(row["carbs_g_max"]) == macro_interval.carbs_g.max
        and float(row["fat_g_min"]) == macro_interval.fat_g.min
        and float(row["fat_g_max"]) == macro_interval.fat_g.max
        and float(row["sugar_g_min"]) == macro_interval.sugar_g.min
        and float(row["sugar_g_max"]) == macro_interval.sugar_g.max
        and float(row["sodium_mg_min"]) == macro_interval.sodium_mg.min
        and float(row["sodium_mg_max"]) == macro_interval.sodium_mg.max
        and float(row["fiber_g_min"]) == macro_interval.fiber_g.min
        and float(row["fiber_g_max"]) == macro_interval.fiber_g.max
        and float(row["best_kcal"]) == meal_macro_best.kcal.value
        and str(row["best_kcal_method"]) == meal_macro_best.kcal.method
        and float(row["best_protein_g"]) == meal_macro_best.protein_g.value
        and str(row["best_protein_g_method"]) == meal_macro_best.protein_g.method
        and float(row["best_carbs_g"]) == meal_macro_best.carbs_g.value
        and str(row["best_carbs_g_method"]) == meal_macro_best.carbs_g.method
        and float(row["best_fat_g"]) == meal_macro_best.fat_g.value
        and str(row["best_fat_g_method"]) == meal_macro_best.fat_g.method
        and float(row["best_sugar_g"]) == meal_macro_best.sugar_g.value
        and str(row["best_sugar_g_method"]) == meal_macro_best.sugar_g.method
        and float(row["best_sodium_mg"]) == meal_macro_best.sodium_mg.value
        and str(row["best_sodium_mg_method"]) == meal_macro_best.sodium_mg.method
        and float(row["best_fiber_g"]) == meal_macro_best.fiber_g.value
        and str(row["best_fiber_g_method"]) == meal_macro_best.fiber_g.method
        and str(row["source_traces_json"]) == source_traces_json
        and str(row["meal_estimate_json"]) == meal_estimate_json
    )


def _validate_local_date(local_date_value: str) -> str:
    try:
        parsed = date.fromisoformat(local_date_value)
    except ValueError as exc:
        raise ValueError("local_date must be YYYY-MM-DD") from exc
    return parsed.isoformat()


def _emit_ledger_to_history_event(
    *,
    emitter: TraceEmitter | None,
    user_id: str,
    local_date: str | None,
    event_name: str,
    payload: dict[str, object],
) -> None:
    if emitter is None:
        return
    trace_scope = local_date if local_date is not None else "all-days"
    emit_stage_event(
        emitter,
        trace_id=f"ledger-history:{user_id}:{trace_scope}",
        stage=_USER_HISTORY_TRACE_STAGE,
        event_name=event_name,
        payload={
            "user_id": user_id,
            "local_date": local_date,
            **payload,
        },
    )


def _normalize_component_name(value: str) -> str:
    if not isinstance(value, str):
        return ""
    normalized = re.sub(r"[^a-z0-9]+", " ", value.casefold())
    return " ".join(normalized.split())


def _resolve_corrected_grams_p50(
    *,
    component_name: str,
    corrected_grams: float | None,
    corrected_serving_label: str | None,
) -> float:
    if corrected_grams is not None:
        if corrected_grams <= 0:
            raise ValueError("corrected_grams must be greater than 0")
        return _round_to_tenth(corrected_grams)

    if corrected_serving_label is None or not corrected_serving_label.strip():
        raise ValueError("either corrected_grams or corrected_serving_label is required")

    parsed = parse_portion_range(
        component_name=component_name,
        portion_hint=corrected_serving_label,
    )
    if parsed.source == "fallback_default":
        raise ValueError("corrected_serving_label could not be parsed into a reliable gram prior")
    return _round_to_tenth(parsed.grams_p50)


def _round_to_tenth(value: float) -> float:
    return round(value, 1)


def _json_dumps(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _json_loads(payload: str) -> object:
    return json.loads(payload)


def _connect(database_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


__all__ = [
    "DailyLedgerTotals",
    "HealthKitExportPreparation",
    "HealthKitPreparedEntry",
    "HealthKitPreparedQuantity",
    "PortionCorrectionPrior",
    "PortionCorrectionPriors",
    "PortionCorrectionRecord",
    "StoredMealEstimate",
    "UserDailyNutritionTotals",
    "UserNutritionLedgerEntry",
    "UserNutritionValues",
    "build_portion_correction_prior_resolver",
    "export_ledger_backup",
    "fetch_daily_totals",
    "fetch_meal_by_id",
    "fetch_portion_correction_by_id",
    "fetch_portion_correction_priors",
    "fetch_user_daily_totals",
    "fetch_user_meal_history",
    "initialize_sqlite_ledger",
    "insert_meal_estimate",
    "insert_portion_correction",
    "insert_user_nutrition_ledger_entry",
    "prepare_healthkit_export",
]
