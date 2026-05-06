from __future__ import annotations

from typing import Any

from services.api import AnalyzePhotoFacadeRequest, analyze_photo_facade
from services.storage.ledger import AppendOnlyLedger


def _payload(request_id: str) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "user_id": "user_tester",
        "image_identity": {
            "image_sha256": "a" * 64,
            "image_format": "heic",
            "width_px": 3024,
            "height_px": 4032,
            "byte_size": 2456789,
        },
        "capture_metadata": {
            "device_model": "iPhone15,3",
            "os_version": "iOS 18.1",
            "camera_position": "back",
            "orientation": "portrait",
            "pitch_degrees": 2.5,
            "roll_degrees": -1.0,
            "focal_length_mm": 5.7,
            "lens_hint": "wide",
            "depth_available": True,
            "depth_quality": "high",
            "lidar_available": True,
            "barcode_payload": "0123456789012",
            "ocr_text_snippets": ["2 tbsp olive oil", "chicken breast"],
            "reference_object_hint": "standard dinner plate",
            "capture_timestamp": "2026-05-01T12:34:56+00:00",
        },
    }


def _request(request_id: str, *, log_anyway: bool = False) -> AnalyzePhotoFacadeRequest:
    data: dict[str, Any] = {"payload": _payload(request_id), "options": {"log_anyway": log_anyway}}
    if log_anyway:
        data["options"]["log_anyway_reason"] = "trusts_estimate"
    return AnalyzePhotoFacadeRequest.model_validate(data)


def _assert_complete_nutrition(response) -> None:
    assert response.nutrition is not None
    for field in ("kcal", "protein_g", "carbs_g", "fat_g", "sugar_g", "sodium_mg", "fiber_g"):
        metric = getattr(response.nutrition, field)
        assert metric.min_estimate <= metric.best_estimate <= metric.max_estimate
        assert metric.source.startswith("deterministic:")


def test_accept_fixture_returns_complete_response() -> None:
    response = analyze_photo_facade(_request("req_accept_fixture"))

    assert response.status == "ACCEPT"
    _assert_complete_nutrition(response)
    assert response.clarify_questions == []
    assert response.trace_id == "trace:req_accept_fixture"
    assert response.ledger_entry_id is None
    assert response.uncertainty_summary.confidence_label == "high"


def test_warn_fixture_returns_complete_response_with_uncertainty_flags() -> None:
    response = analyze_photo_facade(_request("req_warn_fixture"))

    assert response.status == "WARN"
    _assert_complete_nutrition(response)
    assert response.clarify_questions == []
    assert response.trace_id == "trace:req_warn_fixture"
    assert response.ledger_entry_id is None
    assert response.uncertainty_summary.confidence_label == "medium"
    assert response.uncertainty_summary.uncertainty_flags


def test_clarify_fixture_returns_questions_without_log_anyway() -> None:
    response = analyze_photo_facade(_request("req_clarify_fixture"))

    assert response.status == "CLARIFY"
    _assert_complete_nutrition(response)
    assert len(response.clarify_questions) >= 2
    assert response.trace_id == "trace:req_clarify_fixture"
    assert response.ledger_entry_id is None
    assert response.uncertainty_summary.confidence_label == "low"


def test_clarify_fixture_can_log_anyway_and_write_ledger_entry() -> None:
    ledger = AppendOnlyLedger()

    response = analyze_photo_facade(
        _request("req_clarify_fixture_log_anyway", log_anyway=True),
        ledger=ledger,
    )

    assert response.status == "CLARIFY"
    _assert_complete_nutrition(response)
    assert response.ledger_entry_id is not None
    entry = ledger.get_entry(response.ledger_entry_id)
    assert entry is not None
    assert entry.trace_id == "trace:req_clarify_fixture_log_anyway"
    assert entry.user_accepted_wide_range is True
    assert entry.user_decline_clarify_reason == "trusts_estimate"


def test_block_fixture_refuses_llm_raw_macro_input() -> None:
    response = analyze_photo_facade(_request("req_block_fixture"))

    assert response.status == "BLOCK"
    assert response.nutrition is None
    assert "unsupported raw macro claim from llm" in response.reasons
    assert response.clarify_questions == []
    assert response.trace_id == "trace:req_block_fixture"
    assert response.ledger_entry_id is None
    assert response.uncertainty_summary.confidence_label == "low"
