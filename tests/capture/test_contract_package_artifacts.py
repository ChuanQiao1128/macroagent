from __future__ import annotations

import json
from pathlib import Path

from services.api import AnalyzePhotoFacadeResponse
from services.capture import DeviceCaptureMetadata, PhotoAnalyzeRequest, PhotoAnalyzeResponse
from services.capture.src.contract_package import CaptureTraceArtifact, export_contract_package

CONTRACTS_DIR = Path("services/capture/contracts")
SCHEMAS_DIR = CONTRACTS_DIR / "schemas"
EXAMPLES_DIR = CONTRACTS_DIR / "examples"
FIELD_GUIDE_PATH = CONTRACTS_DIR / "ios_capture_field_guide.md"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_forbidden_paths(value: object, bucket: list[str]) -> None:
    forbidden_image_keys = {
        "image",
        "image_bytes",
        "raw_image",
        "raw_bytes",
        "base64_image",
        "image_base64",
    }

    if isinstance(value, dict):
        for key, nested in value.items():
            if key in forbidden_image_keys:
                bucket.append(key)
            _collect_forbidden_paths(nested, bucket)
        return
    if isinstance(value, list):
        for nested in value:
            _collect_forbidden_paths(nested, bucket)
        return
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate.startswith("data:image/"):
            bucket.append(value)
        if candidate.startswith("/") or candidate.startswith("~/"):
            bucket.append(value)


def test_committed_schema_snapshots_match_backend_models() -> None:
    expected = {
        "photo_analyze_request.schema.json": PhotoAnalyzeRequest.model_json_schema(),
        "photo_analyze_response.schema.json": PhotoAnalyzeResponse.model_json_schema(),
        "capture_metadata.schema.json": DeviceCaptureMetadata.model_json_schema(),
        "capture_trace_artifact.schema.json": CaptureTraceArtifact.model_json_schema(),
    }

    for filename, model_schema in expected.items():
        committed_schema = _load_json(SCHEMAS_DIR / filename)
        assert committed_schema == model_schema


def test_contract_export_is_deterministic_and_matches_committed_artifacts(tmp_path: Path) -> None:
    export_contract_package(tmp_path)
    generated_contracts_root = tmp_path

    generated_files = sorted(
        path.relative_to(generated_contracts_root)
        for path in generated_contracts_root.rglob("*.json")
    )
    committed_files = sorted(
        path.relative_to(CONTRACTS_DIR) for path in CONTRACTS_DIR.rglob("*.json")
    )
    assert generated_files == committed_files

    for relative_path in committed_files:
        generated_text = (generated_contracts_root / relative_path).read_text(encoding="utf-8")
        committed_text = (CONTRACTS_DIR / relative_path).read_text(encoding="utf-8")
        assert generated_text == committed_text


def test_sample_payloads_validate_against_backend_models_and_are_synthetic() -> None:
    example_names = [
        "top_down_photo_with_depth",
        "weak_side_angle_without_reference",
        "barcode_packaged_food",
        "missing_scale_clarify_case",
    ]

    for name in example_names:
        payload = _load_json(EXAMPLES_DIR / f"{name}.json")
        PhotoAnalyzeRequest.model_validate(payload["photo_analyze_request"])
        PhotoAnalyzeResponse.model_validate(payload["photo_analyze_response"])
        AnalyzePhotoFacadeResponse.model_validate(payload["analyze_photo_facade_response"])
        CaptureTraceArtifact.model_validate(payload["capture_trace_artifact"])

        forbidden_values: list[str] = []
        _collect_forbidden_paths(payload, forbidden_values)
        assert not forbidden_values


def test_ios_field_guide_covers_required_iphone_api_mappings() -> None:
    guide = FIELD_GUIDE_PATH.read_text(encoding="utf-8")

    for expected_phrase in (
        "AVCaptureDevice.Position",
        "CMMotionManager.deviceMotion?.attitude",
        "ARWorldTrackingConfiguration.supportsFrameSemantics",
        "VNRecognizeTextRequest",
        "VNDetectBarcodesRequest",
        "reference_object_hint",
        "barcode_payload",
        "barcode_payload_safe",
        "ocr_text_snippets",
        "depth_available",
        "depth_quality",
        "lidar_available",
    ):
        assert expected_phrase in guide
