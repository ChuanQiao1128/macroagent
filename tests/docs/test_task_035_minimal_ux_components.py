from __future__ import annotations

from pathlib import Path

COMPONENTS_DIR = Path("apps/frontend/components")
PAGE_FILE = Path("apps/frontend/pages/meal/[id].tsx")

ESTIMATE_RANGE_CARD = COMPONENTS_DIR / "EstimateRangeCard.tsx"
CLARIFICATION_PROMPT = COMPONENTS_DIR / "ClarificationPrompt.tsx"
LOG_ANYWAY_BUTTON = COMPONENTS_DIR / "LogAnywayButton.tsx"
TAKEOFF_TRACE_PANEL = COMPONENTS_DIR / "TakeoffTracePanel.tsx"
WEEKLY_REVIEW_CARD = COMPONENTS_DIR / "WeeklyReviewCard.tsx"
UNCERTAINTY_DEBT_CARD = COMPONENTS_DIR / "UncertaintyDebtCard.tsx"

TASK_035_FILES = (
    ESTIMATE_RANGE_CARD,
    CLARIFICATION_PROMPT,
    LOG_ANYWAY_BUTTON,
    TAKEOFF_TRACE_PANEL,
    WEEKLY_REVIEW_CARD,
    UNCERTAINTY_DEBT_CARD,
    PAGE_FILE,
)


def _read(path: Path) -> str:
    assert path.exists(), f"Missing TASK-035 file: {path.as_posix()}"
    return path.read_text(encoding="utf-8")


def test_task_035_files_exist() -> None:
    missing = [path.as_posix() for path in TASK_035_FILES if not path.exists()]
    assert not missing, f"Missing TASK-035 files: {missing}"


def test_estimate_range_card_shows_required_fields() -> None:
    text = _read(ESTIMATE_RANGE_CARD)

    required_props = (
        "bestEstimateKcal",
        "likelyLowKcal",
        "likelyHighKcal",
        "confidenceLabel",
        "mainUncertaintyDriver",
    )
    for prop in required_props:
        assert prop in text, f"EstimateRangeCard missing required prop: {prop}"

    required_labels = (
        "Best estimate",
        "Likely range",
        "Confidence",
        "Main uncertainty driver",
    )
    for label in required_labels:
        assert label in text, f"EstimateRangeCard missing required label: {label}"


def test_clarification_prompt_shows_at_most_one_question() -> None:
    text = _read(CLARIFICATION_PROMPT)

    assert "const firstQuestion = questions[0]" in text
    assert "if (!firstQuestion)" in text
    assert "firstQuestion.options.map" in text
    assert "questions.map" not in text


def test_log_anyway_button_records_wide_range_flag() -> None:
    button_text = _read(LOG_ANYWAY_BUTTON)
    page_text = _read(PAGE_FILE)

    assert "wideRangeFlag: true" in button_text
    assert "loggedAt: new Date().toISOString()" in button_text
    assert "handleLogAnyway" in page_text
    assert "finalizeLog(wideRangeFlag, loggedAt)" in page_text


def test_takeoff_trace_panel_is_collapsed_by_default() -> None:
    text = _read(TAKEOFF_TRACE_PANEL)

    assert "defaultOpen = false" in text
    assert "open={defaultOpen}" in text
    assert "Trace (optional)" in text
    assert "You can log without opening this." in text


def test_weekly_review_card_shows_uncertainty_debt() -> None:
    weekly_text = _read(WEEKLY_REVIEW_CARD)
    debt_text = _read(UNCERTAINTY_DEBT_CARD)

    assert "UncertaintyDebtCard" in weekly_text
    assert "uncertaintyDebtScore" in weekly_text
    assert "debtScore={uncertaintyDebtScore}" in weekly_text
    assert "Uncertainty Debt" in debt_text
    assert "Debt score" in debt_text


def test_meal_page_acceptance_flows_for_task_035() -> None:
    text = _read(PAGE_FILE)

    # User can log a meal without opening trace.
    assert "Log Meal" in text
    assert "Trace details are optional." in text
    assert "handleLogMeal" in text
    assert "finalizeLog(false, new Date().toISOString())" in text

    # User can select "Log Anyway" from CLARIFY state.
    assert "reviewState === \"CLARIFY\" ? (" in text
    assert "<LogAnywayButton" in text

    # Trace is discoverable but not required.
    assert "<TakeoffTracePanel entries={TRACE_ENTRIES} />" in text


def test_ui_copy_avoids_medical_claims() -> None:
    banned_terms = (
        "diagnose",
        "diagnosis",
        "treat",
        "treatment",
        "cure",
        "heals",
        "therapy",
        "prescription",
        "medical advice",
    )

    combined = "\n".join(_read(path).lower() for path in TASK_035_FILES)
    offending = [term for term in banned_terms if term in combined]
    assert not offending, f"UI copy includes medical-claim terms: {offending}"
