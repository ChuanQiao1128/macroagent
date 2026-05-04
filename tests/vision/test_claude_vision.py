from __future__ import annotations

import base64
import hashlib
import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from services.vision import (
    ClaudeVisionClient,
    FoodComponent,
    JsonFileVisionCache,
    VisionParseError,
    analyze_meal_photo,
)
from services.vision.src import cache as cache_module


class FakeMessages:
    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = payloads
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        payload = self.payloads.pop(0)
        return SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="tool_use",
                    name="extract_food_components",
                    input=payload,
                )
            ]
        )


class FakeAnthropicClient:
    def __init__(self, payloads: list[dict]) -> None:
        self.messages = FakeMessages(payloads)


class RecordingCache:
    def __init__(self, cached: list[dict] | None) -> None:
        self.cached = cached
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, list[dict]]] = []

    def get(self, key: str) -> list[dict] | None:
        self.get_calls.append(key)
        if self.cached is None:
            return None
        return [dict(item) for item in self.cached]

    def set(self, key: str, components: list[dict]) -> None:
        self.set_calls.append((key, [dict(item) for item in components]))


def png_bytes(width: int = 1600, height: int = 800) -> bytes:
    image = Image.new("RGB", (width, height), color=(220, 120, 80))
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def jpeg_bytes_with_exif_orientation(
    width: int = 300, height: int = 100, orientation: int = 6
) -> bytes:
    image = Image.new("RGB", (width, height), color=(60, 160, 220))
    exif = image.getexif()
    exif[274] = orientation
    out = BytesIO()
    image.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def test_analyze_meal_photo_returns_valid_food_components_and_resizes_image() -> None:
    fake = FakeAnthropicClient(
        [
            {
                "components": [
                    {"name": "rice", "confidence": 0.91, "portion_hint": "about one cup"}
                ]
            }
        ]
    )

    result = ClaudeVisionClient(client=fake).analyze_meal_photo(png_bytes())

    assert result == [FoodComponent(name="rice", confidence=0.91, portion_hint="about one cup")]
    request = fake.messages.calls[0]
    content = request["messages"][0]["content"]
    image_source = content[0]["source"]
    assert image_source["media_type"] == "image/jpeg"

    decoded = base64.b64decode(image_source["data"])
    with Image.open(BytesIO(decoded)) as prepared:
        assert prepared.format == "JPEG"
        assert max(prepared.size) == 1024


def test_analyze_meal_photo_accepts_path_input(tmp_path: Path) -> None:
    fake = FakeAnthropicClient(
        [
            {
                "components": [
                    {"name": "broccoli", "confidence": 0.79, "portion_hint": "half a cup"}
                ]
            }
        ]
    )
    image_path = tmp_path / "meal.png"
    image_path.write_bytes(png_bytes(640, 360))

    result = analyze_meal_photo(str(image_path), client=fake)

    assert result == [FoodComponent(name="broccoli", confidence=0.79, portion_hint="half a cup")]
    assert len(fake.messages.calls) == 1


def test_analyze_meal_photo_applies_exif_rotation_before_encoding() -> None:
    fake = FakeAnthropicClient(
        [
            {
                "components": [
                    {"name": "omelette", "confidence": 0.87, "portion_hint": "one plate"}
                ]
            }
        ]
    )

    ClaudeVisionClient(client=fake).analyze_meal_photo(
        jpeg_bytes_with_exif_orientation(300, 100, orientation=6)
    )

    request = fake.messages.calls[0]
    image_source = request["messages"][0]["content"][0]["source"]
    decoded = base64.b64decode(image_source["data"])

    with Image.open(BytesIO(decoded)) as prepared:
        assert prepared.size == (100, 300)


