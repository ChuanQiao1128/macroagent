from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.nutrition import (
    MacroEntry,
    find_macro_entry,
    get_macro_entry,
    get_macro_entry_by_name,
    load_all_macro_entries,
    load_macro_entries,
)

REQUIRED_CATEGORIES = {
    "rice",
    "noodles",
    "bread",
    "chicken",
    "beef",
    "pork",
    "fish",
    "egg",
    "dairy",
    "legumes",
    "fruit",
    "vegetables",
    "nuts",
    "oils",
    "sauces",
}

EXPECTED_FIELDS = {
    "id",
    "name",
    "aliases",
    "category",
    "source",
    "kcal_per_100g",
    "protein_g_per_100g",
    "carbs_g_per_100g",
    "fat_g_per_100g",
}


def test_macro_entry_fields_are_stable() -> None:
    assert set(MacroEntry.model_fields) == EXPECTED_FIELDS


def test_seed_catalog_meets_minimum_coverage_and_source_constraints() -> None:
    entries = load_macro_entries()

    assert len(entries) >= 50
    assert all(entry.source == "USDA" for entry in entries)
    assert REQUIRED_CATEGORIES.issubset({entry.category for entry in entries})


def test_entry_ids_are_unique() -> None:
    entries = load_macro_entries()
    ids = [entry.id for entry in entries]

    assert len(ids) == len(set(ids))


def test_lookup_supports_exact_name_and_alias_case_insensitively() -> None:
    by_name = get_macro_entry("WHITE RICE, COOKED")
    assert by_name is not None
    assert by_name.id == "usda_seed_0001"

    by_alias = get_macro_entry("  CoOkEd   WhItE   RiCe ")
    assert by_alias is not None
    assert by_alias.id == "usda_seed_0001"


def test_lookup_is_exact_not_fuzzy() -> None:
    assert get_macro_entry("white") is None
    assert get_macro_entry("sirloin steak") is None


def test_lookup_alias_helpers_match_primary_lookup() -> None:
    target = "wholemeal bread"

    primary = get_macro_entry(target)
    assert primary is not None
    assert find_macro_entry(target) == primary
    assert get_macro_entry_by_name(target) == primary


def test_load_alias_helper_matches_primary_loader() -> None:
    assert load_all_macro_entries() == load_macro_entries()


def test_loaded_entries_are_immutable() -> None:
    entries = load_macro_entries()

    with pytest.raises(TypeError):
        entries[0] = entries[0]

    with pytest.raises(ValidationError):
        entries[0].name = "Mutated"
