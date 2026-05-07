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


def _assert_single_photo_quick_corrections(response) -> None:
    assert 1 <= len(response.quick_corrections) <= 4
    for correction in response.quick_corrections:
        assert correction.correction_id
        assert correction.label
        assert 2 <= len(correction.options) <= 4


def test_accept_fixture_returns_complete_response() -> None:
    response = analyze_photo_facade(_request("req_accept_fixture"))

    assert response.status == "ACCEPT"
    _assert_complete_nutrition(response)
    assert response.clarify_questions == []
    assert response.trace_id == "trace:req_accept_fixture"
    assert response.ledger_entry_id is None
    assert response.uncertainty_summary.confidence_label == "high"
    _assert_single_photo_quick_corrections(response)


def test_accept_fixture_uses_derived_volume_when_capture_metadata_provides_it() -> None:
    data: dict[str, Any] = {
        "payload": _payload("req_accept_volume_fixture"),
        "options": {"log_anyway": False},
    }
    data["payload"]["capture_metadata"].update(
        {
            "arkit_scene_depth_supported": True,
            "arkit_smoothed_scene_depth_supported": True,
            "arkit_depth_available": True,
            "arkit_depth_quality": "high",
            "arkit_depth_map_width_px": 256,
            "arkit_depth_map_height_px": 192,
            "arkit_confidence_coverage": 0.86,
            "camera_intrinsics_available": True,
            "food_volume_estimate_ml_p10": 180.0,
            "food_volume_estimate_ml_p50": 200.0,
            "food_volume_estimate_ml_p90": 220.0,
            "food_volume_estimate_confidence": 0.74,
            "food_volume_estimate_method": "arkit_depth_region",
        }
    )

    response = analyze_photo_facade(AnalyzePhotoFacadeRequest.model_validate(data))

    assert response.status == "WARN"
    assert response.nutrition is not None
    assert response.nutrition.kcal.min_estimate == 152.1
    assert response.nutrition.kcal.best_estimate == 195.0
    assert response.nutrition.kcal.max_estimate == 257.4
    assert "volume_geometry_estimate" in response.uncertainty_summary.uncertainty_flags
    assert "volume_density_estimate" in response.uncertainty_summary.uncertainty_flags
    correction_ids = {correction.correction_id for correction in response.quick_corrections}
    assert "portion_size_quick_adjust" in correction_ids
    assert "hidden_sauce_oil_check" in correction_ids


def test_accept_fixture_uses_manual_container_when_no_depth_volume_is_available() -> None:
    data: dict[str, Any] = {
        "payload": _payload("req_accept_manual_container_fixture"),
        "options": {"log_anyway": False},
    }
    data["payload"]["capture_metadata"].update(
        {
            "arkit_depth_available": False,
            "arkit_depth_quality": "none",
            "food_volume_estimate_ml_p10": None,
            "food_volume_estimate_ml_p50": None,
            "food_volume_estimate_ml_p90": None,
            "food_volume_estimate_confidence": None,
            "food_volume_estimate_method": None,
            "reference_object_hint": "container_rice_bowl_300ml",
        }
    )

    response = analyze_photo_facade(AnalyzePhotoFacadeRequest.model_validate(data))

    assert response.status == "WARN"
    assert response.nutrition is not None
    assert response.nutrition.kcal.min_estimate == 236.6
    assert response.nutrition.kcal.best_estimate == 292.5
    assert response.nutrition.kcal.max_estimate == 374.4
    assert "manual_container_volume_estimate" in response.uncertainty_summary.uncertainty_flags
    assert "volume_density_estimate" in response.uncertainty_summary.uncertainty_flags
    correction_ids = {correction.correction_id for correction in response.quick_corrections}
    assert "portion_size_quick_adjust" in correction_ids


def test_warn_fixture_returns_complete_response_with_uncertainty_flags() -> None:
    response = analyze_photo_facade(_request("req_warn_fixture"))

    assert response.status == "WARN"
    _assert_complete_nutrition(response)
    assert response.clarify_questions == []
    assert response.trace_id == "trace:req_warn_fixture"
    assert response.ledger_entry_id is None
    assert response.uncertainty_summary.confidence_label == "medium"
    assert response.uncertainty_summary.uncertainty_flags
    _assert_single_photo_quick_corrections(response)


def test_clarify_fixture_returns_questions_without_log_anyway() -> None:
    response = analyze_photo_facade(_request("req_clarify_fixture"))

    assert response.status == "CLARIFY"
    _assert_complete_nutrition(response)
    assert len(response.clarify_questions) >= 2
    assert response.trace_id == "trace:req_clarify_fixture"
    assert response.ledger_entry_id is None
    assert response.uncertainty_summary.confidence_label == "low"
    _assert_single_photo_quick_corrections(response)


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
    _assert_single_photo_quick_corrections(response)


def test_block_fixture_refuses_llm_raw_macro_input() -> None:
    response = analyze_photo_facade(_request("req_block_fixture"))

    assert response.status == "BLOCK"
    assert response.nutrition is None
    assert "unsupported raw macro claim from llm" in response.reasons
    assert response.clarify_questions == []
    assert response.trace_id == "trace:req_block_fixture"
    assert response.ledger_entry_id is None
    assert response.uncertainty_summary.confidence_label == "low"
    assert response.quick_corrections == []
