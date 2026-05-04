from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from services.nutrition import (
    MacroEntry,
    find_macro_entry,
    get_macro_entry,
    get_macro_entry_by_name,
    load_all_macro_entries,
    load_fdc_macro_entries_for_query,
    load_macro_entries,
    load_personal_macro_entries,
    match_food_candidates,
    match_food_name,
)
from services.nutrition.src import food_data as food_data_module

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
    usda_entries = load_macro_entries()
    personal_entries = load_personal_macro_entries()
    all_entries = load_all_macro_entries()

    assert len(personal_entries) == 20
    assert all(entry.source == "PERSONAL" for entry in personal_entries)
    assert all_entries == (*usda_entries, *personal_entries)


def test_personal_seed_catalog_contains_expected_food_types() -> None:
    personal_entries = load_personal_macro_entries()
    searchable_values = " ".join(
        (
            entry.name
            + " "
            + " ".join(entry.aliases)
            + " "
            + entry.category
        ).casefold()
        for entry in personal_entries
    )

    expected_terms = {
        "fairlife",
        "whey",
        "yogurt",
        "egg",
        "coffee",
        "oats",
        "rice",
        "chicken",
        "tuna",
        "tofu",
        "fruit",
        "nuts",
        "oil",
    }
    for term in expected_terms:
        assert term in searchable_values


def test_macro_entry_source_accepts_personal_and_usda_only() -> None:
    payload = {
        "id": "seed_test",
        "name": "Test Food",
        "aliases": ["test alias"],
        "category": "test",
        "kcal_per_100g": 100,
        "protein_g_per_100g": 10,
        "carbs_g_per_100g": 20,
        "fat_g_per_100g": 5,
    }

    personal = MacroEntry.model_validate({**payload, "source": "PERSONAL"})
    usda = MacroEntry.model_validate({**payload, "source": "USDA"})

    assert personal.source == "PERSONAL"
    assert usda.source == "USDA"

    with pytest.raises(ValidationError):
        MacroEntry.model_validate({**payload, "source": "OTHER"})


def test_lookup_behavior_remains_usda_only() -> None:
    # TASK-005 keeps lookup behavior unchanged; personal catalog is not indexed yet.
    assert get_macro_entry("fairlife 2% milk") is None


def test_loaded_entries_are_immutable() -> None:
    entries = load_macro_entries()

    with pytest.raises(TypeError):
        entries[0] = entries[0]

    with pytest.raises(ValidationError):
        entries[0].name = "Mutated"


def test_match_food_name_supports_exact_usda_name_match() -> None:
    matches = match_food_name("White rice, cooked", limit=3)

    assert matches
    assert matches[0].entry.id == "usda_seed_0001"
    assert matches[0].entry.source == "USDA"
    assert matches[0].match_type == "exact_name"
    assert matches[0].matched_on == "White rice, cooked"
    assert matches[0].score == pytest.approx(1.0)


def test_match_food_name_supports_exact_personal_alias_match() -> None:
    matches = match_food_name("gold standard whey", limit=3)

    assert matches
    assert matches[0].entry.id == "personal_seed_0002"
    assert matches[0].entry.source == "PERSONAL"
    assert matches[0].match_type == "exact_alias"
    assert matches[0].matched_on == "gold standard whey"
    assert matches[0].score == pytest.approx(0.99)


def test_match_food_name_prefers_personal_entry_when_scores_tie() -> None:
    matches = match_food_name("bananna", limit=2, min_score=0.6)

    assert len(matches) == 2
    assert matches[0].score == pytest.approx(matches[1].score)
    assert matches[0].entry.source == "PERSONAL"
    assert matches[1].entry.source == "USDA"
    assert matches[0].entry.id == "personal_seed_0012"
    assert matches[1].entry.id == "usda_seed_0043"


def test_match_food_name_supports_fuzzy_typo_match() -> None:
    matches = match_food_name("brocoli", limit=3)

    assert matches
    assert matches[0].entry.id == "usda_seed_0048"
    assert matches[0].entry.source == "USDA"
    assert matches[0].match_type == "fuzzy"
    assert matches[0].matched_on == "broccoli"
    assert matches[0].score == pytest.approx(0.7467, abs=1e-4)


