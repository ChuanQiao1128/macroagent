#!/usr/bin/env python3
"""Check whether a git diff complies with the selected agent role ACL."""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path
from typing import Any


ACL_PATH = Path("dev_agents/policies/path_acl.yaml")


def run_git(args: list[str], *, check: bool = True) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        print(result.stderr.strip() or f"git {' '.join(args)} failed", file=sys.stderr)
        sys.exit(result.returncode)
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line]


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def load_limited_acl(path: Path) -> dict[str, Any]:
    roles: dict[str, dict[str, Any]] = {}
    current_role: str | None = None
    current_key: str | None = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        text = raw.strip()

        if indent == 0:
            continue
        if indent == 2 and text.endswith(":"):
            current_role = text[:-1]
            roles[current_role] = {}
            current_key = None
            continue
        if current_role is None:
            continue
        if indent == 4 and ":" in text:
            key, value = text.split(":", 1)
            current_key = key.strip()
            value = value.strip()
            if value == "[]":
                roles[current_role][current_key] = []
            elif value.lower() in {"true", "false"}:
                roles[current_role][current_key] = value.lower() == "true"
            elif not value:
                roles[current_role][current_key] = []
            else:
                roles[current_role][current_key] = unquote(value)
            continue
        if indent == 6 and text.startswith("- ") and current_key:
            roles[current_role].setdefault(current_key, []).append(unquote(text[2:]))

    return {"roles": roles}


def load_acl(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        return load_limited_acl(path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def matches(path: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return pattern
    return None


def changed_files(base: str, head: str) -> list[str]:
    if head.upper() != "WORKTREE":
        return sorted(set(run_git(["diff", "--name-only", f"{base}..{head}"])))

    names: set[str] = set()
    names.update(run_git(["diff", "--name-only", f"{base}..HEAD"], check=False))
    names.update(run_git(["diff", "--name-only"]))
    names.update(run_git(["diff", "--cached", "--name-only"]))
    names.update(run_git(["ls-files", "--others", "--exclude-standard"]))
    return sorted(names)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()

    acl = load_acl(ACL_PATH).get("roles", {})
    if args.role not in acl:
        print(f"Unknown agent role: {args.role}", file=sys.stderr)
        return 2

    role_acl = acl[args.role]
    diff = changed_files(args.base, args.head)

    if role_acl.get("comment_only") and diff:
        print(f"{args.role} is comment-only but changed {len(diff)} file(s):")
        for path in diff:
            print(f"  {path}")
        return 1

    violations: list[tuple[str, str, str]] = []
    deny = role_acl.get("deny", []) or []
    allow = role_acl.get("allow", []) or []

    for path in diff:
        denied_by = matches(path, deny)
        if denied_by:
            violations.append((path, "deny", denied_by))
            continue
        if allow and not matches(path, allow):
            violations.append((path, "allow", "not in allow list"))

    if violations:
        print(f"{args.role} agent violated ACL:")
        for path, kind, pattern in violations:
            print(f"  {path}  ({kind}: {pattern})")
        return 1

    print(f"{args.role} ACL clean ({len(diff)} file(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
