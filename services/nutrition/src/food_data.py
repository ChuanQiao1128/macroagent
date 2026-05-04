from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
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

MatchType = Literal["exact_name", "exact_alias", "token_containment", "fuzzy"]
StateLabel = Literal["cooked", "raw", "fried", "grilled", "boiled", "plain", "sauced"]
MatchInputCandidate = tuple[str, float] | str
StateSignalInput = tuple[str, float] | str

MATCH_TYPE_PRIORITY: MappingProxyType[MatchType, int] = MappingProxyType(
    {
        "exact_name": 0,
        "exact_alias": 1,
        "token_containment": 2,
        "fuzzy": 3,
    }
)
PERSONAL_PRIORITY_BONUS = 0.015
PERSONAL_PRIORITY_MIN_SCORE = 0.86
STATE_ALIGNMENT_BONUS = 0.04
STATE_CONFLICT_PENALTY = 0.18
STATE_SIGNAL_THRESHOLD = 0.45
QUERY_DERIVED_STATE_FLOOR = 0.40

LOW_CONFIDENCE_MARKERS = (
    "low confidence",
    "uncertain",
    "estimated",
    "estimate",
    "approx",
)
STALE_MARKERS = (
    "stale",
    "deprecated",
    "archived",
    "obsolete",
    "old entry",
)
KNOWN_STATES = frozenset({"cooked", "raw", "fried", "grilled", "boiled", "plain", "sauced"})

COOKED_TEXT_MARKERS = frozenset(
    {
        "cooked",
        "roasted",
        "baked",
        "braised",
        "seared",
        "steamed",
        "sauteed",
        "simmered",
        "poached",
    }
)
FRIED_TEXT_MARKERS = frozenset({"fried"})
GRILLED_TEXT_MARKERS = frozenset({"grilled", "barbecued", "chargrilled", "bbq"})
BOILED_TEXT_MARKERS = frozenset({"boiled"})
RAW_TEXT_MARKERS = frozenset({"raw", "fresh"})
PLAIN_TEXT_MARKERS = frozenset({"plain", "unsauced"})
SAUCED_TEXT_MARKERS = frozenset(
    {
        "sauce",
        "sauced",
        "glaze",
        "glazed",
        "gravy",
        "dressing",
        "curry",
    }
)
METHOD_STATES = frozenset({"fried", "grilled", "boiled"})


@dataclass(frozen=True)
class _QueryCandidate:
    text: str
    normalized: str
    tokens: tuple[str, ...]
    confidence: float


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
    match_type: MatchType
    reason: str = Field(..., min_length=1)


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
) -> tuple[float, str, MatchType] | None:
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
        MatchType,
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
        reason=_build_text_match_reason(match_type=best_match[2], matched_on=best_match[1]),
    )


def _build_text_match_reason(*, match_type: MatchType, matched_on: str) -> str:
    prefix = {
        "exact_name": "exact name match",
        "exact_alias": "exact alias match",
        "token_containment": "token containment match",
        "fuzzy": "fuzzy match",
    }[match_type]
    return f"{prefix} on '{matched_on}'"


def _legacy_match_sort_key(candidate: MacroMatchCandidate) -> tuple[float, int, int, str]:
    # Legacy behavior intentionally prioritizes personal entries when scores tie.
    return (
        -candidate.score,
        0 if candidate.entry.source == "PERSONAL" else 1,
        MATCH_TYPE_PRIORITY[candidate.match_type],
        candidate.entry.id,
    )


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalize_query_candidates(
    query_candidates: Sequence[MatchInputCandidate],
) -> tuple[_QueryCandidate, ...]:
    deduped: dict[str, _QueryCandidate] = {}
    for raw_candidate in query_candidates:
        candidate = _parse_query_candidate(raw_candidate)
        if candidate is None:
            continue
        existing = deduped.get(candidate.normalized)
        if existing is None or candidate.confidence > existing.confidence:
            deduped[candidate.normalized] = candidate
    return tuple(deduped.values())


