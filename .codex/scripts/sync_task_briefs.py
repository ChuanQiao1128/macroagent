#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

TASK_HEADING_RE = re.compile(r"^# (TASK-\d+) .*$", re.MULTILINE)


def parse_task_sections(source_text: str) -> dict[str, str]:
    matches = list(TASK_HEADING_RE.finditer(source_text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        task_id = match.group(1)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source_text)
        sections[task_id] = source_text[match.start() : end].strip() + "\n"
    return sections


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Split macroagent_codex_task_briefs.md into dev_agents/briefs/TASK-xxx.md."
    )
    parser.add_argument(
        "--source",
        default="macroagent_codex_package/macroagent_codex_task_briefs.md",
        help="Combined task brief markdown file.",
    )
    parser.add_argument(
        "--output-dir",
        default="dev_agents/briefs",
        help="Directory where individual task briefs are written.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing task brief files.",
    )
    parser.add_argument("tasks", nargs="*", help="Task ids to sync. Defaults to all tasks.")
    args = parser.parse_args()

    source = Path(args.source)
    output_dir = Path(args.output_dir)
    if not source.exists():
        raise SystemExit(f"Task brief source not found: {source}")

    sections = parse_task_sections(source.read_text(encoding="utf-8"))
    selected_tasks = args.tasks or sorted(sections)
    output_dir.mkdir(parents=True, exist_ok=True)

    for task_id in selected_tasks:
        if task_id not in sections:
            raise SystemExit(f"Task not found in {source}: {task_id}")
        destination = output_dir / f"{task_id}.md"
        if destination.exists() and not args.overwrite:
            print(f"skip {destination}")
            continue
        destination.write_text(sections[task_id], encoding="utf-8")
        print(f"wrote {destination}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