def test_analyze_meal_photo_retries_once_on_schema_failure() -> None:
    fake = FakeAnthropicClient(
        [
            {"components": [{"name": "", "confidence": 2.0, "portion_hint": "bad"}]},
            {"components": [{"name": "salmon", "confidence": 0.82, "portion_hint": "one fillet"}]},
        ]
    )

    result = analyze_meal_photo(png_bytes(256, 256), client=fake)

    assert len(fake.messages.calls) == 2
    first_prompt = fake.messages.calls[0]["messages"][0]["content"][1]["text"]
    second_prompt = fake.messages.calls[1]["messages"][0]["content"][1]["text"]
    assert first_prompt == second_prompt.split("\n\n", maxsplit=1)[0]
    assert "previous response failed schema validation" in second_prompt
    assert result == [FoodComponent(name="salmon", confidence=0.82, portion_hint="one fillet")]


def test_analyze_meal_photo_raises_after_second_schema_failure() -> None:
    fake = FakeAnthropicClient(
        [
            {"components": [{"name": "", "confidence": 2.0, "portion_hint": "bad"}]},
            {"components": [{"name": "", "confidence": 2.0, "portion_hint": "still bad"}]},
        ]
    )

    with pytest.raises(VisionParseError):
        analyze_meal_photo(png_bytes(256, 256), client=fake)

    assert len(fake.messages.calls) == 2


def test_prepare_image_invokes_heif_opener_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"value": False}

    def fake_register() -> None:
        called["value"] = True

    monkeypatch.setattr(ClaudeVisionClient, "_register_heif_opener", staticmethod(fake_register))
    client = ClaudeVisionClient(client=FakeAnthropicClient([{"components": []}]))
    prepared = client._prepare_image(png_bytes(320, 200))

    assert called["value"] is True
    assert prepared.media_type == "image/jpeg"


def test_analyze_meal_photo_cache_hit_skips_anthropic_and_returns_components() -> None:
    cache = RecordingCache(
        cached=[{"name": "tofu", "confidence": 0.88, "portion_hint": "half block"}]
    )
    fake = FakeAnthropicClient([])
    prompt = "custom prompt text"
    model = "claude-cache-test"

    result = ClaudeVisionClient(client=fake, model=model, cache=cache).analyze_meal_photo(
        png_bytes(300, 200), prompt=prompt
    )

    assert result == [FoodComponent(name="tofu", confidence=0.88, portion_hint="half block")]
    assert fake.messages.calls == []
    assert len(cache.get_calls) == 1
    cache_key_data = json.loads(cache.get_calls[0])
    assert cache_key_data["model"] == model
    assert cache_key_data["prompt"] == prompt
    assert cache_key_data["image_hash"] == cache_key_data["image_hash"].lower()
    assert len(cache_key_data["image_hash"]) == 64
    assert all(ch in "0123456789abcdef" for ch in cache_key_data["image_hash"])


def test_analyze_meal_photo_cache_miss_calls_anthropic_once_and_writes_cache() -> None:
    cache = RecordingCache(cached=None)
    fake = FakeAnthropicClient(
        [
            {
                "components": [
                    {"name": "beans", "confidence": 0.67, "portion_hint": "three quarters cup"}
                ]
            }
        ]
    )
    prompt = "find meal parts"
    model = "claude-cache-miss-model"

    result = ClaudeVisionClient(client=fake, model=model, cache=cache).analyze_meal_photo(
        png_bytes(250, 250), prompt=prompt
    )

    assert result == [
        FoodComponent(name="beans", confidence=0.67, portion_hint="three quarters cup")
    ]
    assert len(fake.messages.calls) == 1
    assert len(cache.get_calls) == 2
    assert len(cache.set_calls) == 2

    structured_set_key, structured_set_payload = cache.set_calls[0]
    legacy_set_key, legacy_set_payload = cache.set_calls[1]
    assert structured_set_key == cache.get_calls[1]
    assert legacy_set_key == cache.get_calls[0]
    assert legacy_set_payload == [
        {"name": "beans", "confidence": 0.67, "portion_hint": "three quarters cup"}
    ]
    assert structured_set_payload[0]["_cache_format"] == "vision_analysis_response_v1"
    assert structured_set_payload[0]["payload"]["components"][0]["visible_name"] == "beans"

    cache_key_data = json.loads(legacy_set_key)
    assert cache_key_data["model"] == model
    assert cache_key_data["prompt"] == prompt
    assert len(cache_key_data["image_hash"]) == 64


