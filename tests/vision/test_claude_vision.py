from __future__ import annotations

import base64
from io import BytesIO
from types import SimpleNamespace

from PIL import Image

from services.vision import ClaudeVisionClient, FoodComponent, analyze_meal_photo


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


def test_analyze_meal_photo_retries_once_on_schema_failure() -> None:
    fake = FakeAnthropicClient(
        [
            {"components": [{"name": "", "confidence": 2.0, "portion_hint": "bad"}]},
            {"components": [{"name": "salmon", "confidence": 0.82, "portion_hint": "one fillet"}]},
        ]
    )

    result = analyze_meal_photo(png_bytes(256, 256), client=fake)

    assert len(fake.messages.calls) == 2
    assert result == [FoodComponent(name="salmon", confidence=0.82, portion_hint="one fillet")]
