from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from services.accounting import (
    MacroBestEstimate,
    MacroBestEstimateSet,
    MacroRange,
    MealMacroInterval,
    calculate_food_macro_best_estimate,
    calculate_macro_best_estimate,
    calculate_meal_macro_best_estimate,
)
from services.meal import MealComponentEstimate, MealEstimate


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


def _apply_migrations(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    applied_versions = {
        int(row["version"]) for row in connection.execute("SELECT version FROM schema_migrations")
    }

    for migration in _MIGRATIONS:
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


def _json_dumps(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _connect(database_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


__all__ = [
    "DailyLedgerTotals",
    "StoredMealEstimate",
    "fetch_daily_totals",
    "fetch_meal_by_id",
    "initialize_sqlite_ledger",
    "insert_meal_estimate",
]
