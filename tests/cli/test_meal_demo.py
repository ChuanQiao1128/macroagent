from __future__ import annotations

import json
import uuid
from io import StringIO
from pathlib import Path

import pytest

from services.cli import meal_demo as meal_demo_module
from services.cli.meal_demo import main, parse_args, run_meal_demo
from services.storage import fetch_meal_by_id
from services.trace import LEDGER_SCHEMA_VERSION
from services.vision import FoodComponent, VisionAnalysisResponse


def _write_vision_components(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "components": [
                    {
                        "name": "white rice",
                        "confidence": 0.91,
                        "portion_hint": "100 g",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _structured_top_k_response() -> VisionAnalysisResponse:
    return VisionAnalysisResponse.model_validate(
        {
            "components": [
                {
                    "component_id": "component_1",
                    "visible_name": "ambiguous fruit bowl",
                    "candidates": [
                        {
                            "name": "mystery foam",
                            "confidence": 0.95,
                            "visual_evidence": ["blurry white texture"],
                        },
                        {
                            "name": "banana",
                            "confidence": 0.72,
                            "visual_evidence": ["yellow fruit pieces"],
                        },
                    ],
                    "portion": {
                        "description": "100 g",
                        "confidence": 0.8,
                        "visual_basis": ["single serving bowl"],
                    },
                    "state_hints": [],
                    "hidden_ingredient_risks": [],
                }
            ]
        }
    )


def test_parse_args_accepts_required_and_optional_flags() -> None:
    args = parse_args(
        [
            "meal.jpg",
            "ledger.sqlite3",
            "--cache-path",
            "cache.json",
            "--dry-run",
            "--vision-result-path",
            "vision.json",
        ]
    )

    assert args.image_path == "meal.jpg"
    assert args.db_path == "ledger.sqlite3"
    assert args.cache_path == "cache.json"
    assert args.dry_run is True
    assert args.vision_result_path == "vision.json"


def test_main_dry_run_prints_json_and_skips_persistence(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    vision_path = tmp_path / "vision.json"
    _write_vision_components(vision_path)

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        [
            "unused-image.jpg",
            str(db_path),
            "--dry-run",
            "--vision-result-path",
            str(vision_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert db_path.exists() is False

    payload = json.loads(stdout.getvalue())
    assert payload["dry_run"] is True
    assert payload["persisted"] is False
    uuid.UUID(payload["meal_id"])
    assert len(payload["component_estimates"]) == 1
    assert "macro_ranges" in payload
    assert "best_estimates" in payload
    assert payload["trace_versions"]["ledger_schema_version"] == LEDGER_SCHEMA_VERSION
    assert payload["trace_versions"]["vision_prompt_hash"]
    assert set(payload["trace_versions"]) == {
        "vision_schema_version",
        "vision_model_name",
        "vision_prompt_hash",
        "nutrition_catalog_version",
        "matcher_version",
        "portion_engine_version",
        "macro_calculator_version",
        "ledger_schema_version",
    }


def test_run_meal_demo_default_analyzer_preserves_structured_top_k(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "meal.jpg"
    image_path.write_bytes(b"placeholder")
    db_path = tmp_path / "ledger.sqlite3"

    def fake_structured_analyzer(
        image: str | Path | bytes | bytearray,
        *,
        cache: object | None = None,
    ) -> VisionAnalysisResponse:
        assert Path(image) == image_path
        assert cache is None
        return _structured_top_k_response()

    def fake_legacy_analyzer(*args: object, **kwargs: object) -> list[FoodComponent]:
        return [FoodComponent(name="mystery foam", confidence=0.95, portion_hint="100 g")]

    monkeypatch.setattr(
        meal_demo_module,
        "analyze_meal_photo_structured",
        fake_structured_analyzer,
    )
    monkeypatch.setattr(
        meal_demo_module,
        "analyze_meal_photo",
        fake_legacy_analyzer,
        raising=False,
    )

    payload = run_meal_demo(
        image_path=image_path,
        db_path=db_path,
        dry_run=True,
    )

    component = payload["component_estimates"][0]
    assert component["status"] == "matched"
    assert component["selected_macro_entry_id"] == "personal_seed_0012"
    assert component["top_candidates"][0]["matched_on"] == "banana"
    assert "matched via vision candidate 'banana'" in component["top_candidates"][0]["reason"]


def test_main_persists_result_to_sqlite_when_not_dry_run(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    vision_path = tmp_path / "vision.json"
    _write_vision_components(vision_path)

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        [
            "unused-image.jpg",
            str(db_path),
            "--vision-result-path",
            str(vision_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert db_path.exists() is True

    payload = json.loads(stdout.getvalue())
    assert payload["dry_run"] is False
    assert payload["persisted"] is True
    assert len(payload["component_estimates"]) == 1

    stored = fetch_meal_by_id(db_path, payload["meal_id"])
    assert stored is not None
    assert len(stored.meal_estimate.component_estimates) == len(payload["component_estimates"])
    assert stored.macro_best_estimate.model_dump(mode="json") == payload["best_estimates"]
    assert stored.meal_estimate.trace_versions.model_dump(mode="json") == payload["trace_versions"]


def test_main_returns_error_for_invalid_vision_result_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite3"
    invalid_vision_path = tmp_path / "invalid_vision.json"
    invalid_vision_path.write_text(json.dumps({"components": "not-a-list"}), encoding="utf-8")

    stdout = StringIO()
    stderr = StringIO()

    exit_code = main(
        [
            "unused-image.jpg",
            str(db_path),
            "--vision-result-path",
            str(invalid_vision_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "vision result JSON must be a list of components" in stderr.getvalue()
    assert db_path.exists() is False
