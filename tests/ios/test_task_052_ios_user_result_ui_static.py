from __future__ import annotations

from pathlib import Path

IOS_APP_DIR = Path("apps/ios/MacroAgentCapture")
RESULT_DEBUG = IOS_APP_DIR / "ResultDebugView.swift"
ROOT_VIEW = IOS_APP_DIR / "RootView.swift"
API_CLIENT = IOS_APP_DIR / "APIClient.swift"
README = IOS_APP_DIR / "README.md"
RUNBOOK = Path("docs/ios_native_capture_v0_5.md")


def _read(path: Path) -> str:
    assert path.exists(), f"Missing required file: {path.as_posix()}"
    return path.read_text(encoding="utf-8")


def test_result_view_references_all_seven_user_metrics_with_best_and_range() -> None:
    text = _read(RESULT_DEBUG)

    assert "struct ResultView: View" in text
    assert 'Text("Nutrition estimate")' in text
    assert 'Text("Best estimate with conservative range.")' in text

    expected_metric_keys = (
        'metricKey: "kcal"',
        'metricKey: "protein_g"',
        'metricKey: "carbs_g"',
        'metricKey: "fat_g"',
        'metricKey: "sugar_g"',
        'metricKey: "sodium_mg"',
        'metricKey: "fiber_g"',
    )
    for key in expected_metric_keys:
        assert key in text

    assert 'Text("~\\(formatted(metric.bestEstimate)) \\(unit)")' in text
    assert (
        'Text("Range \\(formatted(metric.minEstimate)) - '
        '\\(formatted(metric.maxEstimate)) \\(unit)")'
    ) in text
    assert 'Text("Source: \\(metric.source)")' in text


def test_result_view_status_and_confidence_cover_accept_warn_clarify_block() -> None:
    text = _read(RESULT_DEBUG)

    assert "Text(response.status.rawValue)" in text
    assert (
        'Text("Confidence: \\(response.uncertaintySummary.confidenceLabel.capitalized)")'
        in text
    )

    assert "private func statusColor(for status: AnalysisDecision) -> Color" in text
    assert "case .accept:" in text
    assert "case .warn:" in text
    assert "case .clarify:" in text
    assert "case .block:" in text

    assert "private func statusMessage(for status: AnalysisDecision) -> String" in text
    assert 'return "Estimate is suitable for logging."' in text
    assert 'return "Estimate is usable but uncertainty is higher than target."' in text
    assert 'return "A quick confirmation is needed before trusting this estimate."' in text
    assert 'return "Unable to provide a safe estimate from this capture."' in text


def test_result_view_surfaces_uncertainty_drivers_and_caps_primary_questions() -> None:
    text = _read(RESULT_DEBUG)

    assert "Array(response.uncertaintySummary.uncertaintyFlags.prefix(3))" in text
    assert 'Text("High-impact uncertainty drivers")' in text

    assert "private func primaryQuestions(for response: AnalyzePhotoResponse) -> [String]" in text
    assert "return Array(response.clarifyQuestions.map(\\.text).prefix(2))" in text
    assert "return Array(derived.prefix(2))" in text
    assert 'Text("Primary question\\(primaryQuestions.count > 1 ? "s" : "")")' in text


def test_result_view_exposes_portion_consumed_sauce_oil_and_drink_add_ins_quick_corrections(
) -> None:
    text = _read(RESULT_DEBUG)

    assert "ForEach(sortedQuickCorrections(response.quickCorrections))" in text
    assert "UserQuickCorrectionCard(" in text
    assert "await store.applyQuickCorrection(" in text

    expected_quick_correction_ids = (
        'case "portion_size_quick_adjust":',
        'case "consumed_amount_check":',
        'case "hidden_sauce_oil_check":',
        'case "drink_add_ins_check":',
    )
    for correction_id in expected_quick_correction_ids:
        assert correction_id in text

    expected_quick_correction_titles = (
        'return "Portion size"',
        'return "Amount consumed"',
        'return "Sauce/oil"',
        'return "Drink add-ins"',
    )
    for title in expected_quick_correction_titles:
        assert title in text


def test_result_debug_remains_secondary_tab_for_raw_request_response_details() -> None:
    result_text = _read(RESULT_DEBUG)
    root_text = _read(ROOT_VIEW)

    assert 'Text("Need raw request/response details? Open the Debug tab.")' in result_text
    assert "struct ResultDebugView: View" in result_text
    assert 'Section("Result")' in result_text
    assert 'DebugRow(label: "request_id", value: response.requestID)' in result_text
    assert 'DebugRow(label: "status", value: response.status.rawValue)' in result_text
    assert 'DebugRow(label: "trace_id", value: response.traceID)' in result_text
    assert 'Section("Debug")' in result_text
    assert '.navigationTitle("Result / Debug")' in result_text

    assert "ResultView(store: store)" in root_text
    assert "ResultDebugView(store: store)" in root_text
    assert 'Label("Result", systemImage: "fork.knife.circle")' in root_text
    assert 'Label("Debug", systemImage: "terminal")' in root_text


def test_backend_boundary_and_manual_iphone_runbook_references_still_exist() -> None:
    api_text = _read(API_CLIENT)
    readme_text = _read(README)
    runbook_text = _read(RUNBOOK)

    assert 'makeURL(path: "/v1/meals/analyze-photo")' in api_text
    assert 'request.httpMethod = "POST"' in api_text

    for swift_file in IOS_APP_DIR.glob("*.swift"):
        lowered = _read(swift_file).lower()
        assert "openai" not in lowered
        assert "anthropic" not in lowered

    assert "## Open / Install on iPhone" in readme_text
    assert "## Manual Phone-to-Mac Smoke Test Runbook" in readme_text
    assert "python -m services.api.local_server --host 0.0.0.0 --port 8765" in readme_text
    assert "http://<mac-lan-ip>:8765" in readme_text
    assert "Select your connected iPhone as the run destination." in readme_text

    assert "Open the checked-in iOS project" in runbook_text
    assert "select a connected physical iPhone" in runbook_text
    assert "Set server URL to http://<mac-lan-ip>:8765" in runbook_text
