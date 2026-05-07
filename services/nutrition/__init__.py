from services.nutrition.src.food_data import (
    MacroEntry,
    MacroMatchCandidate,
    NutritionEntry,
    find_macro_entry,
    find_macro_entry_candidates,
    get_macro_entry,
    get_macro_entry_by_name,
    load_all_macro_entries,
    load_fdc_macro_entries_for_query,
    load_macro_entries,
    load_personal_macro_entries,
    match_food_candidates,
    match_food_name,
)
from services.nutrition.src.portion_parser import (
    PortionGramRange,
    parse_component_portion_range,
    parse_portion_range,
)
from services.nutrition.src.version_metadata import (
    MATCHER_VERSION,
    NUTRITION_CATALOG_VERSION,
    PORTION_ENGINE_VERSION,
)
from services.nutrition.src.volume_portion import (
    DensityProfile,
    VolumeEstimate,
    estimate_portion_from_volume,
    parse_volume_portion_range,
    resolve_density_profile,
)

_FDC_LOCAL_EXPORTS = frozenset(
    {
        "FDC_LOCAL_DB_PATH_ENV",
        "FDC_LOCAL_DEFAULT_DB_PATH",
        "FDC_LOCAL_LOOKUP_ENABLED_ENV",
        "FdcLocalImportResult",
        "build_fdc_local_database",
        "fdc_local_database_available",
        "load_fdc_local_entries_for_query",
    }
)

__all__ = [
    "MacroEntry",
    "MacroMatchCandidate",
    "FDC_LOCAL_DB_PATH_ENV",
    "FDC_LOCAL_DEFAULT_DB_PATH",
    "FDC_LOCAL_LOOKUP_ENABLED_ENV",
    "FdcLocalImportResult",
    "DensityProfile",
    "MATCHER_VERSION",
    "NUTRITION_CATALOG_VERSION",
    "NutritionEntry",
    "PortionGramRange",
    "PORTION_ENGINE_VERSION",
    "VolumeEstimate",
    "build_fdc_local_database",
    "estimate_portion_from_volume",
    "fdc_local_database_available",
    "find_macro_entry",
    "find_macro_entry_candidates",
    "get_macro_entry",
    "get_macro_entry_by_name",
    "load_all_macro_entries",
    "load_fdc_local_entries_for_query",
    "load_fdc_macro_entries_for_query",
    "load_macro_entries",
    "load_personal_macro_entries",
    "match_food_candidates",
    "match_food_name",
    "parse_component_portion_range",
    "parse_portion_range",
    "parse_volume_portion_range",
    "resolve_density_profile",
]


def __getattr__(name: str) -> object:
    if name in _FDC_LOCAL_EXPORTS:
        from services.nutrition.src import fdc_local

        return getattr(fdc_local, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
