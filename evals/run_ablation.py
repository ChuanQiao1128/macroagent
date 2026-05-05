#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import itertools
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

DEFAULT_FACTORS = (
    "vision_top_k",
    "source_critic",
    "scale_evidence",
    "personal_priors",
    "uncertainty_gate",
)


def build_factorial_cells(factors: Sequence[str]) -> list[dict[str, bool]]:
    """Return a full factorial on/off design for the requested factors."""
    return [
        dict(zip(factors, values, strict=True))
        for values in itertools.product((False, True), repeat=len(factors))
    ]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as file_obj:
        for line_number, line in enumerate(file_obj, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number} must contain a JSON object")
            rows.append(payload)
    return rows


def summarize_rows(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "fixture_count": 0,
            "coverage_rate": None,
            "mean_relative_range_width": None,
            "clarify_trigger_rate": None,
            "log_anyway_rate": None,
        }

    return {
        "fixture_count": len(rows),
        "coverage_rate": _mean_bool(row.get("correction_within_range") for row in rows),
        "mean_relative_range_width": _mean_number(
            row.get("relative_range_width") for row in rows
        ),
        "clarify_trigger_rate": _mean_bool(
            _equals(row.get("decision"), "CLARIFY") for row in rows
        ),
        "log_anyway_rate": _mean_bool(row.get("user_accepted_wide_range") for row in rows),
    }


def write_cells_csv(cells: Sequence[dict[str, bool]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(cells[0]) if cells else []
    with output_path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cells)


def _mean_bool(values: Iterable[object]) -> float | None:
    bool_values = [bool(value) for value in values if value is not None]
    if not bool_values:
        return None
    return sum(1 for value in bool_values if value) / len(bool_values)


def _mean_number(values: Iterable[object]) -> float | None:
    numbers: list[float] = []
    for value in values:
        if value is None:
            continue
        try:
            numbers.append(float(value))
        except (TypeError, ValueError):
            continue
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _equals(value: object, expected: str) -> bool | None:
    if value is None:
        return None
    return str(value).upper() == expected


def _parse_factors(raw_factors: str) -> tuple[str, ...]:
    factors = tuple(factor.strip() for factor in raw_factors.split(",") if factor.strip())
    if not factors:
        raise ValueError("at least one ablation factor is required")
    return factors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate factorial ablation cells and summarize fixture JSONL results."
    )
    parser.add_argument(
        "--factors",
        default=",".join(DEFAULT_FACTORS),
        help="Comma-separated factor names. Default is the v0.3 five-factor plan.",
    )
    parser.add_argument(
        "--fixtures-jsonl",
        type=Path,
        help="Optional JSONL file with fixture result rows to summarize.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        help="Optional CSV path for generated factorial cells.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a short text report.",
    )
    args = parser.parse_args()

    factors = _parse_factors(args.factors)
    cells = build_factorial_cells(factors)
    summary = summarize_rows(load_jsonl(args.fixtures_jsonl)) if args.fixtures_jsonl else None

    if args.output_csv:
        write_cells_csv(cells, args.output_csv)

    report = {
        "factors": list(factors),
        "cell_count": len(cells),
        "factorial_design": "full",
        "summary": summary,
    }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Full factorial ablation design: {len(cells)} cells")
        print(f"Factors: {', '.join(factors)}")
        if summary is not None:
            print(json.dumps(summary, indent=2, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
