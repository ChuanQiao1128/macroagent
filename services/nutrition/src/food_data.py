from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
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


class MacroMatchCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entry: MacroEntry
    score: float = Field(..., ge=0, le=1)
    matched_on: str = Field(..., min_length=1)
    match_type: Literal[
        "exact_name",
        "exact_alias",
        "token_containment",
        "fuzzy",
    ]


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


def _tokenize(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", value.casefold()))


def _token_containment_score(
    query_normalized: str,
    query_tokens: frozenset[str],
    candidate_normalized: str,
    candidate_tokens: frozenset[str],
) -> float | None:
    if not query_tokens or not candidate_tokens:
        return None

    overlap_count = len(query_tokens & candidate_tokens)
    if overlap_count == 0:
        return None

    contains_tokens = query_tokens <= candidate_tokens or candidate_tokens <= query_tokens
    contains_text = (
        query_normalized in candidate_normalized
        or candidate_normalized in query_normalized
    )
    if not contains_tokens and not contains_text:
        return None

    overlap_vs_larger = overlap_count / max(len(query_tokens), len(candidate_tokens))
    overlap_vs_candidate = overlap_count / len(candidate_tokens)
    substring_bonus = 0.08 if contains_text else 0.0
    return min(
        0.89,
        0.68 + (0.14 * overlap_vs_larger) + (0.08 * overlap_vs_candidate) + substring_bonus,
    )


def _fuzzy_score(
    query_normalized: str,
    query_tokens: tuple[str, ...],
    candidate_normalized: str,
    candidate_tokens: tuple[str, ...],
) -> float:
    query_token_text = " ".join(query_tokens)
    candidate_token_text = " ".join(candidate_tokens)

    char_ratio = SequenceMatcher(None, query_normalized, candidate_normalized).ratio()
    token_ratio = SequenceMatcher(None, query_token_text, candidate_token_text).ratio()
    query_token_set = set(query_tokens)
    candidate_token_set = set(candidate_tokens)
    token_jaccard = (
        len(query_token_set & candidate_token_set)
        / len(query_token_set | candidate_token_set)
    ) if query_token_set and candidate_token_set else 0.0
    return (0.45 * char_ratio) + (0.35 * token_ratio) + (0.20 * token_jaccard)


def _score_candidate_term(
    *,
    query_normalized: str,
    query_tokens: tuple[str, ...],
    candidate_text: str,
    candidate_is_name: bool,
) -> tuple[float, str, Literal["exact_name", "exact_alias", "token_containment", "fuzzy"]] | None:
    candidate_normalized = _normalize_lookup_key(candidate_text)
    if not candidate_normalized:
        return None

    if query_normalized == candidate_normalized:
        return (
            1.0 if candidate_is_name else 0.99,
            candidate_text,
            "exact_name" if candidate_is_name else "exact_alias",
        )

    query_token_set = frozenset(query_tokens)
    candidate_tokens = _tokenize(candidate_text)
    candidate_token_set = frozenset(candidate_tokens)
    containment_score = _token_containment_score(
        query_normalized=query_normalized,
        query_tokens=query_token_set,
        candidate_normalized=candidate_normalized,
        candidate_tokens=candidate_token_set,
    )
    if containment_score is not None:
        return (containment_score, candidate_text, "token_containment")

    fuzzy_score = _fuzzy_score(
        query_normalized=query_normalized,
        query_tokens=query_tokens,
        candidate_normalized=candidate_normalized,
        candidate_tokens=candidate_tokens,
    )
    if fuzzy_score >= 0.60:
        return (fuzzy_score, candidate_text, "fuzzy")
    return None


def _score_entry_match(
    *,
    query_normalized: str,
    query_tokens: tuple[str, ...],
    entry: MacroEntry,
) -> MacroMatchCandidate | None:
    best_match: tuple[
        float,
        str,
        Literal["exact_name", "exact_alias", "token_containment", "fuzzy"],
    ] | None = _score_candidate_term(
        query_normalized=query_normalized,
        query_tokens=query_tokens,
        candidate_text=entry.name,
        candidate_is_name=True,
    )

    for alias in entry.aliases:
        alias_score = _score_candidate_term(
            query_normalized=query_normalized,
            query_tokens=query_tokens,
            candidate_text=alias,
            candidate_is_name=False,
        )
        if alias_score is None:
            continue
        if best_match is None or alias_score[0] > best_match[0]:
            best_match = alias_score

    if best_match is None:
        return None

    return MacroMatchCandidate(
        entry=entry,
        score=best_match[0],
        matched_on=best_match[1],
        match_type=best_match[2],
    )


def match_food_name(
    query: str,
    *,
    limit: int = 5,
    min_score: float = 0.6,
) -> tuple[MacroMatchCandidate, ...]:
    """Return ranked USDA + personal catalog candidates for a food query."""
    if not isinstance(query, str):
        return ()
    if limit <= 0:
        return ()
    if not 0 <= min_score <= 1:
        raise ValueError("min_score must be within [0, 1]")

    query_normalized = _normalize_lookup_key(query)
    if not query_normalized:
        return ()
    query_tokens = _tokenize(query_normalized)
    if not query_tokens:
        return ()

    match_type_priority = {
        "exact_name": 0,
        "exact_alias": 1,
        "token_containment": 2,
        "fuzzy": 3,
    }

    matches: list[MacroMatchCandidate] = []
    for entry in _load_all_entries():
        candidate = _score_entry_match(
            query_normalized=query_normalized,
            query_tokens=query_tokens,
            entry=entry,
        )
        if candidate is None or candidate.score < min_score:
            continue
        matches.append(candidate)

    matches.sort(
        key=lambda candidate: (
            -candidate.score,
            0 if candidate.entry.source == "PERSONAL" else 1,
            match_type_priority[candidate.match_type],
            candidate.entry.id,
        )
    )
    return tuple(matches[:limit])


def find_macro_entry_candidates(
    query: str,
    *,
    limit: int = 5,
    min_score: float = 0.6,
) -> tuple[MacroMatchCandidate, ...]:
    """Alias for match_food_name for readability at call sites."""
    return match_food_name(query, limit=limit, min_score=min_score)


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
    "MacroMatchCandidate",
    "find_macro_entry",
    "find_macro_entry_candidates",
    "get_macro_entry",
    "get_macro_entry_by_name",
    "load_all_macro_entries",
    "load_macro_entries",
    "load_personal_macro_entries",
    "match_food_name",
]
