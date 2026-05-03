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

_WEIGHT_UNITS = frozenset({"gram", "kilogram"})


class PortionGramRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    grams_min: float = Field(..., ge=0)
    grams_max: float = Field(..., ge=0)
    confidence: float = Field(..., ge=0, le=1)
    source: Literal[
        "portion_hint_weight_unit",
        "portion_hint_household_unit",
        "fallback_default",
    ]
    reason: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_bounds(self) -> PortionGramRange:
        if self.grams_min > self.grams_max:
            raise ValueError("grams_min must be less than or equal to grams_max")
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
        )

    weight_parse = _parse_weight_hint(hint_text)
    if weight_parse is not None:
        unit_name, quantity = weight_parse
        if quantity <= 0:
            return _build_fallback_result(
                component_name=component,
                portion_hint=portion_hint,
                reason_detail="parsed non-positive portion quantity",
                confidence=0.20,
            )
        grams = quantity * (1000.0 if unit_name == "kilogram" else 1.0)
        uncertainty = max(5.0, grams * 0.10)
        return PortionGramRange(
            grams_min=_round_grams(max(0.0, grams - uncertainty)),
            grams_max=_round_grams(grams + uncertainty),
            confidence=0.90,
            source="portion_hint_weight_unit",
            reason=(
                f"parsed '{portion_hint}' as {quantity:g} {unit_name}"
                f" for component '{component}'"
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
            )

        unit_min, unit_max = _HOUSEHOLD_UNIT_GRAMS[unit_name]
        return PortionGramRange(
            grams_min=_round_grams(unit_min * quantity),
            grams_max=_round_grams(unit_max * quantity),
            confidence=0.68 if explicit_quantity else 0.58,
            source="portion_hint_household_unit",
            reason=(
                f"parsed '{portion_hint}' as {quantity:g} {unit_name}"
                f" for component '{component}'"
            ),
        )

    return _build_fallback_result(
        component_name=component,
        portion_hint=portion_hint,
        reason_detail="portion hint could not be parsed",
        confidence=0.20,
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
    text = re.sub(r"(?<=\d)(?=[a-z])", " ", text)
    text = re.sub(r"(?<=[a-z])(?=\d)", " ", text)
    text = re.sub(r"[^a-z0-9./+\-\s]", " ", text)
    text = " ".join(text.split())
    return text or None


def _parse_weight_hint(hint_text: str) -> tuple[str, float] | None:
    tokens = hint_text.split()
    for index, token in enumerate(tokens):
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
    for index, token in enumerate(tokens):
        unit = _TOKEN_TO_UNIT.get(token)
        if unit is None or unit in _WEIGHT_UNITS:
            continue
        quantity, explicit_quantity = _extract_quantity(tokens, unit_index=index)
        if quantity is None:
            continue
        return (unit, quantity, explicit_quantity)
    return None


def _extract_quantity(tokens: list[str], *, unit_index: int) -> tuple[float | None, bool]:
    window = tokens[max(0, unit_index - 5) : unit_index]
    if not window:
        return (1.0, False)

    filtered = [token for token in window if token not in _WINDOW_FILLER_WORDS]
    if not filtered:
        return (1.0, False)
    if filtered in (["a"], ["an"]):
        return (1.0, False)

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
) -> PortionGramRange:
    return PortionGramRange(
        grams_min=_FALLBACK_RANGE_GRAMS[0],
        grams_max=_FALLBACK_RANGE_GRAMS[1],
        confidence=confidence,
        source="fallback_default",
        reason=(
            f"{reason_detail}; component='{component_name}', "
            f"portion_hint='{portion_hint if portion_hint else ''}'"
        ),
    )


def _round_grams(value: float) -> float:
    return round(value, 2)


__all__ = [
    "PortionGramRange",
    "parse_component_portion_range",
    "parse_portion_range",
]