def test_match_food_name_applies_min_score_threshold() -> None:
    assert match_food_name("brocoli", min_score=0.7, limit=3)
    assert match_food_name("brocoli", min_score=0.8, limit=3) == ()


def test_match_food_candidates_personal_high_score_tie_gets_priority_bonus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    usda_entry = MacroEntry.model_validate(
        {
            "id": "usda_test_0001",
            "name": "banana standard",
            "aliases": [],
            "category": "fruit",
            "source": "USDA",
            "kcal_per_100g": 89,
            "protein_g_per_100g": 1.1,
            "carbs_g_per_100g": 22.8,
            "fat_g_per_100g": 0.3,
        }
    )
    personal_entry = MacroEntry.model_validate(
        {
            "id": "personal_test_0001",
            "name": "banana personal",
            "aliases": [],
            "category": "fruit",
            "source": "PERSONAL",
            "kcal_per_100g": 89,
            "protein_g_per_100g": 1.1,
            "carbs_g_per_100g": 22.8,
            "fat_g_per_100g": 0.3,
        }
    )
    monkeypatch.setattr(
        food_data_module,
        "_load_all_entries",
        lambda: (usda_entry, personal_entry),
    )

    matches = match_food_candidates([("banana", 0.93)], limit=2, min_score=0.6)

    assert len(matches) == 2
    assert matches[0].entry.id == "personal_test_0001"
    assert matches[0].entry.source == "PERSONAL"
    assert matches[0].score == pytest.approx(matches[1].score)
    assert "personal priority bonus +0.015 applied" in matches[0].reason


