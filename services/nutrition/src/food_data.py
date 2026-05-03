from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

USDA_DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "usda_seed.json"
PERSONAL_DATA_FILE = (
    Path(__file__).resolve().parents[1] / "data" / "personal_seed.json"
)


class MacroEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    aliases: tuple[str, ...] = Field(default_factory=tuple)
    category: str = Field(..., min_length=1)
    source: Literal["USDA", "PERSONAL"]
    kcal_per_100g: float = Field(..., ge=0)
    protein_g_per_100g: float = Field(..., ge=0)
    carbs_g_per_100g: float = Field(..., ge=0)
    fat_g_per_100g: float = Field(..., ge=0)


@lru_cache(maxsize=1)
def _load_usda_seed_entries() -> tuple[MacroEntry, ...]:
    return _load_seed_entries(
        data_file=USDA_DATA_FILE,
        source_label="USDA",
        expected_source="USDA",
    )


@lru_cache(maxsize=1)
def _load_personal_seed_entries() -> tuple[MacroEntry, ...]:
    return _load_seed_entries(
        data_file=PERSONAL_DATA_FILE,
        source_label="PERSONAL",
        expected_source="PERSONAL",
    )


def _load_seed_entries(
    *, data_file: Path, source_label: str, expected_source: Literal["USDA", "PERSONAL"]
) -> tuple[MacroEntry, ...]:
    payload = json.loads(data_file.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{source_label} seed catalog must be a JSON list")

    entries = tuple(MacroEntry.model_validate(item) for item in payload)
    if len({entry.id for entry in entries}) != len(entries):
        raise ValueError(f"{source_label} seed catalog contains duplicate ids")

    if any(entry.source != expected_source for entry in entries):
        raise ValueError(
            f"{source_label} seed catalog contains entries with invalid source values"
        )

    return entries


@lru_cache(maxsize=1)
def _lookup_index() -> MappingProxyType[str, MacroEntry]:
    lookup: dict[str, MacroEntry] = {}
    for entry in _load_usda_seed_entries():
        candidates = (entry.name, *entry.aliases)
        for candidate in candidates:
            key = _normalize_lookup_key(candidate)
            if key and key not in lookup:
                lookup[key] = entry
    return MappingProxyType(lookup)


def _normalize_lookup_key(value: str) -> str:
    return " ".join(value.casefold().split())


def load_macro_entries() -> tuple[MacroEntry, ...]:
    """Load all USDA seed entries as immutable MacroEntry instances."""
    return _load_usda_seed_entries()


def load_personal_macro_entries() -> tuple[MacroEntry, ...]:
    """Load all personal seed entries as immutable MacroEntry instances."""
    return _load_personal_seed_entries()


def get_macro_entry(name_or_alias: str) -> MacroEntry | None:
    """Return an entry by exact name or alias, case-insensitively."""
    if not isinstance(name_or_alias, str):
        return None
    key = _normalize_lookup_key(name_or_alias)
    if not key:
        return None
    return _lookup_index().get(key)


def find_macro_entry(name_or_alias: str) -> MacroEntry | None:
    """Alias for get_macro_entry for readability at call sites."""
    return get_macro_entry(name_or_alias)


def get_macro_entry_by_name(name_or_alias: str) -> MacroEntry | None:
    """Compatibility alias for callers that use explicit lookup naming."""
    return get_macro_entry(name_or_alias)


@lru_cache(maxsize=1)
def _load_all_entries() -> tuple[MacroEntry, ...]:
    return (*_load_usda_seed_entries(), *_load_personal_seed_entries())


def load_all_macro_entries() -> tuple[MacroEntry, ...]:
    """Load all available nutrition entries (USDA + personal seeds)."""
    return _load_all_entries()


__all__ = [
    "MacroEntry",
    "find_macro_entry",
    "get_macro_entry",
    "get_macro_entry_by_name",
    "load_all_macro_entries",
    "load_macro_entries",
    "load_personal_macro_entries",
]
