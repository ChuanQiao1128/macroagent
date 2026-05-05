from __future__ import annotations

import re
from pathlib import Path

ADR_DIR = Path("docs/adr")
ADR_005 = ADR_DIR / "ADR-005-ranged-estimate-ledger-policy.md"
ADR_006 = ADR_DIR / "ADR-006-meal-takeoff-workflow.md"
ADR_007 = ADR_DIR / "ADR-007-accuracy-stack.md"
ADR_008 = ADR_DIR / "ADR-008-multi-agent-eligibility-evidence-arbitration.md"
TASK_033_ADRS = (ADR_005, ADR_006, ADR_007, ADR_008)


def _read_adr(path: Path) -> str:
    assert path.exists(), f"Missing ADR file: {path.as_posix()}"
    return path.read_text(encoding="utf-8").lower()


def _assert_contains_any(text: str, variants: tuple[str, ...], *, label: str) -> None:
    assert any(variant in text for variant in variants), (
        f"Missing required content for {label}. Expected one of: {variants!r}"
    )


def _assert_contains_all(text: str, required_phrases: tuple[str, ...], *, label: str) -> None:
    missing = [phrase for phrase in required_phrases if phrase not in text]
    assert not missing, f"Missing required {label} phrases: {missing}"


def _count_phrase(text: str, phrase: str) -> int:
    return text.count(phrase)


def test_task_033_adr_files_exist() -> None:
    missing = [path.as_posix() for path in TASK_033_ADRS if not path.exists()]
    assert not missing, f"Missing TASK-033 ADR files: {missing}"


def test_adr_005_ranged_estimate_ledger_policy_content() -> None:
    text = _read_adr(ADR_005)

    _assert_contains_all(
        text,
        (
            "ranged estimate policy",
            "component_mode_sum",
            "append-only",
            "version matrix",
            "portion estimation",
            "clarify",
            "log-anyway",
            "kcal_min",
            "kcal_best",
            "kcal_max",
            "user_accepted_wide_range",
            "user_decline_clarify_reason",
            "ledgerversionmatrix",
        ),
        label=ADR_005.name,
    )
    _assert_contains_any(
        text,
        (
            "min/best/max",
            "min best max",
        ),
        label=f"{ADR_005.name} min/best/max storage requirement",
    )
    _assert_contains_any(
        text,
        (
            "best estimate vs range metadata",
            "best-estimate vs range metadata",
        ),
        label=f"{ADR_005.name} best-vs-range metadata requirement",
    )


def test_adr_006_meal_takeoff_workflow_scope_and_boundaries() -> None:
    text = _read_adr(ADR_006)

    _assert_contains_any(
        text,
        ("9-stage", "nine-stage", "9 stage", "nine stage"),
        label=f"{ADR_006.name} workflow stage count",
    )
    _assert_contains_all(
        text,
        (
            "stage boundaries",
            "agent",
            "deterministic",
            "intermediate artifact",
            "traceemitter",
            "pii-safe",
            "scale evidence resolver",
            "portion range refiner",
            "traceevent",
            "emit_stage_event",
            "image_sha256",
        ),
        label=ADR_006.name,
    )

    # Keep workflow ADR focused; broader strategy and multi-agent governance
    # belong to ADR-007 and ADR-008.
    assert _count_phrase(text, "accuracy stack") <= 1
    assert _count_phrase(text, "agent eligibility") <= 1
    assert _count_phrase(text, "evidence arbitration layer") <= 1


def test_adr_007_accuracy_stack_contains_measurable_release_gates() -> None:
    text = _read_adr(ADR_007)

    _assert_contains_all(
        text,
        (
            "accuracy stack",
            "information capture",
            "calibration",
            "personalization",
            "active learning",
            "release gates",
            "ablation",
            "cold-start",
            "first 3 meals calibration mode",
            "weekly uncertainty debt",
            "relative_range_width",
            "confidence_label",
        ),
        label=ADR_007.name,
    )

    measurable_lines = [
        line
        for line in text.splitlines()
        if re.search(r"\d", line)
        and any(
            token in line
            for token in (
                "gate",
                "threshold",
                "target",
                "max",
                "min",
                "<=",
                ">=",
                "%",
            )
        )
    ]
    assert len(measurable_lines) >= 3, (
        "ADR-007 must define measurable gates with numeric criteria. "
        f"Found {len(measurable_lines)} qualifying lines."
    )


def test_adr_008_multi_agent_eligibility_and_arbitration_rules() -> None:
    text = _read_adr(ADR_008)

    _assert_contains_all(
        text,
        (
            "agent eligibility rule",
            "approved multi-agent positions",
            "rejected multi-agent patterns",
            "evidence arbitration layer",
            "compatibility before conflict",
            "per-claim arbitration",
            "conflict resolution order",
            "cross-cultural component normalization",
            "range_overlap",
            "relative_diff:kcal",
            "category_jaccard",
        ),
        label=ADR_008.name,
    )

    llm_vote_rejection = re.search(
        r"reject\w*[\s\S]{0,160}llm[\s\S]{0,160}vot\w*[\s\S]{0,160}(calorie|kcal|macro)",
        text,
    )
    assert llm_vote_rejection, (
        "ADR-008 must explicitly reject LLM voting for calories/macros."
    )


def test_task_033_adrs_have_separated_primary_responsibilities() -> None:
    texts = {path.name: _read_adr(path) for path in TASK_033_ADRS}

    primary_scope_markers = {
        "ADR-005-ranged-estimate-ledger-policy.md": ("ranged estimate policy",),
        "ADR-006-meal-takeoff-workflow.md": ("9-stage", "nine-stage"),
        "ADR-007-accuracy-stack.md": ("accuracy stack",),
        "ADR-008-multi-agent-eligibility-evidence-arbitration.md": (
            "agent eligibility rule",
        ),
    }

    for owner, markers in primary_scope_markers.items():
        matches = [
            name
            for name, text in texts.items()
            if any(marker in text for marker in markers)
        ]
        assert matches == [owner], (
            f"Primary scope marker for {owner} should appear only in {owner}, "
            f"but found in: {matches}"
        )
