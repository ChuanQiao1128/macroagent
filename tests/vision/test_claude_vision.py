from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from services.vision import (
    ClaudeVisionClient,
    FoodComponent,
    VisionParseError,
    analyze_meal_photo,
)


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
