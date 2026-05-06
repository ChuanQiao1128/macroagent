from __future__ import annotations

from pathlib import Path

IOS_APP_DIR = Path("apps/ios/MacroAgentCapture")
API_CLIENT = IOS_APP_DIR / "APIClient.swift"
CAPTURE_SCREEN = IOS_APP_DIR / "CaptureScreenView.swift"
CAPTURE_FLOW_STORE = IOS_APP_DIR / "CaptureFlowStore.swift"
METADATA_PREVIEW = IOS_APP_DIR / "MetadataPreviewView.swift"
MODELS = IOS_APP_DIR / "Models.swift"
RESULT_DEBUG = IOS_APP_DIR / "ResultDebugView.swift"
README = IOS_APP_DIR / "README.md"
RUNBOOK = Path("docs/ios_native_capture_v0_5.md")


def _read(path: Path) -> str:
    assert path.exists(), f"Missing required file: {path.as_posix()}"
    return path.read_text(encoding="utf-8")


def test_api_client_posts_to_analyze_photo_endpoint_with_expected_request_shape() -> None:
    text = _read(API_CLIENT)

    assert "func analyzePhoto(_ requestEnvelope: AnalyzePhotoRequestEnvelope)" in text
    assert 'makeURL(path: "/v1/meals/analyze-photo")' in text
    assert 'request.httpMethod = "POST"' in text
    assert 'request.setValue("application/json", forHTTPHeaderField: "Content-Type")' in text
    assert 'request.setValue("application/json", forHTTPHeaderField: "Accept")' in text
    assert "encoder.encode(requestEnvelope)" in text


def test_metadata_preview_is_explicitly_present_before_analyze_action() -> None:
    metadata_text = _read(METADATA_PREVIEW)
    capture_text = _read(CAPTURE_SCREEN)

    assert (
        "Capture metadata payload that will be sent to `/v1/meals/analyze-photo`."
        in metadata_text
    )
    assert "Review the Metadata tab preview before sending Analyze." in capture_text


def test_result_view_renders_status_reasons_trace_id_clarify_questions_and_seven_metrics() -> None:
    text = _read(RESULT_DEBUG)

    assert 'DebugRow(label: "status", value: response.status.rawValue)' in text
    assert 'DebugRow(label: "trace_id", value: response.traceID)' in text
    assert 'Text("reasons")' in text
    assert 'Text("clarify_questions")' in text

    expected_metric_rows = (
        'NutritionMetricRow(label: "kcal", metric: nutrition.kcal)',
        'NutritionMetricRow(label: "protein_g", metric: nutrition.proteinG)',
        'NutritionMetricRow(label: "carbs_g", metric: nutrition.carbsG)',
        'NutritionMetricRow(label: "fat_g", metric: nutrition.fatG)',
        'NutritionMetricRow(label: "sugar_g", metric: nutrition.sugarG)',
        'NutritionMetricRow(label: "sodium_mg", metric: nutrition.sodiumMG)',
        'NutritionMetricRow(label: "fiber_g", metric: nutrition.fiberG)',
    )
    for row in expected_metric_rows:
        assert row in text


def test_analyze_error_states_cover_invalid_url_network_failure_and_invalid_response() -> None:
    text = _read(CAPTURE_FLOW_STORE)

    assert "case invalidServerURL(String)" in text
    assert "case networkFailure(String)" in text
    assert "case invalidResponse(String)" in text

    assert 'return "Invalid server URL"' in text
    assert 'return "Network failure"' in text
    assert 'return "Invalid response"' in text

    assert "case .invalidBaseURL(let raw):" in text
    assert 'return .invalidServerURL("Invalid server URL: \\(raw)")' in text
    assert "if let urlError = error as? URLError" in text
    assert "return .networkFailure(urlError.localizedDescription)" in text
    assert "if error is DecodingError" in text
    assert 'return .invalidResponse("Response JSON did not match expected fields.")' in text


def test_v0_4_response_contract_field_names_are_statically_referenced() -> None:
    text = _read(MODELS)

    assert 'case requestID = "request_id"' in text
    assert 'case clarifyQuestions = "clarify_questions"' in text
    assert 'case traceID = "trace_id"' in text
    assert 'case ledgerEntryID = "ledger_entry_id"' in text
    assert 'case uncertaintySummary = "uncertainty_summary"' in text

    expected_nutrition_keys = (
        'case proteinG = "protein_g"',
        'case carbsG = "carbs_g"',
        'case fatG = "fat_g"',
        'case sugarG = "sugar_g"',
        'case sodiumMG = "sodium_mg"',
        'case fiberG = "fiber_g"',
    )
    for key in expected_nutrition_keys:
        assert key in text


def test_readme_runbook_documents_lan_ip_server_start_and_response_verification() -> None:
    text = _read(README)

    assert "## Manual Phone-to-Mac Smoke Test Runbook" in text
    assert "ipconfig getifaddr en0" in text
    assert 'ifconfig | rg "inet "' in text
    assert "python -m services.api.local_server --host 0.0.0.0 --port 8765" in text
    assert "http://<mac-lan-ip>:8765" in text
    assert "Open `Metadata` tab and confirm the request preview" in text
    assert "Confirm `status`, `trace_id`, and `reasons`." in text
    assert "Confirm seven nutrition metrics render when status is not `BLOCK`" in text
    assert "Confirm `clarify_questions` are shown when status is `CLARIFY`." in text


def test_readme_runbook_includes_same_wifi_and_firewall_troubleshooting_and_mock_first_behavior(
) -> None:
    readme_text = _read(README)
    runbook_text = _read(RUNBOOK)

    assert "## Mock-First Backend Behavior (Explicit)" in readme_text
    assert "deterministic mock-first analysis" in readme_text
    assert "transport and contract validation" in readme_text

    assert "Same Wi-Fi/LAN" in readme_text
    assert "macOS firewall" in readme_text
    assert "allow incoming connections for Terminal/Python" in readme_text

    assert "Wire the iOS app to the local Mac server" in runbook_text
    assert "same Wi-Fi network as" in runbook_text
