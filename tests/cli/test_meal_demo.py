from __future__ import annotations

import json
import uuid
from io import StringIO
from pathlib import Path

from services.cli.meal_demo import main, parse_args
from services.storage import fetch_meal_by_id


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
