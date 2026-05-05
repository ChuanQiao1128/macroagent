from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field

from services.meal.takeoff.schemas import (
    ConfidenceLabel,
    ConsumptionFractionClaim,
    EvidenceClaim,
    EvidenceConflict,
    FoodIdentityClaim,
    MacroValueClaim,
    PortionQuantityClaim,
    StrictModel,
)

POLICY_DIR = Path(__file__).resolve().parents[1] / "policies"
DEFAULT_ARBITRATION_POLICY_PATH = POLICY_DIR / "evidence_arbitration_policy.yaml"
DEFAULT_CONFIDENCE_CALIBRATION_PATH = POLICY_DIR / "source_confidence_calibration.yaml"


class EvidenceArbitrationResult(StrictModel):
    merged_claims: list[EvidenceClaim] = Field(default_factory=list)
    conflicts: list[EvidenceConflict] = Field(default_factory=list)


class SourceConfidenceCalibration(StrictModel):
    version: str
    source_confidence_calibration: dict[str, dict[ConfidenceLabel, float]]


def arbitrate_evidence_claims(
    claims: Sequence[EvidenceClaim],
    *,
    policy_path: Path | str = DEFAULT_ARBITRATION_POLICY_PATH,
) -> EvidenceArbitrationResult:
    """Resolve compatible claims and report conflicts without computing final nutrition."""
    policy = load_evidence_arbitration_policy(policy_path)
    conflict_policy = policy["conflict_detection"]
    macro_rules = (
        policy.get("evidence_arbitration", {})
        .get("macro_value", {})
        .get("rules", {})
    )

    merged_claims: list[EvidenceClaim] = []
    conflicts: list[EvidenceConflict] = []

    grouped = _group_claims(claims)
    for (claim_type, _component_id), group in grouped.items():
        if claim_type == "portion_quantity":
            merged, group_conflicts = _resolve_portion_quantity_group(
                group,
                compatibility_threshold=float(
                    conflict_policy["portion_quantity"]["compatibility_threshold"]
                ),
            )
            merged_claims.extend(merged)
            conflicts.extend(group_conflicts)
        elif claim_type == "macro_value":
            conflicts.extend(
                _detect_macro_conflicts(
                    group,
                    conflict_threshold=float(conflict_policy["macro_value"]["conflict_threshold"]),
                    block_llm_raw_macro=_rule_blocks_llm_raw_macro(macro_rules),
                )
            )
        elif claim_type == "food_identity":
            conflicts.extend(
                _detect_food_identity_conflicts(
                    group,
                    threshold=float(conflict_policy["food_identity"]["threshold"]),
                )
            )
        elif claim_type == "consumption_fraction":
            conflicts.extend(
                _detect_consumption_fraction_conflicts(
                    group,
                    conflict_threshold=float(
                        conflict_policy["consumption_fraction"]["conflict_threshold"]
                    ),
                )
            )

    return EvidenceArbitrationResult(merged_claims=merged_claims, conflicts=conflicts)


def load_evidence_arbitration_policy(
    path: Path | str = DEFAULT_ARBITRATION_POLICY_PATH,
) -> dict[str, Any]:
    policy = _load_yaml_mapping(path)
    if "conflict_detection" not in policy:
        raise ValueError("evidence arbitration policy missing conflict_detection")
    if "evidence_arbitration" not in policy:
        raise ValueError("evidence arbitration policy missing evidence_arbitration")
    return policy


def load_source_confidence_calibration(
    path: Path | str = DEFAULT_CONFIDENCE_CALIBRATION_PATH,
) -> SourceConfidenceCalibration:
    return SourceConfidenceCalibration.model_validate(_load_yaml_mapping(path))


def calibrate_confidence_score(
    source_key: str,
    confidence_label: ConfidenceLabel,
    *,
    calibration_path: Path | str = DEFAULT_CONFIDENCE_CALIBRATION_PATH,
) -> float:
    calibration = load_source_confidence_calibration(calibration_path)
    try:
        return calibration.source_confidence_calibration[source_key][confidence_label]
    except KeyError as exc:
        raise KeyError(
            f"no confidence calibration for {source_key!r}/{confidence_label!r}"
        ) from exc


def _load_yaml_mapping(path: Path | str) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as file_obj:
        loaded = yaml.safe_load(file_obj)
    if not isinstance(loaded, dict):
        raise ValueError(f"expected YAML mapping in {path}")
    return loaded


def _group_claims(
    claims: Sequence[EvidenceClaim],
) -> dict[tuple[str, str | None], list[EvidenceClaim]]:
    grouped: dict[tuple[str, str | None], list[EvidenceClaim]] = defaultdict(list)
    for claim in claims:
        payload = claim.payload
        component_id = getattr(payload, "component_id", None)
        grouped[(payload.claim_type, component_id)].append(claim)
    return grouped


