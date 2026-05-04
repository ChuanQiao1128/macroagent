from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from pydantic import ValidationError

from services.accounting import calculate_meal_macro_best_estimate
from services.meal import analyze_meal_components
from services.storage import initialize_sqlite_ledger, insert_meal_estimate
from services.vision import (
    FoodComponent,
    JsonFileVisionCache,
    VisionAnalysisResponse,
    analyze_meal_photo_structured,
)

VisionAnalysisInput = list[FoodComponent] | VisionAnalysisResponse
VisionAnalyzeFn = Callable[[Path, Path | None], VisionAnalysisInput]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m services.cli.meal_demo",
        description=(
            "Analyze a meal image with the local pipeline and optionally persist "
            "the estimate to a SQLite ledger."
        ),
    )
    parser.add_argument("image_path", help="Path to the meal image file.")
    parser.add_argument("db_path", help="Path to the SQLite ledger file.")
    parser.add_argument(
        "--cache-path",
        default=None,
        help="Optional JSON cache file for vision responses.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip SQLite persistence and only print the computed estimate.",
    )
    parser.add_argument(
        "--vision-result-path",
        default=None,
        help=(
            "Optional JSON file containing precomputed vision components. "
            "Use for offline/test runs without API calls."
        ),
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def run_meal_demo(
    *,
    image_path: str | Path,
    db_path: str | Path,
    cache_path: str | Path | None = None,
    dry_run: bool = False,
    vision_result_path: str | Path | None = None,
    vision_analyzer: VisionAnalyzeFn | None = None,
) -> dict[str, object]:
    image_file = Path(image_path)
    db_file = Path(db_path)
    cache_file = Path(cache_path) if cache_path is not None else None

    if vision_result_path is not None:
        components = _load_components_from_path(vision_result_path)
    else:
        image_file = _validate_image_path(image_file)
        analyzer = vision_analyzer or _analyze_with_claude_vision
        components = analyzer(image_file, cache_file)

    meal_estimate = analyze_meal_components(components)
    best_estimates = calculate_meal_macro_best_estimate(meal_estimate.macro_interval)

    meal_id = str(uuid.uuid4())
    persisted = False
    if not dry_run:
        initialize_sqlite_ledger(db_file)
        meal_id = insert_meal_estimate(
            db_file,
            meal_estimate=meal_estimate,
            meal_id=meal_id,
        )
        persisted = True

    return {
        "meal_id": meal_id,
        "persisted": persisted,
        "dry_run": dry_run,
        "component_estimates": [
            component.model_dump(mode="json")
            for component in meal_estimate.component_estimates
        ],
        "macro_ranges": meal_estimate.macro_interval.model_dump(mode="json"),
        "best_estimates": best_estimates.model_dump(mode="json"),
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = stdout or sys.stdout
    err = stderr or sys.stderr

    try:
        args = parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)

    try:
        payload = run_meal_demo(
            image_path=args.image_path,
            db_path=args.db_path,
            cache_path=args.cache_path,
            dry_run=bool(args.dry_run),
            vision_result_path=args.vision_result_path,
        )
    except Exception as exc:  # pragma: no cover - exercised by CLI error-path tests
        err.write(f"error: {exc}\n")
        return 1

    json.dump(payload, out, sort_keys=True)
    out.write("\n")
    return 0


def _validate_image_path(path: str | Path) -> Path:
    image_file = Path(path)
    if not image_file.exists():
        raise FileNotFoundError(f"image file not found: {image_file}")
    if not image_file.is_file():
        raise ValueError(f"image path is not a file: {image_file}")
    return image_file


def _analyze_with_claude_vision(
    image_path: Path,
    cache_path: Path | None,
) -> VisionAnalysisResponse:
    cache = JsonFileVisionCache(cache_path) if cache_path is not None else None
    return analyze_meal_photo_structured(str(image_path), cache=cache)


def _load_components_from_path(path: str | Path) -> VisionAnalysisInput:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        try:
            return VisionAnalysisResponse.model_validate(payload)
        except ValidationError:
            payload = payload.get("components")
    elif isinstance(payload, list):
        try:
            return VisionAnalysisResponse.model_validate({"components": payload})
        except ValidationError:
            pass

    if isinstance(payload, dict):
        payload = payload.get("components")
    if not isinstance(payload, list):
        raise ValueError(
            "vision result JSON must be a list of components or an object with "
            "a 'components' list"
        )

    components: list[FoodComponent] = []
    for index, item in enumerate(payload):
        try:
            components.append(FoodComponent.model_validate(item))
        except ValidationError as exc:
            raise ValueError(f"invalid component payload at index {index}") from exc
    return components


if __name__ == "__main__":
    raise SystemExit(main())
