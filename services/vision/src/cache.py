from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol


class VisionResultCache(Protocol):
    def get(self, key: str) -> list[dict[str, Any]] | None:
        """Return cached component payloads for a key, if present."""

    def set(self, key: str, components: list[dict[str, Any]]) -> None:
        """Persist component payloads for a key."""


class JsonFileVisionCache:
    """Simple local JSON cache for vision analysis results."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def get(self, key: str) -> list[dict[str, Any]] | None:
        data = self._load()
        payload = data.get(key)
        if not isinstance(payload, list):
            return None
        if not all(isinstance(item, dict) for item in payload):
            return None
        return [dict(item) for item in payload]

    def set(self, key: str, components: list[dict[str, Any]]) -> None:
        data = self._load()
        data[key] = [dict(item) for item in components]
        self._write_atomic(data)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            content = self.path.read_text(encoding="utf-8")
            parsed = json.loads(content)
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(parsed, dict):
            return {}
        return parsed

    def _write_atomic(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix=f"{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, sort_keys=True)
            os.replace(temp_path, self.path)
        finally:
            try:
                os.remove(temp_path)
            except FileNotFoundError:
                pass
