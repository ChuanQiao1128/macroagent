from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict, Field, ValidationError

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"
DEFAULT_PROMPT = (
    "Identify visible food components in this meal photo. Return each distinct "
    "component with a short name, confidence from 0 to 1, and a concise portion hint. "
    "Use the tool schema only."
)
TOOL_NAME = "extract_food_components"


class VisionParseError(ValueError):
    """Raised when Claude returns content that does not match the expected schema."""


class FoodComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    portion_hint: str | None = None


class FoodComponentsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    components: list[FoodComponent]


@dataclass(frozen=True)
class PreparedImage:
    media_type: str
    data: bytes


class ClaudeVisionClient:
    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str | None = None,
        max_long_side: int = 1024,
    ) -> None:
        self.model = model or os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
        self.max_long_side = max_long_side
        self._client = client or self._build_default_client()

    def analyze_meal_photo(
        self,
        image: str | Path | bytes | bytearray,
        *,
        prompt: str = DEFAULT_PROMPT,
    ) -> list[FoodComponent]:
        prepared = self._prepare_image(image)
        encoded_image = base64.b64encode(prepared.data).decode("ascii")
        last_error: Exception | None = None

        for attempt in range(2):
            response = self._client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0,
                tools=[self._tool_schema()],
                tool_choice={"type": "tool", "name": TOOL_NAME},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": prepared.media_type,
                                    "data": encoded_image,
                                },
                            },
                            {"type": "text", "text": self._prompt_for_attempt(prompt, attempt)},
                        ],
                    }
                ],
            )

            try:
                return self._parse_response(response)
            except (ValidationError, VisionParseError, TypeError, ValueError) as exc:
                last_error = exc

        raise VisionParseError(
            "Claude vision response did not match FoodComponent schema"
        ) from last_error

    @staticmethod
    def _build_default_client() -> Any:
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise RuntimeError("Install the anthropic package to use ClaudeVisionClient") from exc
        return Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    @staticmethod
    def _tool_schema() -> dict[str, Any]:
        return {
            "name": TOOL_NAME,
            "description": "Return the visible meal food components.",
            "input_schema": FoodComponentsResponse.model_json_schema(),
        }

    @staticmethod
    def _prompt_for_attempt(prompt: str, attempt: int) -> str:
        if attempt == 0:
            return prompt
        return (
            f"{prompt}\n\nThe previous response failed schema validation. "
            "Call the tool again with only valid schema fields."
        )

    def _prepare_image(self, image: str | Path | bytes | bytearray) -> PreparedImage:
        raw = self._read_image_bytes(image)
        self._register_heif_opener()

        with Image.open(BytesIO(raw)) as opened:
            img = ImageOps.exif_transpose(opened)
            if img.mode not in {"RGB", "L"}:
                img = img.convert("RGB")
            elif img.mode == "L":
                img = img.convert("RGB")

            if max(img.size) > self.max_long_side:
                img.thumbnail((self.max_long_side, self.max_long_side), Image.Resampling.LANCZOS)

            out = BytesIO()
            img.save(out, format="JPEG", quality=90, optimize=True)
            return PreparedImage(media_type="image/jpeg", data=out.getvalue())

    @staticmethod
    def _read_image_bytes(image: str | Path | bytes | bytearray) -> bytes:
        if isinstance(image, bytes):
            return image
        if isinstance(image, bytearray):
            return bytes(image)
        return Path(image).read_bytes()

    @staticmethod
    def _register_heif_opener() -> None:
        try:
            from pillow_heif import register_heif_opener
        except ImportError:
            return
        register_heif_opener()

    @staticmethod
    def _parse_response(response: Any) -> list[FoodComponent]:
        for block in getattr(response, "content", []) or []:
            block_type = _read_attr(block, "type")
            block_name = _read_attr(block, "name")
            if block_type == "tool_use" and block_name == TOOL_NAME:
                payload = _read_attr(block, "input")
                return FoodComponentsResponse.model_validate(payload).components

        text = "".join(
            str(_read_attr(block, "text"))
            for block in getattr(response, "content", []) or []
            if _read_attr(block, "type") == "text" and _read_attr(block, "text") is not None
        ).strip()
        if text:
            payload = json.loads(text)
            if isinstance(payload, list):
                payload = {"components": payload}
            return FoodComponentsResponse.model_validate(payload).components

        raise VisionParseError("Claude response did not include a matching tool call")


def _read_attr(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def analyze_meal_photo(
    image: str | Path | bytes | bytearray,
    *,
    client: Any | None = None,
    model: str | None = None,
) -> list[FoodComponent]:
    return ClaudeVisionClient(client=client, model=model).analyze_meal_photo(image)
