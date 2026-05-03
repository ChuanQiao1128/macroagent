# Claude Vision Meal Component Wrapper

`services.vision` exposes a small wrapper around Anthropic Claude Sonnet for meal-photo understanding.

## What It Does

- Accepts image input as a file path, `bytes`, or `bytearray`.
- Normalizes the image before sending it to Claude:
  - applies EXIF rotation
  - registers HEIC support when `pillow-heif` is available
  - converts to JPEG
  - resizes the long side to 1024 px
- Computes a stable SHA-256 hash from the normalized JPEG bytes.
- Optionally checks a cache before calling Anthropic.
- Sends the image to Claude Sonnet through the Anthropic API on cache miss.
- Enforces a JSON-schema-shaped tool response for `FoodComponent[]`.
- Retries once if the first response fails schema validation.
- Ships with a simple JSON-file cache for local Track A usage.

## Public API

- `ClaudeVisionClient`
- `analyze_meal_photo(image, client=None, model=None, cache=None)`
- `FoodComponent`
- `JsonFileVisionCache`
- `VisionParseError`
- `VisionResultCache`

## Caching

`ClaudeVisionClient` accepts an optional cache object that implements `VisionResultCache`.
Cache keys include:

- normalized image hash
- model name
- prompt text

On a cache hit, the client returns validated `FoodComponent[]` without making an Anthropic call.
On a cache miss, it calls Anthropic once and stores the validated result.

`JsonFileVisionCache` stores component payloads in a local JSON file and does not persist raw images.
Writes use a temporary file plus `os.replace()` so local single-user updates are atomic enough for this use case.

## Output Shape

Each detected food component includes:

- `name`
- `confidence`
- `portion_hint`

## Verification

- `pytest tests/vision/test_claude_vision.py`
- `ruff check services/vision/`
