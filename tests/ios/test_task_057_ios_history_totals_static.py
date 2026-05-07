from __future__ import annotations

from pathlib import Path

IOS_APP_DIR = Path("apps/ios/MacroAgentCapture")
ROOT_VIEW = IOS_APP_DIR / "RootView.swift"
RESULT_DEBUG_VIEW = IOS_APP_DIR / "ResultDebugView.swift"
CAPTURE_FLOW_STORE = IOS_APP_DIR / "CaptureFlowStore.swift"
API_CLIENT = IOS_APP_DIR / "APIClient.swift"


def _read(path: Path) -> str:
    assert path.exists(), f"Missing required file: {path.as_posix()}"
    return path.read_text(encoding="utf-8")


def test_task_057_history_tab_and_history_view_are_wired() -> None:
    root_view = _read(ROOT_VIEW)
    result_debug = _read(RESULT_DEBUG_VIEW)

    assert "HistoryView(store: store)" in root_view
    assert 'Label("History", systemImage: "calendar")' in root_view

    assert "struct HistoryView: View" in result_debug
    assert '.navigationTitle("History")' in result_debug
    assert 'Text("Daily totals")' in result_debug
    assert 'Text("HealthKit export prep")' in result_debug
    assert 'Text("Meal history")' in result_debug
    assert 'Text("No entries found for this day.")' in result_debug


def test_task_057_history_view_includes_all_seven_daily_total_metrics() -> None:
    result_debug = _read(RESULT_DEBUG_VIEW)

    expected_metric_rows = (
        'HistoryMetricRow(label: "kcal", value: totals.kcal, decimals: 0)',
        'HistoryMetricRow(label: "protein_g", value: totals.proteinG, decimals: 1)',
        'HistoryMetricRow(label: "carbs_g", value: totals.carbsG, decimals: 1)',
        'HistoryMetricRow(label: "fat_g", value: totals.fatG, decimals: 1)',
        'HistoryMetricRow(label: "sugar_g", value: totals.sugarG, decimals: 1)',
        'HistoryMetricRow(label: "sodium_mg", value: totals.sodiumMG, decimals: 0)',
        'HistoryMetricRow(label: "fiber_g", value: totals.fiberG, decimals: 1)',
    )
    for row in expected_metric_rows:
        assert row in result_debug

    assert (
        'Text("Meals: \\(totals.mealCount) • Active entries: '
        '\\(totals.activeEntryCount)")'
    ) in result_debug


def test_task_057_capture_flow_store_refreshes_history_totals_and_healthkit_export() -> None:
    store_text = _read(CAPTURE_FLOW_STORE)

    assert "@Published private(set) var isRefreshingHistory: Bool" in store_text
    assert (
        "@Published private(set) var mealHistory: "
        "[UserNutritionLedgerHistoryEntry]"
    ) in store_text
    assert (
        "@Published private(set) var dailyTotals: "
        "UserDailyNutritionTotalsResponse?"
    ) in store_text
    assert (
        "@Published private(set) var healthKitExportPreparation: "
        "HealthKitExportPreparationResponse?"
    ) in store_text
    assert "@Published private(set) var historyLoadError: String?" in store_text

    assert "func refreshHistoryAndTotals() async" in store_text
    assert "let historyResponse = try await client.fetchMealHistory(" in store_text
    assert "let totalsResponse = try await client.fetchDailyTotals(" in store_text
    assert "let exportPreparation = try await client.prepareHealthKitExport(" in store_text
    assert "mealHistory = historyResponse.entries" in store_text
    assert "dailyTotals = totalsResponse" in store_text
    assert "healthKitExportPreparation = exportPreparation" in store_text


def test_task_057_api_client_uses_history_totals_and_healthkit_export_routes() -> None:
    api_client_text = _read(API_CLIENT)

    assert "func fetchMealHistory(" in api_client_text
    assert "func fetchDailyTotals(" in api_client_text
    assert "func prepareHealthKitExport(" in api_client_text

    assert 'URLQueryItem(name: "user_id", value: userID)' in api_client_text
    assert 'URLQueryItem(name: "local_date", value: localDate)' in api_client_text
    assert (
        'URLQueryItem(name: "include_inactive", value: '
        'includeInactive ? "true" : "false")'
    ) in api_client_text
    assert 'URLQueryItem(name: "limit", value: String(limit))' in api_client_text

    assert 'makeURL(path: "/v1/users/history", queryItems: queryItems)' in api_client_text
    assert 'makeURL(path: "/v1/users/daily-totals", queryItems: queryItems)' in api_client_text
    assert (
        'makeURL(path: "/v1/users/healthkit-export-prep", queryItems: queryItems)'
    ) in api_client_text