def test_image_hash_is_deterministic_sha256_of_normalized_jpeg_bytes() -> None:
    client = ClaudeVisionClient(client=FakeAnthropicClient([{"components": []}]))
    prepared_1 = client._prepare_image(png_bytes(640, 360))
    prepared_2 = client._prepare_image(png_bytes(640, 360))

    hash_1 = client._image_hash(prepared_1.data)
    hash_2 = client._image_hash(prepared_2.data)

    assert hash_1 == hashlib.sha256(prepared_1.data).hexdigest()
    assert hash_1 == hash_2


def test_json_file_cache_roundtrip_stores_component_payloads_only(tmp_path: Path) -> None:
    cache_path = tmp_path / "vision-cache.json"
    cache = JsonFileVisionCache(cache_path)
    key = json.dumps(
        {
            "image_hash": "a" * 64,
            "model": "model-x",
            "prompt": "detect meal components",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    components = [{"name": "rice", "confidence": 0.9, "portion_hint": "one cup"}]

    cache.set(key, components)

    disk_payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert list(disk_payload.keys()) == [key]
    assert disk_payload[key] == components
    assert disk_payload[key][0].keys() == {"name", "confidence", "portion_hint"}

    loaded = cache.get(key)
    assert loaded == components
    assert loaded is not None
    loaded[0]["name"] = "modified"
    assert cache.get(key) == components


def test_json_file_cache_set_uses_atomic_replace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache_path = tmp_path / "vision-cache.json"
    cache = JsonFileVisionCache(cache_path)
    replace_calls: list[tuple[Path, Path]] = []
    original_replace = cache_module.os.replace

    def tracking_replace(src: str | Path, dst: str | Path) -> None:
        replace_calls.append((Path(src), Path(dst)))
        original_replace(src, dst)

    monkeypatch.setattr(cache_module.os, "replace", tracking_replace)

    cache.set("cache-key", [{"name": "egg", "confidence": 0.5, "portion_hint": None}])

    assert len(replace_calls) == 1
    temp_path, final_path = replace_calls[0]
    assert final_path == cache_path
    assert temp_path.name.startswith(f"{cache_path.name}.")
    assert temp_path.suffix == ".tmp"
    assert cache_path.exists()
    assert not any(cache_path.parent.glob(f"{cache_path.name}.*.tmp"))


def test_analyze_meal_photo_structured_parses_full_uncertainty_response() -> None:
    payload = {
        "image_quality_issues": [
            {
                "issue": "motion blur near plate edge",
                "severity": "medium",
                "impact": "shape ambiguity",
            }
        ],
        "meal_uncertainty_flags": ["mixed_dish", "partial_occlusion"],
        "components": [
            {
                "component_id": "component_1",
                "visible_name": "sauced chicken pieces",
                "candidates": [
                    {
                        "name": "teriyaki chicken",
                        "confidence": 0.63,
                        "visual_evidence": ["brown glossy coating", "cubed chicken texture"],
                    },
                    {
                        "name": "orange chicken",
                        "confidence": 0.24,
                        "visual_evidence": ["thick sticky sauce"],
                    },
                ],
                "portion": {
                    "description": "about one cup",
                    "confidence": 0.72,
                    "visual_basis": ["relative to fork size"],
                },
                "state_hints": [
                    {"state": "sauced", "confidence": 0.94, "visual_evidence": ["surface sheen"]},
                    {"state": "cooked", "confidence": 0.88, "visual_evidence": ["opaque protein"]},
                ],
                "hidden_ingredient_risks": [
                    {
                        "ingredient": "added sugar in sauce",
                        "likelihood": 0.83,
                        "macro_impact": "high",
                        "rationale": "thick sweet glaze suggests sugar-heavy sauce",
                    }
                ],
            }
        ],
    }
    fake = FakeAnthropicClient([payload])

    structured = ClaudeVisionClient(client=fake).analyze_meal_photo_structured(png_bytes(640, 360))

    assert structured.meal_uncertainty_flags == ["mixed_dish", "partial_occlusion"]
    assert structured.image_quality_issues[0].issue == "motion blur near plate edge"
    component = structured.components[0]
    assert component.component_id == "component_1"
    assert component.visible_name == "sauced chicken pieces"
    assert component.candidates[0].name == "teriyaki chicken"
    assert component.portion.description == "about one cup"
    assert component.state_hints[0].state == "sauced"
    assert component.hidden_ingredient_risks[0].ingredient == "added sugar in sauce"


def test_default_analyzer_maps_structured_response_to_legacy_food_components() -> None:
    fake = FakeAnthropicClient(
        [
            {
                "components": [
                    {
                        "component_id": "component_1",
                        "visible_name": "grain bowl base",
                        "candidates": [
                            {
                                "name": "brown rice",
                                "confidence": 0.77,
                                "visual_evidence": ["small whole grains"],
                            },
                            {
                                "name": "quinoa",
                                "confidence": 0.18,
                                "visual_evidence": ["speckled seeds"],
                            },
                        ],
                        "portion": {
                            "description": "around three quarters cup",
                            "confidence": 0.7,
                            "visual_basis": ["fills base of bowl"],
                        },
                        "state_hints": [
                            {"state": "cooked", "confidence": 0.9, "visual_evidence": []}
                        ],
                        "hidden_ingredient_risks": [],
                    }
                ]
            }
        ]
    )

    components = ClaudeVisionClient(client=fake).analyze_meal_photo(png_bytes(500, 500))

    assert components == [
        FoodComponent(
            name="brown rice",
            confidence=0.77,
            portion_hint="around three quarters cup",
        )
    ]


def test_analyze_meal_photo_structured_accepts_legacy_simple_component_response() -> None:
    fake = FakeAnthropicClient(
        [
            {
                "components": [
                    {"name": "grilled salmon", "confidence": 0.81, "portion_hint": "one fillet"}
                ]
            }
        ]
    )

    structured = ClaudeVisionClient(client=fake).analyze_meal_photo_structured(png_bytes(300, 300))

    assert structured.meal_uncertainty_flags == ["legacy_simple_response"]
    assert structured.image_quality_issues == []
    component = structured.components[0]
    assert component.component_id == "component_1"
    assert component.visible_name == "grilled salmon"
    assert component.candidates[0].name == "grilled salmon"
    assert component.portion.description == "one fillet"
    assert component.hidden_ingredient_risks == []


def test_analyze_meal_photo_structured_retries_on_invalid_structured_payload() -> None:
    fake = FakeAnthropicClient(
        [
            {
                "components": [
                    {
                        "component_id": "component_1",
                        "visible_name": "chicken",
                        "candidates": [{"name": "chicken breast", "confidence": 1.3}],
                        "portion": {
                            "description": "one piece",
                            "confidence": 0.6,
                            "visual_basis": [],
                        },
                    }
                ]
            },
            {
                "components": [
                    {
                        "component_id": "component_1",
                        "visible_name": "chicken",
                        "candidates": [
                            {
                                "name": "chicken breast",
                                "confidence": 0.86,
                                "visual_evidence": ["white cooked meat"],
                            }
                        ],
                        "portion": {
                            "description": "one piece",
                            "confidence": 0.6,
                            "visual_basis": ["single visible cutlet"],
                        },
                        "state_hints": [],
                        "hidden_ingredient_risks": [],
                    }
                ]
            },
        ]
    )

    structured = ClaudeVisionClient(client=fake).analyze_meal_photo_structured(png_bytes(256, 256))

    assert len(fake.messages.calls) == 2
    first_prompt = fake.messages.calls[0]["messages"][0]["content"][1]["text"]
    second_prompt = fake.messages.calls[1]["messages"][0]["content"][1]["text"]
    assert first_prompt == second_prompt.split("\n\n", maxsplit=1)[0]
    assert "previous response failed schema validation" in second_prompt
    assert structured.components[0].candidates[0].confidence == 0.86


def test_malformed_structured_payload_is_not_downgraded_to_legacy_response() -> None:
    malformed_structured_payload = {
        "components": [
            {
                "component_id": "component_1",
                "visible_name": "chicken",
                "candidates": [{"name": "chicken breast", "confidence": 0.86}],
                "portion": {
                    "description": "one piece",
                    "confidence": 0.6,
                    "visual_basis": [],
                },
                "state_hints": [],
                "hidden_ingredient_risks": [],
            }
        ]
    }
    fake = FakeAnthropicClient([malformed_structured_payload, malformed_structured_payload])

    with pytest.raises(VisionParseError):
        ClaudeVisionClient(client=fake).analyze_meal_photo_structured(png_bytes(256, 256))

    assert len(fake.messages.calls) == 2


def test_default_analyzer_populates_structured_cache_for_later_structured_calls(
    tmp_path: Path,
) -> None:
    cache = JsonFileVisionCache(tmp_path / "vision-cache.json")
    payload = {
        "components": [
            {
                "component_id": "component_1",
                "visible_name": "grain bowl base",
                "candidates": [
                    {
                        "name": "brown rice",
                        "confidence": 0.77,
                        "visual_evidence": ["small whole grains"],
                    }
                ],
                "portion": {
                    "description": "around three quarters cup",
                    "confidence": 0.7,
                    "visual_basis": ["fills base of bowl"],
                },
                "state_hints": [],
                "hidden_ingredient_risks": [],
            }
        ]
    }
    image = png_bytes(500, 500)
    first_fake = FakeAnthropicClient([payload])

    components = ClaudeVisionClient(client=first_fake, cache=cache).analyze_meal_photo(image)

    assert components == [
        FoodComponent(
            name="brown rice",
            confidence=0.77,
            portion_hint="around three quarters cup",
        )
    ]
    assert len(first_fake.messages.calls) == 1

    second_fake = FakeAnthropicClient([])
    structured = ClaudeVisionClient(client=second_fake, cache=cache).analyze_meal_photo_structured(
        image
    )

    assert second_fake.messages.calls == []
    assert structured.components[0].candidates[0].name == "brown rice"


def test_hidden_ingredient_risk_alias_fields_are_parsed() -> None:
    fake = FakeAnthropicClient(
        [
            {
                "components": [
                    {
                        "id": "component_1",
                        "name": "fries with dip",
                        "top_k_candidates": [
                            {
                                "food_name": "french fries",
                                "confidence": 0.9,
                                "evidence": ["thin fried strips"],
                            }
                        ],
                        "portion_estimate": {
                            "portion_description": "small side basket",
                            "portion_confidence": 0.68,
                            "visual_evidence": ["fits beside sandwich"],
                        },
                        "state": [
                            {
                                "state": "fried",
                                "confidence": 0.95,
                                "visual_evidence": ["golden crisp surface"],
                            }
                        ],
                        "hidden_risks": [
                            {
                                "ingredient": "frying oil absorption",
                                "likelihood": 0.79,
                                "macro_impact": "medium",
                                "rationale": "visible sheen and porous texture",
                            }
                        ],
                    }
                ]
            }
        ]
    )

    structured = ClaudeVisionClient(client=fake).analyze_meal_photo_structured(png_bytes(420, 320))

    risk = structured.components[0].hidden_ingredient_risks[0]
    assert risk.ingredient == "frying oil absorption"
    assert risk.likelihood == 0.79
    assert risk.macro_impact == "medium"
    assert risk.rationale == "visible sheen and porous texture"


def test_tool_schema_excludes_nutrition_number_fields() -> None:
    schema = ClaudeVisionClient._tool_schema()
    schema_text = json.dumps(schema).lower()

    forbidden_fields = [
        "kcal",
        "calorie",
        "calories",
        "protein",
        "carb",
        "carbs",
        "fat",
        "meal_total",
    ]
    for field in forbidden_fields:
        assert field not in schema_text
