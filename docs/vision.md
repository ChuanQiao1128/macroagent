# Claude Vision Meal Component Wrapper

`services.vision` exposes a small wrapper around Anthropic Claude Sonnet for meal-photo understanding.

## What It Does

- Accepts image input as a file path, `bytes`, or `bytearray`.
- Normalizes the image before sending it to Claude:
  - applies EXIF rotation
  - registers HEIC support when `pillow-heif` is available
  - converts to JPEG
  - resizes the long side to 1024 px
- Sends the image to Claude Sonnet through the Anthropic API.
- Enforces a JSON-schema-shaped tool response for `FoodComponent[]`.
- Retries once if the first response fails schema validation.

## Public API

- `ClaudeVisionClient`
- `analyze_meal_photo(image, client=None, model=None)`
- `FoodComponent`
- `VisionParseError`

## Output Shape

Each detected food component includes:

- `name`
- `confidence`
- `portion_hint`

## Verification

- `pytest tests/vision/test_claude_vision.py`
- `ruff check services/vision/`