def _parse_query_candidate(raw_candidate: MatchInputCandidate) -> _QueryCandidate | None:
    if isinstance(raw_candidate, str):
        text = raw_candidate
        confidence = 1.0
    elif (
        isinstance(raw_candidate, tuple)
        and len(raw_candidate) == 2
        and isinstance(raw_candidate[0], str)
    ):
        text = raw_candidate[0]
        confidence = _parse_confidence(raw_candidate[1], fallback=1.0)
    else:
        return None

    normalized = _normalize_lookup_key(text)
    if not normalized:
        return None
    tokens = _tokenize(normalized)
    if not tokens:
        return None
    return _QueryCandidate(
        text=normalized,
        normalized=normalized,
        tokens=tokens,
        confidence=confidence,
    )


def _parse_confidence(value: object, *, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return _clamp_score(parsed)


def _normalize_state_signals(
    *,
    state_hints: Sequence[StateSignalInput],
) -> tuple[frozenset[StateLabel], str]:
    signals: dict[StateLabel, float] = {}

    for raw_hint in state_hints:
        hint_state, hint_confidence = _parse_state_signal(raw_hint)
        if hint_state is None:
            continue
        signals[hint_state] = max(signals.get(hint_state, 0.0), hint_confidence)

    observed_states = frozenset(
        state for state, confidence in signals.items() if confidence >= STATE_SIGNAL_THRESHOLD
    )
    if not observed_states:
        return observed_states, "no strong state hints present"
    state_text = ", ".join(sorted(observed_states))
    return observed_states, f"state hints observed: {state_text}"


def _derived_candidate_state_signals(
    query_candidate: _QueryCandidate,
) -> frozenset[StateLabel]:
    derived_states = _extract_states_from_text(query_candidate.normalized)
    if not derived_states:
        return frozenset()

    derived_confidence = max(
        QUERY_DERIVED_STATE_FLOOR,
        query_candidate.confidence * 0.75,
    )
    if derived_confidence < STATE_SIGNAL_THRESHOLD:
        return frozenset()
    return derived_states


def _merge_observed_states(
    *,
    state_hints: frozenset[StateLabel],
    candidate_states: frozenset[StateLabel],
) -> tuple[frozenset[StateLabel], str]:
    observed_states = state_hints | candidate_states
    if not observed_states:
        return observed_states, "no strong state hints present"
    state_text = ", ".join(sorted(observed_states))
    return observed_states, f"state hints observed: {state_text}"


def _parse_state_signal(raw_hint: StateSignalInput) -> tuple[StateLabel | None, float]:
    if isinstance(raw_hint, str):
        normalized_state = _normalize_state_label(raw_hint)
        return normalized_state, 1.0 if normalized_state is not None else 0.0

    if (
        isinstance(raw_hint, tuple)
        and len(raw_hint) == 2
        and isinstance(raw_hint[0], str)
    ):
        normalized_state = _normalize_state_label(raw_hint[0])
        return normalized_state, _parse_confidence(raw_hint[1], fallback=1.0)

    return None, 0.0


def _normalize_state_label(value: str) -> StateLabel | None:
    normalized = _normalize_lookup_key(value)
    if normalized in KNOWN_STATES:
        return normalized
    return None


def _extract_states_from_text(value: str) -> frozenset[StateLabel]:
    normalized = _normalize_lookup_key(value)
    if not normalized:
        return frozenset()
    tokens = frozenset(_tokenize(normalized))
    states: set[StateLabel] = set()

    if tokens & RAW_TEXT_MARKERS:
        states.add("raw")

    if tokens & COOKED_TEXT_MARKERS:
        states.add("cooked")

    if tokens & FRIED_TEXT_MARKERS:
        states.add("fried")
        states.add("cooked")

    if tokens & GRILLED_TEXT_MARKERS:
        states.add("grilled")
        states.add("cooked")

    if tokens & BOILED_TEXT_MARKERS:
        states.add("boiled")
        states.add("cooked")

    if tokens & PLAIN_TEXT_MARKERS:
        states.add("plain")
    if {"no", "sauce"} <= tokens:
        states.add("plain")

    if tokens & SAUCED_TEXT_MARKERS:
        states.add("sauced")

    return frozenset(states)


def _extract_entry_states(entry: MacroEntry) -> frozenset[StateLabel]:
    states = set(_extract_states_from_text(entry.name))
    for alias in entry.aliases:
        states.update(_extract_states_from_text(alias))
    return frozenset(states)


def _expand_cooked_state_family(states: frozenset[StateLabel]) -> frozenset[StateLabel]:
    if states & METHOD_STATES and "cooked" not in states:
        return frozenset((*states, "cooked"))
    return states


def _evaluate_state_alignment(
    *,
    observed_states: frozenset[StateLabel],
    entry_states: frozenset[StateLabel],
) -> tuple[float, str, bool]:
    if not observed_states:
        return 0.0, "no state adjustment applied", False
    if not entry_states:
        observed_text = ", ".join(sorted(observed_states))
        return 0.0, f"entry has no explicit state tags; observed {observed_text}", False

    normalized_observed_states = _expand_cooked_state_family(observed_states)
    normalized_entry_states = _expand_cooked_state_family(entry_states)

    conflicts: list[str] = []
    if "raw" in normalized_observed_states and "cooked" in normalized_entry_states:
        conflicts.append("observed raw vs entry cooked")
    if "cooked" in normalized_observed_states and "raw" in normalized_entry_states:
        conflicts.append("observed cooked vs entry raw")

    observed_methods = normalized_observed_states & METHOD_STATES
    entry_methods = normalized_entry_states & METHOD_STATES
    if observed_methods and entry_methods and observed_methods.isdisjoint(entry_methods):
        conflicts.append(
            "observed prep "
            f"{'/'.join(sorted(observed_methods))} vs entry prep {'/'.join(sorted(entry_methods))}"
        )

    if "plain" in normalized_observed_states and "sauced" in normalized_entry_states:
        conflicts.append("observed plain vs entry sauced")
    if "sauced" in normalized_observed_states and "plain" in normalized_entry_states:
        conflicts.append("observed sauced vs entry plain")

    if conflicts:
        return (
            -STATE_CONFLICT_PENALTY,
            "state conflict: " + "; ".join(conflicts),
            True,
        )

    aligned_states = normalized_observed_states & normalized_entry_states
    if aligned_states:
        aligned_text = ", ".join(sorted(aligned_states))
        return STATE_ALIGNMENT_BONUS, f"state aligned on {aligned_text}", False

    if ("cooked" in normalized_observed_states and entry_methods) or (
        "cooked" in normalized_entry_states and observed_methods
    ):
        return STATE_ALIGNMENT_BONUS, "state aligned on cooked-preparation family", False

    observed_text = ", ".join(sorted(normalized_observed_states))
    entry_text = ", ".join(sorted(normalized_entry_states))
    return (
        0.0,
        f"state hints ({observed_text}) differ from entry tags ({entry_text}); no state adjustment",
        False,
    )


def _entry_marked_low_confidence_or_stale(entry: MacroEntry) -> bool:
    searchable_text = " ".join((entry.name, *entry.aliases)).casefold()
    return any(marker in searchable_text for marker in LOW_CONFIDENCE_MARKERS) or any(
        marker in searchable_text for marker in STALE_MARKERS
    )


def match_food_candidates(
    query_candidates: Sequence[MatchInputCandidate],
    *,
    state_hints: Sequence[StateSignalInput] = (),
    limit: int = 5,
    min_score: float = 0.6,
) -> tuple[MacroMatchCandidate, ...]:
    """
    Match nutrition entries from multiple vision candidates with optional state-aware reranking.

    This is the state-aware counterpart to ``match_food_name`` for structured vision flows.
    """
    if limit <= 0:
        return ()
    if not 0 <= min_score <= 1:
        raise ValueError("min_score must be within [0, 1]")

    normalized_candidates = _normalize_query_candidates(query_candidates)
    if not normalized_candidates:
        return ()

    hinted_states, _ = _normalize_state_signals(
        state_hints=state_hints,
    )

    ranked_matches: list[tuple[float, MacroMatchCandidate]] = []
    for entry in _load_all_entries():
        entry_states = _extract_entry_states(entry)
        best_text_match: MacroMatchCandidate | None = None
        best_query_text = ""
        best_query_confidence = 0.0
        best_query_metric = -1.0
        best_state_adjustment = 0.0
        best_state_reason = "no state adjustment applied"
        best_state_conflict = False
        best_state_signal_reason = "no strong state hints present"

        for query_candidate in normalized_candidates:
            text_match = _score_entry_match(
                query_normalized=query_candidate.normalized,
                query_tokens=query_candidate.tokens,
                entry=entry,
            )
            if text_match is None or text_match.score < min_score:
                continue

            candidate_states = _derived_candidate_state_signals(query_candidate)
            observed_states, state_signal_reason = _merge_observed_states(
                state_hints=hinted_states,
                candidate_states=candidate_states,
            )
            state_adjustment, state_reason, state_conflict = _evaluate_state_alignment(
                observed_states=observed_states,
                entry_states=entry_states,
            )
            query_metric = (
                text_match.score + state_adjustment + (0.02 * query_candidate.confidence)
            )
            if query_metric <= best_query_metric:
                continue
            best_query_metric = query_metric
            best_text_match = text_match
            best_query_text = query_candidate.text
            best_query_confidence = query_candidate.confidence
            best_state_adjustment = state_adjustment
            best_state_reason = state_reason
            best_state_conflict = state_conflict
            best_state_signal_reason = state_signal_reason

        if best_text_match is None:
            continue

        final_score = _clamp_score(best_text_match.score + best_state_adjustment)
        ranking_score = final_score

        reason_parts = [
            best_text_match.reason,
            (
                "matched via vision candidate "
                f"'{best_query_text}' (confidence={best_query_confidence:.2f})"
            ),
            best_state_signal_reason,
            best_state_reason,
        ]

        if entry.source == "PERSONAL":
            if _entry_marked_low_confidence_or_stale(entry):
                reason_parts.append(
                    "personal priority bonus skipped (entry marked low confidence or stale)"
                )
            elif best_text_match.score < PERSONAL_PRIORITY_MIN_SCORE:
                reason_parts.append(
                    "personal priority bonus skipped "
                    + (
                        f"(text score {best_text_match.score:.3f} "
                        f"below {PERSONAL_PRIORITY_MIN_SCORE:.2f})"
                    )
                )
            elif best_state_conflict:
                reason_parts.append("personal priority bonus skipped (state conflict)")
            else:
                ranking_score = _clamp_score(ranking_score + PERSONAL_PRIORITY_BONUS)
                reason_parts.append(
                    f"personal priority bonus +{PERSONAL_PRIORITY_BONUS:.3f} applied"
                )

        if final_score < min_score:
            continue

        ranked_matches.append(
            (
                ranking_score,
                MacroMatchCandidate(
                    entry=entry,
                    score=final_score,
                    matched_on=best_text_match.matched_on,
                    match_type=best_text_match.match_type,
                    reason="; ".join(part for part in reason_parts if part),
                ),
            )
        )

    ranked_matches.sort(
        key=lambda item: (
            -item[0],
            MATCH_TYPE_PRIORITY[item[1].match_type],
            item[1].entry.id,
        )
    )
    return tuple(candidate for _, candidate in ranked_matches[:limit])


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

    matches.sort(key=_legacy_match_sort_key)
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
    "match_food_candidates",
    "match_food_name",
]
