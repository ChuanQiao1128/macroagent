from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from services.meal import (
    V0_3_BENCHMARK_FIXTURES,
    load_fixture_results_jsonl,
    summarize_benchmark_results,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m services.cli.benchmark_report",
        description="Summarize v0.3 benchmark fixture outputs from a JSONL file.",
    )
    parser.add_argument(
        "--fixtures-jsonl",
        type=Path,
        required=True,
        help="JSONL file containing one benchmark result row per line.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional output path for writing the report JSON.",
    )
    return parser


def generate_benchmark_report(fixtures_jsonl: str | Path) -> dict[str, Any]:
    rows = load_fixture_results_jsonl(fixtures_jsonl)
    return summarize_benchmark_results(rows, fixtures=V0_3_BENCHMARK_FIXTURES)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = generate_benchmark_report(args.fixtures_jsonl)
    rendered = json.dumps(report, indent=2, sort_keys=True)

    if args.output_json is None:
        print(rendered)
    else:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