def _resolve_portion_quantity_group(
    claims: Sequence[EvidenceClaim],
    *,
    compatibility_threshold: float,
) -> tuple[list[EvidenceClaim], list[EvidenceConflict]]:
    if len(claims) < 2:
        return [], []

    payloads = [_portion_payload(claim) for claim in claims]
    units = {payload.quantity_unit for payload in payloads}
    if len(units) > 1:
        return [], [
            _conflict(
                claim_type="portion_quantity",
                claims=claims,
                metric="quantity_unit",
                metric_value="mismatch",
                severity="medium",
                decision="clarify_user",
                reason="portion quantity claims use different units",
            )
        ]

    overlap_scores = [
        _range_overlap_ratio(first, second)
        for first, second in _pairwise(payloads)
    ]
    if overlap_scores and min(overlap_scores) >= compatibility_threshold:
        return [_merge_portion_claims(claims)], []

    return [], [
        _conflict(
            claim_type="portion_quantity",
            claims=claims,
            metric="range_overlap",
            metric_value=min(overlap_scores) if overlap_scores else 0.0,
            severity="medium",
            decision="clarify_user",
            reason="portion quantity ranges are below compatibility threshold",
        )
    ]


def _detect_macro_conflicts(
    claims: Sequence[EvidenceClaim],
    *,
    conflict_threshold: float,
    block_llm_raw_macro: bool = False,
) -> list[EvidenceConflict]:
    conflicts: list[EvidenceConflict] = []

    if block_llm_raw_macro:
        for claim in claims:
            payload = _macro_payload(claim)
            if payload.value_basis != "llm_raw":
                continue
            conflicts.append(
                _conflict(
                    claim_type="macro_value",
                    claims=(claim,),
                    metric="value_basis",
                    metric_value="llm_raw",
                    severity="high",
                    decision="block_ledger_write",
                    reason="llm raw macro claims are blocked by arbitration policy",
                )
            )

    if len(claims) < 2:
        return conflicts

    for first, second in _pairwise(claims):
        first_payload = _macro_payload(first)
        second_payload = _macro_payload(second)
        for nutrient_name in ("kcal", "protein_g", "carbs_g", "fat_g"):
            first_value = getattr(first_payload, nutrient_name)
            second_value = getattr(second_payload, nutrient_name)
            if first_value is None or second_value is None:
                continue
            relative_diff = _relative_difference(float(first_value), float(second_value))
            if relative_diff > conflict_threshold:
                conflicts.append(
                    _conflict(
                        claim_type="macro_value",
                        claims=(first, second),
                        metric=f"relative_diff:{nutrient_name}",
                        metric_value=relative_diff,
                        severity="high" if relative_diff > 0.50 else "medium",
                        decision="clarify_user",
                        reason=(
                            f"{nutrient_name} claims differ by more than "
                            f"{conflict_threshold:.0%}"
                        ),
                    )
                )
    return conflicts


def _rule_blocks_llm_raw_macro(rules: Mapping[str, Any]) -> bool:
    rule_value = rules.get("llm_raw_macro")
    return isinstance(rule_value, str) and rule_value.strip().lower() == "block"


def _detect_food_identity_conflicts(
    claims: Sequence[EvidenceClaim],
    *,
    threshold: float,
) -> list[EvidenceConflict]:
    conflicts: list[EvidenceConflict] = []
    if len(claims) < 2:
        return conflicts

    for first, second in _pairwise(claims):
        first_payload = _food_identity_payload(first)
        second_payload = _food_identity_payload(second)
        if not first_payload.taxonomy_category or not second_payload.taxonomy_category:
            continue
        similarity = _category_jaccard(
            first_payload.taxonomy_category,
            second_payload.taxonomy_category,
        )
        if similarity < threshold:
            conflicts.append(
                _conflict(
                    claim_type="food_identity",
                    claims=(first, second),
                    metric="category_jaccard",
                    metric_value=similarity,
                    severity="medium",
                    decision="clarify_user",
                    reason="food identity claims disagree on taxonomy category",
                )
            )
    return conflicts


def _detect_consumption_fraction_conflicts(
    claims: Sequence[EvidenceClaim],
    *,
    conflict_threshold: float,
) -> list[EvidenceConflict]:
    conflicts: list[EvidenceConflict] = []
    if len(claims) < 2:
        return conflicts

    for first, second in _pairwise(claims):
        first_payload = _consumption_fraction_payload(first)
        second_payload = _consumption_fraction_payload(second)
        if (
            first_payload.consumption_fraction is None
            or second_payload.consumption_fraction is None
        ):
            continue
        absolute_diff = abs(
            first_payload.consumption_fraction - second_payload.consumption_fraction
        )
        if absolute_diff > conflict_threshold:
            conflicts.append(
                _conflict(
                    claim_type="consumption_fraction",
                    claims=(first, second),
                    metric="absolute_diff",
                    metric_value=absolute_diff,
                    severity="medium",
                    decision="clarify_user",
                    reason="consumption fraction claims differ beyond policy threshold",
                )
            )
    return conflicts