def test_match_food_candidates_personal_state_conflict_loses_to_usda(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    usda_entry = MacroEntry.model_validate(
        {
            "id": "usda_test_0002",
            "name": "Chicken breast, grilled",
            "aliases": ["chicken breast"],
            "category": "chicken",
            "source": "USDA",
            "kcal_per_100g": 170,
            "protein_g_per_100g": 31.0,
            "carbs_g_per_100g": 0.0,
            "fat_g_per_100g": 4.0,
        }
    )
    personal_entry = MacroEntry.model_validate(
        {
            "id": "personal_test_0002",
            "name": "Chicken breast, fried",
            "aliases": ["chicken breast"],
            "category": "chicken",
            "source": "PERSONAL",
            "kcal_per_100g": 230,
            "protein_g_per_100g": 28.0,
            "carbs_g_per_100g": 4.0,
            "fat_g_per_100g": 12.0,
        }
    )
    monkeypatch.setattr(
        food_data_module,
        "_load_all_entries",
        lambda: (usda_entry, personal_entry),
    )

    matches = match_food_candidates(
        [("chicken breast", 0.95)],
        state_hints=[("grilled", 0.95)],
        limit=2,
        min_score=0.6,
    )

    assert len(matches) == 2
    assert matches[0].entry.id == "usda_test_0002"
    assert matches[0].entry.source == "USDA"
    assert matches[1].entry.id == "personal_test_0002"
    assert "state conflict:" in matches[1].reason
    assert "personal priority bonus skipped (state conflict)" in matches[1].reason


@pytest.mark.parametrize(
    ("query", "state_hint", "usda_name", "personal_name", "expected_top_source"),
    (
        (
            "chicken breast",
            "grilled",
            "Chicken breast, grilled",
            "Chicken breast, fried",
            "USDA",
        ),
        (
            "chicken breast",
            "fried",
            "Chicken breast, grilled",
            "Chicken breast, fried",
            "PERSONAL",
        ),
        (
            "chicken breast",
            "boiled",
            "Chicken breast, boiled",
            "Chicken breast, fried",
            "USDA",
        ),
        (
            "salmon fillet",
            "raw",
            "Salmon fillet, cooked",
            "Salmon fillet, raw",
            "PERSONAL",
        ),
        (
            "salmon fillet",
            "cooked",
            "Salmon fillet, cooked",
            "Salmon fillet, raw",
            "USDA",
        ),
        (
            "pasta",
            "plain",
            "Pasta, plain",
            "Pasta, sauced",
            "USDA",
        ),
        (
            "pasta",
            "sauced",
            "Pasta, plain",
            "Pasta, sauced",
            "PERSONAL",
        ),
    ),
)
def test_match_food_candidates_state_hints_cover_supported_state_labels(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
    state_hint: str,
    usda_name: str,
    personal_name: str,
    expected_top_source: str,
) -> None:
    usda_entry = MacroEntry.model_validate(
        {
            "id": "state_usda",
            "name": usda_name,
            "aliases": [query],
            "category": "test",
            "source": "USDA",
            "kcal_per_100g": 100,
            "protein_g_per_100g": 10.0,
            "carbs_g_per_100g": 10.0,
            "fat_g_per_100g": 10.0,
        }
    )
    personal_entry = MacroEntry.model_validate(
        {
            "id": "state_personal",
            "name": personal_name,
            "aliases": [query],
            "category": "test",
            "source": "PERSONAL",
            "kcal_per_100g": 100,
            "protein_g_per_100g": 10.0,
            "carbs_g_per_100g": 10.0,
            "fat_g_per_100g": 10.0,
        }
    )
    monkeypatch.setattr(
        food_data_module,
        "_load_all_entries",
        lambda: (usda_entry, personal_entry),
    )

    matches = match_food_candidates(
        [(query, 0.95)],
        state_hints=[(state_hint, 0.95)],
        limit=2,
        min_score=0.6,
    )

    assert len(matches) == 2
    assert matches[0].entry.source == expected_top_source
    assert f"state hints observed: {state_hint}" in matches[0].reason


@pytest.mark.parametrize(
    ("personal_name", "personal_aliases"),
    (
        ("banana low confidence tracker", ["banana"]),
        ("banana archived tracker", ["banana"]),
    ),
)
def test_match_food_candidates_personal_low_confidence_or_stale_skips_priority_bonus(
    monkeypatch: pytest.MonkeyPatch,
    personal_name: str,
    personal_aliases: list[str],
) -> None:
    usda_entry = MacroEntry.model_validate(
        {
            "id": "a_usda_test_0003",
            "name": "banana usda tracker",
            "aliases": ["banana"],
            "category": "fruit",
            "source": "USDA",
            "kcal_per_100g": 89,
            "protein_g_per_100g": 1.1,
            "carbs_g_per_100g": 22.8,
            "fat_g_per_100g": 0.3,
        }
    )
    personal_entry = MacroEntry.model_validate(
        {
            "id": "z_personal_test_0003",
            "name": personal_name,
            "aliases": personal_aliases,
            "category": "fruit",
            "source": "PERSONAL",
            "kcal_per_100g": 89,
            "protein_g_per_100g": 1.1,
            "carbs_g_per_100g": 22.8,
            "fat_g_per_100g": 0.3,
        }
    )
    monkeypatch.setattr(
        food_data_module,
        "_load_all_entries",
        lambda: (usda_entry, personal_entry),
    )

    matches = match_food_candidates([("banana", 0.95)], limit=2, min_score=0.6)

    assert len(matches) == 2
    assert matches[0].entry.id == "a_usda_test_0003"
    assert matches[1].entry.id == "z_personal_test_0003"
    assert matches[1].match_type == "exact_alias"
    assert matches[1].score == pytest.approx(0.99)
    assert "personal priority bonus skipped (entry marked low confidence or stale)" in matches[
        1
    ].reason
    assert "personal priority bonus +0.015 applied" not in matches[1].reason


def test_match_food_candidates_personal_low_text_score_skips_priority_bonus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    usda_entry = MacroEntry.model_validate(
        {
            "id": "a_usda_test_0004",
            "name": "banana usda tracker",
            "aliases": [],
            "category": "fruit",
            "source": "USDA",
            "kcal_per_100g": 89,
            "protein_g_per_100g": 1.1,
            "carbs_g_per_100g": 22.8,
            "fat_g_per_100g": 0.3,
        }
    )
    personal_entry = MacroEntry.model_validate(
        {
            "id": "z_personal_test_0004",
            "name": "banana personal tracker",
            "aliases": [],
            "category": "fruit",
            "source": "PERSONAL",
            "kcal_per_100g": 89,
            "protein_g_per_100g": 1.1,
            "carbs_g_per_100g": 22.8,
            "fat_g_per_100g": 0.3,
        }
    )
    monkeypatch.setattr(
        food_data_module,
        "_load_all_entries",
        lambda: (usda_entry, personal_entry),
    )

    matches = match_food_candidates([("banana", 0.91)], limit=2, min_score=0.6)

    assert len(matches) == 2
    assert matches[0].entry.id == "a_usda_test_0004"
    assert matches[1].entry.id == "z_personal_test_0004"
    assert matches[1].match_type == "token_containment"
    assert matches[1].score == pytest.approx(0.8333333333, abs=1e-10)
    assert "personal priority bonus skipped (text score 0.833 below 0.86)" in matches[1].reason
    assert "personal priority bonus +0.015 applied" not in matches[1].reason


def test_match_food_candidates_falls_back_to_later_top_k_vision_candidate() -> None:
    matches = match_food_candidates(
        [("mystery foam", 0.98), ("banana", 0.62)],
        limit=3,
        min_score=0.6,
    )

    assert matches
    assert matches[0].entry.id == "personal_seed_0012"
    assert matches[0].matched_on == "banana"
    assert "matched via vision candidate 'banana' (confidence=0.62)" in matches[0].reason


def test_match_food_candidates_ignores_very_low_confidence_vision_candidates() -> None:
    matches = match_food_candidates([("avocado residue", 0.05)], limit=3, min_score=0.6)

    assert matches == ()


def test_match_food_candidates_uses_fdc_when_local_catalog_misses(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("FDC_LOOKUP_ENABLED", "1")
    monkeypatch.setenv("FDC_API_KEY", "fdc-test-key")
    monkeypatch.setenv("FDC_CACHE_PATH", str(tmp_path / "fdc_cache.json"))

    def fake_fetch_fdc_search_payload(*, query: str, api_key: str) -> dict[str, object]:
        assert api_key == "fdc-test-key"
        return _fdc_sushi_payload() if query == "spicy tuna maki roll" else {"foods": []}

    monkeypatch.setattr(
        food_data_module,
        "_fetch_fdc_search_payload",
        fake_fetch_fdc_search_payload,
    )

    matches = match_food_candidates(
        [("spicy tuna maki roll", 0.68)],
        limit=3,
        min_score=0.6,
    )

    assert matches
    assert matches[0].entry.id == "fdc:234567"
    assert matches[0].entry.source == "USDA"
    assert matches[0].entry.kcal_per_100g == pytest.approx(145.0)
    assert matches[0].entry.protein_g_per_100g == pytest.approx(5.2)
    assert matches[0].score >= 0.70
    assert "matched via FDC query 'spicy tuna maki roll'" in matches[0].reason


def test_match_food_candidates_cleans_fdc_query_for_sugar_packet(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("FDC_LOOKUP_ENABLED", "1")
    monkeypatch.setenv("FDC_API_KEY", "fdc-test-key")
    monkeypatch.setenv("FDC_CACHE_PATH", str(tmp_path / "fdc_cache.json"))
    seen_queries: list[str] = []

    def fake_fetch_fdc_search_payload(*, query: str, api_key: str) -> dict[str, object]:
        del api_key
        seen_queries.append(query)
        return _fdc_sugar_payload() if query == "granulated sugar" else {"foods": []}

    monkeypatch.setattr(
        food_data_module,
        "_fetch_fdc_search_payload",
        fake_fetch_fdc_search_payload,
    )

    matches = match_food_candidates(
        [("White granulated sugar stick (~4 g)", 0.95)],
        limit=3,
        min_score=0.6,
    )

    assert "granulated sugar" in seen_queries
    assert matches
    assert matches[0].entry.id == "fdc:999001"
    assert matches[0].entry.name == "Sugars, granulated"
    assert "matched via FDC query 'granulated sugar'" in matches[0].reason


def test_match_food_candidates_does_not_search_fdc_when_local_match_is_confident(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("FDC_LOOKUP_ENABLED", "1")
    monkeypatch.setenv("FDC_API_KEY", "fdc-test-key")
    monkeypatch.setenv("FDC_CACHE_PATH", str(tmp_path / "fdc_cache.json"))

    def fail_fetch_fdc_search_payload(*, query: str, api_key: str) -> dict[str, object]:
        raise AssertionError(f"unexpected FDC lookup for {query} with {api_key}")

    monkeypatch.setattr(
        food_data_module,
        "_fetch_fdc_search_payload",
        fail_fetch_fdc_search_payload,
    )

    matches = match_food_candidates(
        [("americano", 0.90), ("drip coffee", 0.20)],
        limit=3,
        min_score=0.6,
    )

    assert matches
    assert matches[0].entry.id == "personal_seed_0005"
    assert matches[0].entry.name == "Coffee, brewed, black"


def test_load_fdc_macro_entries_for_query_uses_persistent_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("FDC_LOOKUP_ENABLED", "1")
    monkeypatch.setenv("FDC_API_KEY", "fdc-test-key")
    monkeypatch.setenv("FDC_CACHE_PATH", str(tmp_path / "fdc_cache.json"))
    calls = {"count": 0}

    def fake_fetch_fdc_search_payload(*, query: str, api_key: str) -> dict[str, object]:
        del query, api_key
        calls["count"] += 1
        return _fdc_sugar_payload()

    monkeypatch.setattr(
        food_data_module,
        "_fetch_fdc_search_payload",
        fake_fetch_fdc_search_payload,
    )

    first = load_fdc_macro_entries_for_query("white sugar packet")
    second = load_fdc_macro_entries_for_query("white sugar packet")

    assert calls["count"] == 1
    assert first == second
    assert first[0].id == "fdc:999001"
    assert first[0].name == "Sugars, granulated"
    assert (tmp_path / "fdc_cache.json").exists()


def test_match_food_candidates_reason_includes_state_and_candidate_trace() -> None:
    matches = match_food_candidates(
        [("chicken breast", 0.90)],
        state_hints=[("grilled", 0.92)],
        limit=3,
        min_score=0.6,
    )

    assert matches
    reason = matches[0].reason
    assert "matched via vision candidate 'chicken breast' (confidence=0.90)" in reason
    assert "state hints observed: grilled" in reason
    assert (
        "state aligned on " in reason
        or "state conflict:" in reason
        or "no state adjustment" in reason
    )


def test_match_food_name_legacy_behavior_does_not_include_state_aware_reason_trace() -> None:
    matches = match_food_name("banana", limit=2, min_score=0.6)

    assert len(matches) == 2
    assert matches[0].entry.id == "personal_seed_0012"
    assert matches[0].match_type == "exact_alias"
    assert "matched via vision candidate" not in matches[0].reason
    assert "state hints observed:" not in matches[0].reason


def _fdc_sushi_payload() -> dict[str, object]:
    return {
        "foods": [
            {
                "fdcId": 234567,
                "description": "Sushi roll, tuna",
                "lowercaseDescription": "sushi roll tuna",
                "dataType": "Survey (FNDDS)",
                "foodNutrients": [
                    {
                        "nutrientId": 1008,
                        "nutrientNumber": "208",
                        "nutrientName": "Energy",
                        "unitName": "KCAL",
                        "value": 145.0,
                    },
                    {
                        "nutrientId": 1003,
                        "nutrientNumber": "203",
                        "nutrientName": "Protein",
                        "unitName": "G",
                        "value": 5.2,
                    },
                    {
                        "nutrientId": 1005,
                        "nutrientNumber": "205",
                        "nutrientName": "Carbohydrate, by difference",
                        "unitName": "G",
                        "value": 27.8,
                    },
                    {
                        "nutrientId": 1004,
                        "nutrientNumber": "204",
                        "nutrientName": "Total lipid (fat)",
                        "unitName": "G",
                        "value": 2.1,
                    },
                ],
            }
        ]
    }


def _fdc_sugar_payload() -> dict[str, object]:
    return {
        "foods": [
            {
                "fdcId": 999001,
                "description": "Sugars, granulated",
                "lowercaseDescription": "sugars granulated",
                "dataType": "SR Legacy",
                "foodNutrients": [
                    {
                        "nutrientId": 1008,
                        "nutrientNumber": "208",
                        "nutrientName": "Energy",
                        "unitName": "KCAL",
                        "value": 387.0,
                    },
                    {
                        "nutrientId": 1003,
                        "nutrientNumber": "203",
                        "nutrientName": "Protein",
                        "unitName": "G",
                        "value": 0.0,
                    },
                    {
                        "nutrientId": 1005,
                        "nutrientNumber": "205",
                        "nutrientName": "Carbohydrate, by difference",
                        "unitName": "G",
                        "value": 100.0,
                    },
                    {
                        "nutrientId": 1004,
                        "nutrientNumber": "204",
                        "nutrientName": "Total lipid (fat)",
                        "unitName": "G",
                        "value": 0.0,
                    },
                ],
            }
        ]
    }
