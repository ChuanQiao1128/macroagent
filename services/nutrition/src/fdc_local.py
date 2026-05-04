from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from services.nutrition.src.food_data import NutritionEntry

FDC_LOCAL_DB_PATH_ENV = "FDC_LOCAL_DB_PATH"
FDC_LOCAL_LOOKUP_ENABLED_ENV = "FDC_LOCAL_LOOKUP_ENABLED"
FDC_LOCAL_DEFAULT_DB_PATH = Path("local_outputs/fdc_local/nutrition.db")
FDC_LOCAL_SCHEMA_VERSION = 1
FDC_LOCAL_SOURCE = "USDA"

_FOOD_LIST_KEYS = (
    "FoundationFoods",
    "SRLegacyFoods",
    "SurveyFoods",
    "BrandedFoods",
    "Foods",
    "foods",
)


class FdcLocalImportResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    db_path: str = Field(..., min_length=1)
    source_file_count: int = Field(..., ge=0)
    imported_food_count: int = Field(..., ge=0)
    skipped_food_count: int = Field(..., ge=0)


@dataclass(frozen=True)
class _ExtractedFood:
    entry: NutritionEntry
    source_type: str
    publication_date: str | None
    food_code: str | None
    aliases_text: str


def build_fdc_local_database(
    source_paths: Sequence[str | Path],
    *,
    db_path: str | Path | None = None,
) -> FdcLocalImportResult:
    """Build a local SQLite nutrition database from downloaded FDC JSON files."""
    resolved_db_path = _resolve_db_path(db_path)
    source_files = tuple(Path(path) for path in source_paths)
    if not source_files:
        raise ValueError("at least one FDC JSON source path is required")
    for source_file in source_files:
        if not source_file.exists():
            raise FileNotFoundError(source_file)

    resolved_db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = resolved_db_path.with_suffix(resolved_db_path.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    imported_count = 0
    skipped_count = 0
    with sqlite3.connect(tmp_path) as connection:
        _initialize_schema(connection)
        for source_file in source_files:
            imported, skipped = _import_source_file(connection, source_file)
            imported_count += imported
            skipped_count += skipped
        connection.execute("ANALYZE")
        connection.execute("PRAGMA optimize")

    tmp_path.replace(resolved_db_path)
    return FdcLocalImportResult(
        db_path=str(resolved_db_path),
        source_file_count=len(source_files),
        imported_food_count=imported_count,
        skipped_food_count=skipped_count,
    )


def load_fdc_local_entries_for_query(
    query: str,
    *,
    db_path: str | Path | None = None,
    limit: int = 25,
) -> tuple[NutritionEntry, ...]:
    """Search the local FDC SQLite database and return NutritionEntry matches."""
    if not _local_lookup_enabled():
        return ()
    if limit <= 0 or not isinstance(query, str):
        return ()

    resolved_db_path = _resolve_db_path(db_path)
    if not resolved_db_path.exists():
        return ()

    tokens = _tokenize(query)
    if not tokens:
        return ()

    with sqlite3.connect(resolved_db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = _search_rows(connection, tokens=tokens, limit=limit)
    return tuple(_entry_from_row(row) for row in rows)


def fdc_local_database_available(*, db_path: str | Path | None = None) -> bool:
    """Return whether the local FDC lookup path is enabled and has a database file."""
    return _local_lookup_enabled() and _resolve_db_path(db_path).exists()


def _resolve_db_path(db_path: str | Path | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    configured = os.getenv(FDC_LOCAL_DB_PATH_ENV)
    return Path(configured) if configured else FDC_LOCAL_DEFAULT_DB_PATH


def _local_lookup_enabled() -> bool:
    configured = os.getenv(FDC_LOCAL_LOOKUP_ENABLED_ENV)
    if configured is None:
        return True
    return configured.strip().casefold() not in {"0", "false", "no", "off"}


def _initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode = DELETE;
        PRAGMA synchronous = NORMAL;

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE foods (
            food_id TEXT PRIMARY KEY,
            fdc_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            source_type TEXT NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            publication_date TEXT,
            food_code TEXT,
            aliases_text TEXT NOT NULL,
            kcal_per_100g REAL NOT NULL,
            protein_g_per_100g REAL NOT NULL,
            carbs_g_per_100g REAL NOT NULL,
            fat_g_per_100g REAL NOT NULL,
            sugar_g_per_100g REAL NOT NULL,
            sodium_mg_per_100g REAL NOT NULL,
            fiber_g_per_100g REAL NOT NULL
        );

        CREATE INDEX idx_foods_fdc_id ON foods(fdc_id);
        CREATE INDEX idx_foods_source_type ON foods(source_type);

        CREATE VIRTUAL TABLE food_search_fts USING fts5(
            food_id UNINDEXED,
            name,
            aliases,
            category,
            source_type
        );
        """
    )
    connection.execute(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        ("schema_version", str(FDC_LOCAL_SCHEMA_VERSION)),
    )


def _import_source_file(connection: sqlite3.Connection, source_file: Path) -> tuple[int, int]:
    payload = json.loads(source_file.read_text(encoding="utf-8"))
    imported_count = 0
    skipped_count = 0
    for food in _iter_food_payloads(payload):
        extracted = _extract_food(food)
        if extracted is None:
            skipped_count += 1
            continue
        _insert_food(connection, extracted)
        imported_count += 1
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        (f"source_file:{source_file.name}", str(source_file)),
    )
    return imported_count, skipped_count


def _iter_food_payloads(payload: object) -> Iterable[Mapping[str, object]]:
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        for item in payload:
            if isinstance(item, Mapping):
                yield item
        return

    if not isinstance(payload, Mapping):
        return
    for key in _FOOD_LIST_KEYS:
        foods = payload.get(key)
        if isinstance(foods, Sequence) and not isinstance(foods, (str, bytes)):
            for item in foods:
                if isinstance(item, Mapping):
                    yield item
            return


def _extract_food(food: Mapping[str, object]) -> _ExtractedFood | None:
    fdc_id = food.get("fdcId")
    description = food.get("description")
    if not isinstance(fdc_id, int) or not isinstance(description, str):
        return None

    nutrients = food.get("foodNutrients")
    if not isinstance(nutrients, Sequence) or isinstance(nutrients, (str, bytes)):
        return None

    kcal = _extract_nutrient(nutrients, ids={1008}, numbers={"208"})
    if kcal is None:
        energy_kj = _extract_nutrient(
            nutrients,
            ids={1062},
            names={"energy"},
            source_units={"kj"},
        )
        kcal = None if energy_kj is None else energy_kj / 4.184
    protein = _extract_nutrient(nutrients, ids={1003}, numbers={"203"}, target_unit="g")
    carbs = _extract_nutrient(nutrients, ids={1005}, numbers={"205"}, target_unit="g")
    fat = _extract_nutrient(nutrients, ids={1004}, numbers={"204"}, target_unit="g")
    if kcal is None or protein is None or carbs is None or fat is None:
        return None

    sugar = _extract_nutrient(
        nutrients,
        ids={2000},
        numbers={"269"},
        names={"sugars, total including nlea", "sugars, total", "total sugars"},
        target_unit="g",
    )
    sodium = _extract_nutrient(
        nutrients,
        ids={1093},
        numbers={"307"},
        names={"sodium, na", "sodium"},
        target_unit="mg",
    )
    fiber = _extract_nutrient(
        nutrients,
        ids={1079},
        numbers={"291"},
        names={"fiber, total dietary", "total dietary fiber", "dietary fiber"},
        target_unit="g",
    )
    aliases = _aliases_for_food(food)
    source_type = _clean_text(str(food.get("dataType") or "FDC")) or "FDC"
    food_code = food.get("foodCode")
    publication_date = food.get("publicationDate")
    name = _clean_text(description)
    category = _infer_category(food, aliases=aliases)
    entry = NutritionEntry(
        id=f"fdc:{fdc_id}",
        name=name,
        aliases=aliases,
        category=category,
        source=FDC_LOCAL_SOURCE,
        kcal_per_100g=round(float(kcal), 3),
        protein_g_per_100g=round(float(protein), 3),
        carbs_g_per_100g=round(float(carbs), 3),
        fat_g_per_100g=round(float(fat), 3),
        sugar_g_per_100g=round(float(sugar or 0.0), 3),
        sodium_mg_per_100g=round(float(sodium or 0.0), 3),
        fiber_g_per_100g=round(float(fiber or 0.0), 3),
    )
    return _ExtractedFood(
        entry=entry,
        source_type=source_type,
        publication_date=str(publication_date) if isinstance(publication_date, str) else None,
        food_code=str(food_code) if food_code is not None else None,
        aliases_text=" | ".join(aliases),
    )


def _insert_food(connection: sqlite3.Connection, food: _ExtractedFood) -> None:
    entry = food.entry
    connection.execute(
        """
        INSERT OR REPLACE INTO foods (
            food_id,
            fdc_id,
            source,
            source_type,
            name,
            category,
            publication_date,
            food_code,
            aliases_text,
            kcal_per_100g,
            protein_g_per_100g,
            carbs_g_per_100g,
            fat_g_per_100g,
            sugar_g_per_100g,
            sodium_mg_per_100g,
            fiber_g_per_100g
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry.id,
            int(entry.id.removeprefix("fdc:")),
            entry.source,
            food.source_type,
            entry.name,
            entry.category,
            food.publication_date,
            food.food_code,
            food.aliases_text,
            entry.kcal_per_100g,
            entry.protein_g_per_100g,
            entry.carbs_g_per_100g,
            entry.fat_g_per_100g,
            entry.sugar_g_per_100g,
            entry.sodium_mg_per_100g,
            entry.fiber_g_per_100g,
        ),
    )
    connection.execute(
        """
        INSERT INTO food_search_fts(food_id, name, aliases, category, source_type)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            entry.id,
            entry.name,
            food.aliases_text,
            entry.category,
            food.source_type,
        ),
    )


def _search_rows(
    connection: sqlite3.Connection,
    *,
    tokens: tuple[str, ...],
    limit: int,
) -> tuple[sqlite3.Row, ...]:
    fts_query = " OR ".join(f"{token}*" for token in tokens)
    rows = connection.execute(
        """
        SELECT foods.*
        FROM food_search_fts
        JOIN foods ON foods.food_id = food_search_fts.food_id
        WHERE food_search_fts MATCH ?
        ORDER BY bm25(food_search_fts)
        LIMIT ?
        """,
        (fts_query, max(limit, 1)),
    ).fetchall()
    if rows:
        return tuple(rows)

    like_clauses = " AND ".join("lower(name || ' ' || aliases_text) LIKE ?" for _ in tokens)
    like_values = tuple(f"%{token}%" for token in tokens)
    return tuple(
        connection.execute(
            f"""
            SELECT *
            FROM foods
            WHERE {like_clauses}
            ORDER BY length(name) ASC
            LIMIT ?
            """,
            (*like_values, max(limit, 1)),
        ).fetchall()
    )


def _entry_from_row(row: sqlite3.Row) -> NutritionEntry:
    aliases = tuple(
        alias.strip() for alias in str(row["aliases_text"]).split("|") if alias.strip()
    )
    return NutritionEntry(
        id=str(row["food_id"]),
        name=str(row["name"]),
        aliases=aliases,
        category=str(row["category"]),
        source="USDA",
        kcal_per_100g=float(row["kcal_per_100g"]),
        protein_g_per_100g=float(row["protein_g_per_100g"]),
        carbs_g_per_100g=float(row["carbs_g_per_100g"]),
        fat_g_per_100g=float(row["fat_g_per_100g"]),
        sugar_g_per_100g=float(row["sugar_g_per_100g"]),
        sodium_mg_per_100g=float(row["sodium_mg_per_100g"]),
        fiber_g_per_100g=float(row["fiber_g_per_100g"]),
    )


def _extract_nutrient(
    nutrients: Sequence[object],
    *,
    ids: set[int] | None = None,
    numbers: set[str] | None = None,
    names: set[str] | None = None,
    source_units: set[str] | None = None,
    target_unit: Literal["g", "mg"] | None = None,
) -> float | None:
    for nutrient in nutrients:
        if not isinstance(nutrient, Mapping):
            continue
        value = nutrient.get("amount")
        if value is None:
            value = nutrient.get("value")
        if value is None:
            continue

        nested_nutrient = nutrient.get("nutrient")
        nested = nested_nutrient if isinstance(nested_nutrient, Mapping) else {}
        nutrient_id = nutrient.get("nutrientId", nested.get("id"))
        nutrient_number = str(
            nutrient.get("nutrientNumber", nested.get("number", ""))
        ).strip()
        nutrient_name = str(nutrient.get("nutrientName", nested.get("name", ""))).strip().casefold()
        unit_name = str(nutrient.get("unitName", nested.get("unitName", ""))).strip().casefold()

        if source_units is not None and unit_name not in source_units:
            continue
        if ids is not None and nutrient_id in ids:
            return _convert_unit(float(value), unit_name, target_unit)
        if numbers is not None and nutrient_number in numbers:
            return _convert_unit(float(value), unit_name, target_unit)
        if names is not None and nutrient_name in names:
            return _convert_unit(float(value), unit_name, target_unit)
    return None


def _convert_unit(
    value: float,
    source_unit: str,
    target_unit: Literal["g", "mg"] | None,
) -> float:
    if target_unit is None:
        return value
    normalized_source = _normalize_unit(source_unit)
    if normalized_source is None or normalized_source == target_unit:
        return value
    if normalized_source == "mg" and target_unit == "g":
        return value / 1000.0
    if normalized_source == "g" and target_unit == "mg":
        return value * 1000.0
    return value


def _normalize_unit(unit_name: str) -> Literal["g", "mg"] | None:
    normalized = unit_name.strip().casefold()
    if normalized in {"g", "gram", "grams"}:
        return "g"
    if normalized in {"mg", "milligram", "milligrams"}:
        return "mg"
    return None


def _aliases_for_food(food: Mapping[str, object]) -> tuple[str, ...]:
    aliases: list[str] = []
    for key in (
        "lowercaseDescription",
        "additionalDescriptions",
        "brandOwner",
        "brandName",
        "ingredients",
    ):
        value = food.get(key)
        if isinstance(value, str):
            cleaned = _clean_text(value)
            if cleaned:
                aliases.append(cleaned)

    category_description = _category_description(food)
    if category_description is not None:
        aliases.append(category_description)
    food_code = food.get("foodCode")
    if food_code is not None:
        aliases.append(str(food_code))
    return tuple(dict.fromkeys(aliases))


def _category_description(food: Mapping[str, object]) -> str | None:
    category = food.get("foodCategory")
    if isinstance(category, Mapping):
        description = category.get("description")
        if isinstance(description, str) and description.strip():
            return _clean_text(description)
    wweia = food.get("wweiaFoodCategory")
    if isinstance(wweia, Mapping):
        description = wweia.get("wweiaFoodCategoryDescription")
        if isinstance(description, str) and description.strip():
            return _clean_text(description)
    attributes = food.get("foodAttributes")
    if isinstance(attributes, Sequence) and not isinstance(attributes, (str, bytes)):
        for attribute in attributes:
            if not isinstance(attribute, Mapping):
                continue
            if attribute.get("name") != "WWEIA Category description":
                continue
            value = attribute.get("value")
            if isinstance(value, str) and value.strip():
                return _clean_text(value)
    return None


def _infer_category(food: Mapping[str, object], *, aliases: tuple[str, ...]) -> str:
    category_description = _category_description(food)
    if category_description is not None:
        return category_description
    text = " ".join((str(food.get("description") or ""), *aliases)).casefold()
    tokens = set(_tokenize(text))
    if tokens & {"sushi", "maki", "roll", "pizza", "sandwich", "burrito"}:
        return "prepared_meal"
    if tokens & {"coffee", "espresso", "americano", "tea", "juice", "soda"}:
        return "beverages"
    if tokens & {"sugar", "syrup", "sweetener"}:
        return "sugars"
    if tokens & {"sauce", "mayo", "mayonnaise", "dressing", "ketchup"}:
        return "sauces"
    if tokens & {"rice", "noodle", "pasta", "bread", "cereal", "oats"}:
        return "grains"
    if tokens & {"fish", "salmon", "tuna", "shrimp", "beef", "chicken", "pork", "turkey"}:
        return "protein"
    if tokens & {"milk", "cheese", "yogurt", "cream"}:
        return "dairy"
    if tokens & {"apple", "banana", "orange", "fruit", "berries"}:
        return "fruit"
    if tokens & {"broccoli", "vegetable", "vegetables", "salad", "spinach"}:
        return "vegetables"
    if tokens & {"oil", "butter"}:
        return "oils"
    return "fdc"


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _tokenize(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(re.findall(r"[a-z0-9]+", value.casefold())))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m services.nutrition.src.fdc_local",
        description="Build a local SQLite nutrition database from FDC JSON downloads.",
    )
    parser.add_argument("source_paths", nargs="+", help="FDC JSON files to import.")
    parser.add_argument(
        "--db-path",
        default=str(FDC_LOCAL_DEFAULT_DB_PATH),
        help="Output SQLite path.",
    )
    args = parser.parse_args(argv)
    result = build_fdc_local_database(args.source_paths, db_path=args.db_path)
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FDC_LOCAL_DB_PATH_ENV",
    "FDC_LOCAL_DEFAULT_DB_PATH",
    "FDC_LOCAL_LOOKUP_ENABLED_ENV",
    "FdcLocalImportResult",
    "build_fdc_local_database",
    "fdc_local_database_available",
    "load_fdc_local_entries_for_query",
]
