# Claude Vision Meal Component Wrapper

`services.vision` wraps Claude Sonnet for meal-photo understanding and exposes both a structured uncertainty API and a compatibility view for the existing meal pipeline.

## What It Does

- Accepts image input as a file path, `bytes`, or `bytearray`.
- Normalizes the image before sending it to Claude:
  - applies EXIF rotation
  - registers HEIC support when `pillow-heif` is available
  - converts to JPEG
  - resizes the long side to 1024 px
- Computes a stable SHA-256 hash from the normalized JPEG bytes.
- Optionally checks a cache before making a Claude call.
- Uses Claude Code subscription auth by default through `ClaudeCliVisionClient`, which shells out to `claude -p` and removes `ANTHROPIC_API_KEY` from the subprocess environment.
- Can still use the Anthropic SDK path by setting `VISION_PROVIDER=anthropic`.
- Constrains Claude with a Pydantic-generated tool schema for `VisionAnalysisResponse`.
- Requests uncertainty-aware perception only:
  - image quality and usability issues
  - meal-level uncertainty flags
  - per-component ids, visible names, top-k food candidates, portion estimates, state hints, and hidden ingredient risks
- Does not ask for kcal, protein, carbs, fat, sugar, sodium, fiber, or meal totals.
- Attaches stable trace version metadata to every structured response.
- Retries once if the first structured response fails validation.
- Accepts legacy `FoodComponent[]` responses and lifts them into the structured schema for compatibility.
- Ships with a simple JSON-file cache for local Track A usage.

## Public API

- `ClaudeCliVisionClient`
- `ClaudeVisionClient`
- `analyze_meal_photo(image, client=None, model=None, cache=None)`
- `analyze_meal_photo_structured(image, client=None, model=None, cache=None)`
- `FoodCandidate`
- `FoodComponent`
- `HiddenIngredientRisk`
- `ImageQualityIssue`
- `JsonFileVisionCache`
- `PortionEstimate`
- `StateHint`
- `StructuredFoodComponent`
- `VisionAnalysisResponse`
- `VisionParseError`
- `VisionResultCache`

## Output Shapes

`analyze_meal_photo()` returns the backward-compatible `FoodComponent[]` list that the existing meal-analysis code expects.

`analyze_meal_photo_structured()` returns `VisionAnalysisResponse` with:

- `image_quality_issues`
- `meal_uncertainty_flags`
- `components`
- `trace_versions`

Each `StructuredFoodComponent` contains:

- `component_id`
- `visible_name`
- `candidates`: up to 5 food candidates, each with `name`, `confidence`, and `visual_evidence`
- `portion`: `description`, `confidence`, and `visual_basis`
- `state_hints`: optional cooked/raw/fried/grilled/plain/sauced signals when visible
- `hidden_ingredient_risks`: optional ingredient risks with `likelihood`, `macro_impact`, and optional `rationale`

Legacy simple payloads such as `{"components": [{"name": "...", "confidence": ..., "portion_hint": "..."}]}` are still accepted. They are converted into the structured response with `meal_uncertainty_flags=["legacy_simple_response"]`.

## Caching

`ClaudeCliVisionClient` and `ClaudeVisionClient` accept an optional cache object that implements `VisionResultCache`.
Cache keys include:

- normalized image hash
- model name
- prompt text

Structured and legacy-compatible payloads are cached separately so either API can reuse the same analysis.
Structured cache entries are tagged with the vision schema version.
`JsonFileVisionCache` stores serialized payloads in a local JSON file and does not persist raw images.
Writes use a temporary file plus `os.replace()` so local single-user updates are atomic enough for this use case.

## Verification

- `pytest tests/vision/test_claude_vision.py`
- `pytest tests/`
- `ruff check services/vision/ tests/vision/`
