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
from services.nutrition import parse_portion_range
from services.trace import LEDGER_SCHEMA_VERSION


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
    macro_best_estimate: MacroBestEstimateSet


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
)

_EXPORT_FORMAT = "macroagent.sqlite_ledger_backup"
_EXPORT_SCHEMA_VERSION = LEDGER_SCHEMA_VERSION
_BASE_SCHEMA_VERSION = _MIGRATIONS[0].version if _MIGRATIONS else 0
_LATEST_SCHEMA_VERSION = _MIGRATIONS[-1].version if _MIGRATIONS else 0


def initialize_sqlite_ledger(database_path: str | Path) -> None:
    """Create or migrate the local SQLite ledger schema."""
    db_target = _normalize_database_path(database_path)
    if db_target != ":memory:":
        Path(db_target).parent.mkdir(parents=True, exist_ok=True)

    with _connect(db_target) as connection:
        _apply_migrations(connection, target_version=_BASE_SCHEMA_VERSION)


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
                    best_kcal,
                    best_kcal_method,
                    best_protein_g,
                    best_protein_g_method,
                    best_carbs_g,
                    best_carbs_g_method,
                    best_fat_g,
                    best_fat_g_method,
                    source_traces_json,
                    meal_estimate_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_meal_id,
                    resolved_local_date,
                    created_at_iso,
                    meal_estimate.matched_component_count,
                    meal_estimate.unmatched_component_count,
                    len(meal_estimate.component_estimates),
                    macro_interval.kcal.min,
                    macro_interval.kcal.max,
                    macro_interval.protein_g.min,
                    macro_interval.protein_g.max,
                    macro_interval.carbs_g.min,
                    macro_interval.carbs_g.max,
                    macro_interval.fat_g.min,
                    macro_interval.fat_g.max,
                    meal_macro_best.kcal.value,
                    meal_macro_best.kcal.method,
                    meal_macro_best.protein_g.value,
                    meal_macro_best.protein_g.method,
                    meal_macro_best.carbs_g.value,
                    meal_macro_best.carbs_g.method,
                    meal_macro_best.fat_g.value,
                    meal_macro_best.fat_g.method,
                    source_traces_json,
                    meal_estimate_json,
                ),
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
                best_fat_g_method
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
                COALESCE(SUM(fat_g_max), 0) AS fat_g_max
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
        ),
    )
    return totals


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
                best_kcal,
                best_kcal_method,
                best_protein_g,
                best_protein_g_method,
                best_carbs_g,
                best_carbs_g_method,
                best_fat_g,
                best_fat_g_method,
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
                best_kcal,
                best_kcal_method,
                best_protein_g,
                best_protein_g_method,
                best_carbs_g,
                best_carbs_g_method,
                best_fat_g,
                best_fat_g_method,
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
            best_kcal,
            best_kcal_method,
            best_protein_g,
            best_protein_g_method,
            best_carbs_g,
            best_carbs_g_method,
            best_fat_g,
            best_fat_g_method,
            source_trace_json,
            component_estimate_json
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?
        )
        """,
        (
            meal_id,
            component_index,
            component.component_name,
            component.component_confidence,
            component.portion_hint,
            component.status,
            _json_dumps(top_candidates_payload),
            component.selected_macro_entry_id,
            component.selected_macro_entry_name,
            component.selected_macro_entry_source,
            component.selected_match_score,
            component.portion_range.grams_min,
            component.portion_range.grams_max,
            component.portion_range.confidence,
            component.portion_range.source,
            component.portion_range.reason,
            component.unmatched_reason,
            macro_interval.kcal.min if macro_interval is not None else None,
            macro_interval.kcal.max if macro_interval is not None else None,
            macro_interval.protein_g.min if macro_interval is not None else None,
            macro_interval.protein_g.max if macro_interval is not None else None,
            macro_interval.carbs_g.min if macro_interval is not None else None,
            macro_interval.carbs_g.max if macro_interval is not None else None,
            macro_interval.fat_g.min if macro_interval is not None else None,
            macro_interval.fat_g.max if macro_interval is not None else None,
            component_best.kcal.value if component_best is not None else None,
            component_best.kcal.method if component_best is not None else None,
            component_best.protein_g.value if component_best is not None else None,
            component_best.protein_g.method if component_best is not None else None,
            component_best.carbs_g.value if component_best is not None else None,
            component_best.carbs_g.method if component_best is not None else None,
            component_best.fat_g.value if component_best is not None else None,
            component_best.fat_g.method if component_best is not None else None,
            _json_dumps(macro_interval.source_trace.model_dump(mode="json"))
            if macro_interval is not None
            else None,
            _json_dumps(component.model_dump(mode="json")),
        ),
    )


def _apply_migrations(
    connection: sqlite3.Connection,
    *,
    target_version: int = _BASE_SCHEMA_VERSION,
) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    if target_version <= 0:
        return

    applied_versions = {
        int(row["version"]) for row in connection.execute("SELECT version FROM schema_migrations")
    }

    for migration in _MIGRATIONS:
        if migration.version > target_version:
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
            best_kcal,
            best_kcal_method,
            best_protein_g,
            best_protein_g_method,
            best_carbs_g,
            best_carbs_g_method,
            best_fat_g,
            best_fat_g_method,
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
        and float(row["best_kcal"]) == meal_macro_best.kcal.value
        and str(row["best_kcal_method"]) == meal_macro_best.kcal.method
        and float(row["best_protein_g"]) == meal_macro_best.protein_g.value
        and str(row["best_protein_g_method"]) == meal_macro_best.protein_g.method
        and float(row["best_carbs_g"]) == meal_macro_best.carbs_g.value
        and str(row["best_carbs_g_method"]) == meal_macro_best.carbs_g.method
        and float(row["best_fat_g"]) == meal_macro_best.fat_g.value
        and str(row["best_fat_g_method"]) == meal_macro_best.fat_g.method
        and str(row["source_traces_json"]) == source_traces_json
        and str(row["meal_estimate_json"]) == meal_estimate_json
    )


def _validate_local_date(local_date_value: str) -> str:
    try:
        parsed = date.fromisoformat(local_date_value)
    except ValueError as exc:
        raise ValueError("local_date must be YYYY-MM-DD") from exc
    return parsed.isoformat()


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
    "PortionCorrectionPrior",
    "PortionCorrectionPriors",
    "PortionCorrectionRecord",
    "StoredMealEstimate",
    "build_portion_correction_prior_resolver",
    "export_ledger_backup",
    "fetch_daily_totals",
    "fetch_meal_by_id",
    "fetch_portion_correction_by_id",
    "fetch_portion_correction_priors",
    "initialize_sqlite_ledger",
    "insert_meal_estimate",
    "insert_portion_correction",
]
