from __future__ import annotations

import re
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_FALLBACK_RANGE_GRAMS = (60.0, 350.0)
_APPROX_WORDS = frozenset({"about", "around", "approx", "approximately", "roughly"})
_WINDOW_FILLER_WORDS = _APPROX_WORDS | {"of", "the"}

_NUMBER_WORDS = MappingProxyType(
    {
        "a": 1.0,
        "an": 1.0,
        "one": 1.0,
        "two": 2.0,
        "three": 3.0,
        "four": 4.0,
        "five": 5.0,
        "six": 6.0,
        "seven": 7.0,
        "eight": 8.0,
        "nine": 9.0,
        "ten": 10.0,
    }
)
_FRACTION_WORDS = MappingProxyType(
    {
        "half": 0.5,
        "halves": 0.5,
        "quarter": 0.25,
        "quarters": 0.25,
        "third": 1.0 / 3.0,
        "thirds": 1.0 / 3.0,
    }
)
_SPECIAL_WORD_QUANTITIES = MappingProxyType(
    {
        "half": 0.5,
        "a half": 0.5,
        "one half": 0.5,
        "quarter": 0.25,
        "a quarter": 0.25,
        "one quarter": 0.25,
        "three quarter": 0.75,
        "three quarters": 0.75,
    }
)

_TOKEN_TO_UNIT = MappingProxyType(
    {
        "g": "gram",
        "gram": "gram",
        "grams": "gram",
        "kg": "kilogram",
        "kgs": "kilogram",
        "kilogram": "kilogram",
        "kilograms": "kilogram",
        "kilo": "kilogram",
        "kilos": "kilogram",
        "cup": "cup",
        "cups": "cup",
        "bowl": "bowl",
        "bowls": "bowl",
        "plate": "plate",
        "plates": "plate",
        "slice": "slice",
        "slices": "slice",
        "piece": "piece",
        "pieces": "piece",
        "egg": "egg",
        "eggs": "egg",
        "scoop": "scoop",
        "scoops": "scoop",
        "tablespoon": "tablespoon",
        "tablespoons": "tablespoon",
        "tbsp": "tablespoon",
        "tbs": "tablespoon",
        "teaspoon": "teaspoon",
        "teaspoons": "teaspoon",
        "tsp": "teaspoon",
        "palm": "palm",
        "palms": "palm",
    }
)

_HOUSEHOLD_UNIT_GRAMS = MappingProxyType(
    {
        "cup": (120.0, 260.0),
        "bowl": (240.0, 600.0),
        "plate": (280.0, 700.0),
        "slice": (18.0, 90.0),
        "piece": (25.0, 180.0),
        "egg": (40.0, 75.0),
        "scoop": (20.0, 50.0),
        "tablespoon": (10.0, 20.0),
        "teaspoon": (3.0, 8.0),
        "palm": (75.0, 150.0),
    }
)
_SUSHI_PIECE_RANGE_GRAMS = (22.0, 45.0)

_WEIGHT_UNITS = frozenset({"gram", "kilogram"})
PortionUncertaintyFlag = Literal[
    "missing_portion_hint",
    "unknown_portion_hint",
    "non_positive_quantity",
    "implicit_quantity",
    "approximate_quantity",
    "volume_geometry_estimate",
    "manual_container_volume_estimate",
    "recipe_template_volume_estimate",
    "volume_density_estimate",
    "generic_density_profile",
]


class PortionGramRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    grams_min: float | None = Field(default=None, ge=0)
    grams_max: float | None = Field(default=None, ge=0)
    grams_p10: float | None = Field(default=None, ge=0)
    grams_p50: float | None = Field(default=None, ge=0)
    grams_p90: float | None = Field(default=None, ge=0)
    percentiles_available: bool = False
    confidence: float = Field(..., ge=0, le=1)
    source: Literal[
        "portion_hint_weight_unit",
        "portion_hint_household_unit",
        "volume_estimate_density_table",
        "fallback_default",
    ]
    reason: str = Field(..., min_length=1)
    uncertainty_flags: tuple[PortionUncertaintyFlag, ...] = Field(default_factory=tuple)

    @model_validator(mode="before")
    @classmethod
    def _hydrate_bounds_and_percentiles(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        explicit_percentiles = any(
            key in payload and payload.get(key) is not None
            for key in ("grams_p10", "grams_p50", "grams_p90")
        )
        grams_min = payload.get("grams_min")
        grams_max = payload.get("grams_max")
        grams_p10 = payload.get("grams_p10")
        grams_p50 = payload.get("grams_p50")
        grams_p90 = payload.get("grams_p90")

        if grams_p10 is None and grams_min is not None:
            payload["grams_p10"] = grams_min
        if grams_p90 is None and grams_max is not None:
            payload["grams_p90"] = grams_max
        if grams_min is None and grams_p10 is not None:
            payload["grams_min"] = grams_p10
        if grams_max is None and grams_p90 is not None:
            payload["grams_max"] = grams_p90

        grams_p10 = payload.get("grams_p10")
        grams_p90 = payload.get("grams_p90")
        if grams_p50 is None and grams_p10 is not None and grams_p90 is not None:
            payload["grams_p50"] = _round_grams((float(grams_p10) + float(grams_p90)) / 2.0)
        if "percentiles_available" not in payload:
            payload["percentiles_available"] = explicit_percentiles

        return payload

    @model_validator(mode="after")
    def _validate_bounds(self) -> PortionGramRange:
        if self.grams_min is None or self.grams_max is None:
            raise ValueError("grams_min and grams_max must be provided")
        if self.grams_p10 is None or self.grams_p50 is None or self.grams_p90 is None:
            raise ValueError("grams_p10, grams_p50, and grams_p90 must be provided")
        if self.grams_min > self.grams_max:
            raise ValueError("grams_min must be less than or equal to grams_max")
        if not self.grams_p10 <= self.grams_p50 <= self.grams_p90:
            raise ValueError("grams_p10 must be less than or equal to grams_p50 and grams_p90")
        if self.grams_min != self.grams_p10 or self.grams_max != self.grams_p90:
            raise ValueError("grams_min/grams_max must align with grams_p10/grams_p90")
        return self


def parse_portion_range(
    component_name: str,
    portion_hint: str | None = None,
) -> PortionGramRange:
    """Parse common portion hints into a deterministic conservative gram range."""
    component = _normalize_component_name(component_name)
    hint_text = _normalize_hint_text(portion_hint)
    if hint_text is None:
        return _build_fallback_result(
            component_name=component,
            portion_hint=portion_hint,
            reason_detail="portion hint missing",
            confidence=0.25,
            uncertainty_flags=("missing_portion_hint",),
        )

    has_approximate_language = _contains_approximate_language(hint_text)
    weight_parse = _parse_weight_hint(hint_text)
    if weight_parse is not None:
        unit_name, quantity = weight_parse
        if quantity <= 0:
            return _build_fallback_result(
                component_name=component,
                portion_hint=portion_hint,
                reason_detail="parsed non-positive portion quantity",
                confidence=0.20,
                uncertainty_flags=("non_positive_quantity",),
            )
        grams = quantity * (1000.0 if unit_name == "kilogram" else 1.0)
        uncertainty = grams * 0.10
        grams_p10 = _round_grams(max(0.0, grams - uncertainty))
        grams_p90 = _round_grams(grams + uncertainty)
        return PortionGramRange(
            grams_min=grams_p10,
            grams_max=grams_p90,
            grams_p10=grams_p10,
            grams_p50=_round_grams(grams),
            grams_p90=grams_p90,
            percentiles_available=True,
            confidence=0.90,
            source="portion_hint_weight_unit",
            reason=(
                f"parsed '{portion_hint}' as {quantity:g} {unit_name}"
                f" for component '{component}'"
            ),
            uncertainty_flags=_build_uncertainty_flags(
                "approximate_quantity" if has_approximate_language else None,
            ),
        )

    household_parse = _parse_household_hint(hint_text)
    if household_parse is not None:
        unit_name, quantity, explicit_quantity = household_parse
        if quantity <= 0:
            return _build_fallback_result(
                component_name=component,
                portion_hint=portion_hint,
                reason_detail="parsed non-positive portion quantity",
                confidence=0.20,
                uncertainty_flags=("non_positive_quantity",),
            )

        unit_min, unit_max = _household_unit_grams(
            unit_name=unit_name,
            component_name=component,
        )
        grams_p10 = _round_grams(unit_min * quantity)
        grams_p90 = _round_grams(unit_max * quantity)
        return PortionGramRange(
            grams_min=grams_p10,
            grams_max=grams_p90,
            grams_p10=grams_p10,
            grams_p50=_round_grams((grams_p10 + grams_p90) / 2.0),
            grams_p90=grams_p90,
            percentiles_available=True,
            confidence=0.68 if explicit_quantity else 0.58,
            source="portion_hint_household_unit",
            reason=(
                f"parsed '{portion_hint}' as {quantity:g} {unit_name}"
                f" for component '{component}'"
            ),
            uncertainty_flags=_build_uncertainty_flags(
                "implicit_quantity" if not explicit_quantity else None,
                "approximate_quantity" if has_approximate_language else None,
            ),
        )

    return _build_fallback_result(
        component_name=component,
        portion_hint=portion_hint,
        reason_detail="portion hint could not be parsed",
        confidence=0.20,
        uncertainty_flags=_build_uncertainty_flags(
            "unknown_portion_hint",
            "approximate_quantity" if has_approximate_language else None,
        ),
    )


def parse_component_portion_range(
    component_name: str,
    portion_hint: str | None = None,
) -> PortionGramRange:
    """Compatibility alias for parse_portion_range()."""
    return parse_portion_range(component_name=component_name, portion_hint=portion_hint)


def _normalize_component_name(component_name: str) -> str:
    if not isinstance(component_name, str):
        return "unknown component"
    normalized = " ".join(component_name.split())
    if normalized:
        return normalized
    return "unknown component"


def _normalize_hint_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.casefold().strip()
    if not text:
        return None
    text = re.sub(r"(?<=[a-z])[-–—]+(?=[a-z])", " ", text)
    text = re.sub(r"(?<=\d)[-–—]+(?=[a-z])", " ", text)
    text = re.sub(r"(?<=\d)(?=[a-z])", " ", text)
    text = re.sub(r"(?<=[a-z])(?=\d)", " ", text)
    text = re.sub(r"[^a-z0-9./+\-\s]", " ", text)
    text = " ".join(text.split())
    return text or None


def _parse_weight_hint(hint_text: str) -> tuple[str, float] | None:
    tokens = hint_text.split()
    for index in range(len(tokens) - 1, -1, -1):
        token = tokens[index]
        unit = _TOKEN_TO_UNIT.get(token)
        if unit not in _WEIGHT_UNITS:
            continue
        quantity, explicit_quantity = _extract_quantity(tokens, unit_index=index)
        if quantity is None or not explicit_quantity:
            continue
        return (unit, quantity)
    return None


def _parse_household_hint(hint_text: str) -> tuple[str, float, bool] | None:
    tokens = hint_text.split()
    implicit_match: tuple[str, float, bool] | None = None
    for index, token in enumerate(tokens):
        unit = _TOKEN_TO_UNIT.get(token)
        if unit is None or unit in _WEIGHT_UNITS:
            continue
        quantity, explicit_quantity = _extract_quantity(tokens, unit_index=index)
        if quantity is None:
            continue
        match = (unit, quantity, explicit_quantity)
        if explicit_quantity:
            return match
        if implicit_match is None:
            implicit_match = match
    return implicit_match


def _contains_approximate_language(hint_text: str) -> bool:
    return any(token in _APPROX_WORDS for token in hint_text.split())


def _household_unit_grams(*, unit_name: str, component_name: str) -> tuple[float, float]:
    if unit_name == "piece" and _looks_like_sushi_piece(component_name):
        return _SUSHI_PIECE_RANGE_GRAMS
    return _HOUSEHOLD_UNIT_GRAMS[unit_name]


def _looks_like_sushi_piece(component_name: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", component_name.casefold()))
    return bool(tokens & {"sushi", "maki", "nigiri"})


def _build_uncertainty_flags(
    *flags: PortionUncertaintyFlag | None,
) -> tuple[PortionUncertaintyFlag, ...]:
    deduped: list[PortionUncertaintyFlag] = []
    for flag in flags:
        if flag is None:
            continue
        if flag not in deduped:
            deduped.append(flag)
    return tuple(deduped)


def _extract_quantity(tokens: list[str], *, unit_index: int) -> tuple[float | None, bool]:
    window = tokens[max(0, unit_index - 5) : unit_index]
    if not window:
        return (1.0, False)

    filtered = [token for token in window if token not in _WINDOW_FILLER_WORDS]
    if not filtered:
        return (1.0, False)
    if filtered in (["a"], ["an"]):
        return (1.0, False)

    quantity_suffix = _quantity_suffix(filtered)
    if quantity_suffix:
        quantity = _parse_quantity_text(" ".join(quantity_suffix))
        if quantity is not None:
            return (quantity, True)

    quantity = _parse_quantity_window(filtered)
    if quantity is not None:
        return (quantity, True)

    if any(any(char.isdigit() for char in token) for token in filtered):
        return (None, False)

    # Treat adjective-only hints like "medium bowl" as an implicit single unit.
    return (1.0, False)


def _parse_quantity_window(tokens: list[str]) -> float | None:
    for start in range(len(tokens)):
        for end in range(len(tokens), start, -1):
            quantity = _parse_quantity_text(" ".join(tokens[start:end]))
            if quantity is not None:
                return quantity
    return None


def _quantity_suffix(tokens: list[str]) -> list[str]:
    suffix: list[str] = []
    for token in reversed(tokens):
        if _could_be_quantity_token(token):
            suffix.append(token)
            continue
        break
    suffix.reverse()
    return suffix


def _could_be_quantity_token(token: str) -> bool:
    return (
        token in _NUMBER_WORDS
        or token in _FRACTION_WORDS
        or token in {"a", "an", "and"}
        or re.fullmatch(r"[+-]?\d+(?:\.\d+)?", token) is not None
        or re.fullmatch(r"[+-]?\d+(?:\.\d+)?-[+-]?\d+(?:\.\d+)?", token) is not None
        or re.fullmatch(r"[+-]?\d+\s*/\s*\d+", token) is not None
    )


def _parse_quantity_text(quantity_text: str) -> float | None:
    normalized = " ".join(quantity_text.split())
    if not normalized:
        return None

    mixed_number_match = re.fullmatch(r"([+-]?\d+)\s+(\d+)\s*/\s*(\d+)", normalized)
    if mixed_number_match is not None:
        whole, numerator, denominator = mixed_number_match.groups()
        denominator_value = int(denominator)
        if denominator_value == 0:
            return None
        return float(int(whole) + (int(numerator) / denominator_value))

    fraction_match = re.fullmatch(r"([+-]?\d+)\s*/\s*(\d+)", normalized)
    if fraction_match is not None:
        numerator, denominator = fraction_match.groups()
        denominator_value = int(denominator)
        if denominator_value == 0:
            return None
        return float(int(numerator) / denominator_value)

    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", normalized):
        return float(normalized)

    range_match = re.fullmatch(
        r"([+-]?\d+(?:\.\d+)?)\s*-\s*([+-]?\d+(?:\.\d+)?)",
        normalized,
    )
    if range_match is not None:
        lower, upper = range_match.groups()
        return (float(lower) + float(upper)) / 2.0

    return _parse_word_quantity(normalized)


def _parse_word_quantity(quantity_text: str) -> float | None:
    if quantity_text in _SPECIAL_WORD_QUANTITIES:
        return _SPECIAL_WORD_QUANTITIES[quantity_text]

    tokens = quantity_text.split()
    while tokens and tokens[-1] in {"a", "an"}:
        tokens = tokens[:-1]
    if not tokens:
        return None

    joined = " ".join(tokens)
    if joined in _SPECIAL_WORD_QUANTITIES:
        return _SPECIAL_WORD_QUANTITIES[joined]

    if len(tokens) == 1:
        token = tokens[0]
        if token in _NUMBER_WORDS:
            return _NUMBER_WORDS[token]
        if token in _FRACTION_WORDS:
            return _FRACTION_WORDS[token]
        return None

    if len(tokens) == 2 and tokens[0] in _NUMBER_WORDS and tokens[1] in _FRACTION_WORDS:
        number = _NUMBER_WORDS[tokens[0]]
        fraction = _FRACTION_WORDS[tokens[1]]
        if number == 1.0:
            return fraction
        return number * fraction

    if len(tokens) >= 3 and tokens[1] == "and" and tokens[0] in _NUMBER_WORDS:
        whole = _NUMBER_WORDS[tokens[0]]
        fraction_tokens = tokens[2:]
        if fraction_tokens and fraction_tokens[0] in {"a", "an"}:
            fraction_tokens = fraction_tokens[1:]
        if len(fraction_tokens) == 1 and fraction_tokens[0] in _FRACTION_WORDS:
            return whole + _FRACTION_WORDS[fraction_tokens[0]]

    return None


def _build_fallback_result(
    *,
    component_name: str,
    portion_hint: str | None,
    reason_detail: str,
    confidence: float,
    uncertainty_flags: tuple[PortionUncertaintyFlag, ...],
) -> PortionGramRange:
    grams_p10 = _FALLBACK_RANGE_GRAMS[0]
    grams_p90 = _FALLBACK_RANGE_GRAMS[1]
    return PortionGramRange(
        grams_min=grams_p10,
        grams_max=grams_p90,
        grams_p10=grams_p10,
        grams_p50=_round_grams((grams_p10 + grams_p90) / 2.0),
        grams_p90=grams_p90,
        percentiles_available=True,
        confidence=confidence,
        source="fallback_default",
        reason=(
            f"{reason_detail}; component='{component_name}', "
            f"portion_hint={portion_hint!r}"
        ),
        uncertainty_flags=uncertainty_flags,
    )


def _round_grams(value: float) -> float:
    return round(value, 2)


__all__ = [
    "PortionGramRange",
    "parse_component_portion_range",
    "parse_portion_range",
]
