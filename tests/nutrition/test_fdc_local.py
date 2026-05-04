from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.nutrition import (
    build_fdc_local_database,
    fdc_local_database_available,
    load_fdc_local_entries_for_query,
)


def test_build_fdc_local_database_imports_searchable_core7_entries(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "survey.json"
    db_path = tmp_path / "nutrition.db"
    source_path.write_text(
        json.dumps(
            {
                "SurveyFoods": [
                    _fdc_food_payload(),
                    _fdc_food_payload(
                        fdc_id=345678,
                        description="Energy drink, citrus",
                        nutrients=[
                            _nutrient(1062, "268", "Energy", "kJ", 180.0),
                            _nutrient(1003, "203", "Protein", "G", 0.2),
                            _nutrient(1005, "205", "Carbohydrate, by difference", "G", 11.0),
                            _nutrient(1004, "204", "Total lipid (fat)", "G", 0.0),
                        ],
                    ),
                    {"fdcId": 456789, "description": "Incomplete food", "foodNutrients": []},
                ]
            }
        ),
        encoding="utf-8",
    )

    result = build_fdc_local_database([source_path], db_path=db_path)

    assert result.source_file_count == 1
    assert result.imported_food_count == 2
    assert result.skipped_food_count == 1
    assert db_path.exists()

    entries = load_fdc_local_entries_for_query(
        "spicy tuna roll",
        db_path=db_path,
    )

    assert entries
    assert entries[0].id == "fdc:234567"
    assert entries[0].name == "Sushi roll, spicy tuna"
    assert entries[0].category == "Prepared foods"
    assert entries[0].kcal_per_100g == pytest.approx(145.0)
    assert entries[0].protein_g_per_100g == pytest.approx(5.2)
    assert entries[0].carbs_g_per_100g == pytest.approx(27.8)
    assert entries[0].fat_g_per_100g == pytest.approx(2.1)
    assert entries[0].sugar_g_per_100g == pytest.approx(3.4)
    assert entries[0].sodium_mg_per_100g == pytest.approx(315.0)
    assert entries[0].fiber_g_per_100g == pytest.approx(1.2)

    energy_drink = load_fdc_local_entries_for_query("citrus energy drink", db_path=db_path)
    assert energy_drink
    assert energy_drink[0].kcal_per_100g == pytest.approx(180.0 / 4.184)


def test_fdc_local_lookup_respects_disabled_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "survey.json"
    db_path = tmp_path / "nutrition.db"
    source_path.write_text(json.dumps({"SurveyFoods": [_fdc_food_payload()]}), encoding="utf-8")
    build_fdc_local_database([source_path], db_path=db_path)

    monkeypatch.setenv("FDC_LOCAL_LOOKUP_ENABLED", "0")

    assert not fdc_local_database_available(db_path=db_path)
    assert load_fdc_local_entries_for_query("spicy tuna roll", db_path=db_path) == ()


def _fdc_food_payload(
    *,
    fdc_id: int = 234567,
    description: str = "Sushi roll, spicy tuna",
    nutrients: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "fdcId": fdc_id,
        "description": description,
        "lowercaseDescription": description.casefold(),
        "dataType": "Survey (FNDDS)",
        "publicationDate": "2024-10-31",
        "foodCategory": {"description": "Prepared foods"},
        "foodCode": "58100010",
        "additionalDescriptions": "spicy tuna maki roll",
        "foodNutrients": nutrients
        or [
            _nutrient(1008, "208", "Energy", "KCAL", 145.0),
            _nutrient(1003, "203", "Protein", "G", 5.2),
            _nutrient(1005, "205", "Carbohydrate, by difference", "G", 27.8),
            _nutrient(1004, "204", "Total lipid (fat)", "G", 2.1),
            _nutrient(2000, "269", "Total Sugars", "G", 3.4),
            _nutrient(1093, "307", "Sodium, Na", "MG", 315.0),
            _nutrient(1079, "291", "Fiber, total dietary", "G", 1.2),
        ],
    }


def _nutrient(
    nutrient_id: int,
    nutrient_number: str,
    name: str,
    unit: str,
    amount: float,
) -> dict[str, object]:
    return {
        "nutrient": {
            "id": nutrient_id,
            "number": nutrient_number,
            "name": name,
            "unitName": unit,
        },
        "amount": amount,
    }