def _merge_portion_claims(claims: Sequence[EvidenceClaim]) -> EvidenceClaim:
    payloads = [_portion_payload(claim) for claim in claims]
    quantity_min = max(payload.quantity_min for payload in payloads)
    quantity_max = min(payload.quantity_max for payload in payloads)
    averaged_best = sum(payload.quantity_best for payload in payloads) / len(payloads)
    quantity_best = min(max(averaged_best, quantity_min), quantity_max)
    selected_claim = max(claims, key=lambda claim: claim.confidence_score)
    selected_payload = _portion_payload(selected_claim)
    claim_ids = sorted(claim.claim_id for claim in claims)

    return EvidenceClaim(
        claim_id=f"merged:{'+'.join(claim_ids)}",
        source_type=selected_claim.source_type,
        confidence_label=selected_claim.confidence_label,
        confidence_score=selected_claim.confidence_score,
        evidence_refs=_dedupe(
            [claim.claim_id for claim in claims]
            + [evidence_ref for claim in claims for evidence_ref in claim.evidence_refs]
        ),
        evidence_timestamp=max(claim.evidence_timestamp for claim in claims),
        payload=PortionQuantityClaim(
            claim_type="portion_quantity",
            component_id=selected_payload.component_id,
            quantity_min=quantity_min,
            quantity_best=quantity_best,
            quantity_max=quantity_max,
            quantity_unit=selected_payload.quantity_unit,
        ),
    )


def _range_overlap_ratio(
    first: PortionQuantityClaim,
    second: PortionQuantityClaim,
) -> float:
    first_width = first.quantity_max - first.quantity_min
    second_width = second.quantity_max - second.quantity_min
    overlap_width = min(first.quantity_max, second.quantity_max) - max(
        first.quantity_min,
        second.quantity_min,
    )
    if overlap_width < 0:
        return 0.0
    smaller_width = min(first_width, second_width)
    if smaller_width == 0:
        return 1.0 if overlap_width == 0 and first.quantity_min == second.quantity_min else 0.0
    return overlap_width / smaller_width


def _relative_difference(first: float, second: float) -> float:
    first_abs = abs(first)
    second_abs = abs(second)
    if first_abs == 0 and second_abs == 0:
        return 0.0
    if first_abs == 0 or second_abs == 0:
        return 1.0
    denominator = min(first_abs, second_abs)
    return abs(first - second) / denominator


def _category_jaccard(first: str, second: str) -> float:
    first_tokens = _category_tokens(first)
    second_tokens = _category_tokens(second)
    if not first_tokens and not second_tokens:
        return 1.0
    if not first_tokens or not second_tokens:
        return 0.0
    return len(first_tokens & second_tokens) / len(first_tokens | second_tokens)


def _category_tokens(value: str) -> set[str]:
    return {token for token in value.lower().replace("/", " ").replace("_", " ").split() if token}


def _conflict(
    *,
    claim_type: str,
    claims: Sequence[EvidenceClaim],
    metric: str,
    metric_value: float | str,
    severity: Literal["low", "medium", "high"],
    decision: Literal[
        "prefer_claim",
        "merge_claims",
        "downgrade_confidence",
        "clarify_user",
        "block_ledger_write",
    ],
    reason: str,
) -> EvidenceConflict:
    claim_ids = sorted(claim.claim_id for claim in claims)
    return EvidenceConflict(
        conflict_id=f"conflict:{claim_type}:{':'.join(claim_ids)}:{metric}",
        claim_type=claim_type,
        claim_ids=claim_ids,
        severity=severity,
        metric=metric,
        metric_value=metric_value,
        decision=decision,
        reason=reason,
    )


def _pairwise[T](items: Sequence[T]) -> Iterable[tuple[T, T]]:
    for index, first in enumerate(items):
        for second in items[index + 1 :]:
            yield first, second


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _portion_payload(claim: EvidenceClaim) -> PortionQuantityClaim:
    payload = claim.payload
    if not isinstance(payload, PortionQuantityClaim):
        raise TypeError(f"claim {claim.claim_id} is not a portion_quantity claim")
    return payload


def _macro_payload(claim: EvidenceClaim) -> MacroValueClaim:
    payload = claim.payload
    if not isinstance(payload, MacroValueClaim):
        raise TypeError(f"claim {claim.claim_id} is not a macro_value claim")
    return payload


def _food_identity_payload(claim: EvidenceClaim) -> FoodIdentityClaim:
    payload = claim.payload
    if not isinstance(payload, FoodIdentityClaim):
        raise TypeError(f"claim {claim.claim_id} is not a food_identity claim")
    return payload


def _consumption_fraction_payload(claim: EvidenceClaim) -> ConsumptionFractionClaim:
    payload = claim.payload
    if not isinstance(payload, ConsumptionFractionClaim):
        raise TypeError(f"claim {claim.claim_id} is not a consumption_fraction claim")
    return payload
