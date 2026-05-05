from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.meal.takeoff.schemas import LOG_ANYWAY_REASON_VALUES, ConfidenceLabel


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LedgerVersionMatrix(_StrictModel):
    calculator_version: str = Field(..., min_length=1)
    uncertainty_policy_version: str = Field(..., min_length=1)
    energy_density_policy_version: str = Field(..., min_length=1)
    scale_evidence_policy_version: str = Field(..., min_length=1)
    contract_yaml_version: str = Field(..., min_length=1)
    source_dataset_versions: dict[str, str] = Field(..., min_length=1)
    takeoff_pipeline_version: str = Field(..., min_length=1)
    semantic_judge_version: str | None = None


class LedgerEntry(_StrictModel):
    entry_id: str = Field(..., min_length=1)
    created_at: str = Field(
        default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds")
    )
    meal_id: str | None = None
    component_name: str | None = None
    corrected_grams: float | None = Field(default=None, gt=0)
    corrected_serving_label: str | None = None
    kcal_best: float | None = Field(default=None, ge=0)
    kcal_min: float | None = Field(default=None, ge=0)
    kcal_max: float | None = Field(default=None, ge=0)
    protein_best: float | None = Field(default=None, ge=0)
    carbs_best: float | None = Field(default=None, ge=0)
    fat_best: float | None = Field(default=None, ge=0)
    confidence_label: ConfidenceLabel | None = None
    top_uncertainty_drivers: list[str] = Field(default_factory=list)
    note: str | None = None
    supersedes_id: str | None = None
    active: bool = True
    user_id: str | None = None
    trace_id: str | None = None
    meal_signature_hash: str | None = None
    version: int = Field(default=1, ge=1)
    correction_reason: str | None = None
    user_accepted_wide_range: bool | None = None
    user_decline_clarify_reason: str | None = None
    version_matrix: LedgerVersionMatrix

    @model_validator(mode="after")
    def _validate_entry(self) -> LedgerEntry:
        if self.supersedes_id == self.entry_id:
            raise ValueError("supersedes_id must not reference the same entry_id")
        has_correction = (
            self.corrected_grams is not None or self.corrected_serving_label is not None
        )
        has_macro_estimate = (
            self.kcal_min is not None and self.kcal_best is not None and self.kcal_max is not None
        )
        if not has_correction and not has_macro_estimate:
            raise ValueError("ledger entry requires correction data or kcal min/best/max")
        if has_macro_estimate:
            if not self.kcal_min <= self.kcal_best <= self.kcal_max:
                raise ValueError("ledger kcal interval must satisfy min <= best <= max")
            if self.confidence_label is None:
                raise ValueError("macro ledger entry requires confidence_label")
            if self.meal_id is None:
                raise ValueError("macro ledger entry requires meal_id")
            if self.user_id is None:
                raise ValueError("macro ledger entry requires user_id")
            if self.trace_id is None:
                raise ValueError("macro ledger entry requires trace_id")
        if self.user_decline_clarify_reason:
            if self.user_accepted_wide_range is False:
                return self
            if (
                self.user_accepted_wide_range is True
                and self.user_decline_clarify_reason in LOG_ANYWAY_REASON_VALUES
            ):
                return self
            raise ValueError(
                "user_decline_clarify_reason requires user_accepted_wide_range=False"
                " (or accepted log-anyway reason code)"
            )
        return self


class AppendOnlyLedger:
    """In-memory append-only correction ledger with supersession chains."""

    def __init__(self) -> None:
        self._entries_by_id: dict[str, LedgerEntry] = {}
        self._entry_order: list[str] = []

    def append(self, entry: LedgerEntry) -> LedgerEntry:
        if entry.entry_id in self._entries_by_id:
            raise ValueError(f"entry_id already exists: {entry.entry_id}")

        if entry.supersedes_id is not None:
            previous_entry = self._entries_by_id.get(entry.supersedes_id)
            if previous_entry is None:
                raise ValueError(f"supersedes_id not found: {entry.supersedes_id}")
            if not previous_entry.active:
                raise ValueError(f"supersedes_id is not active: {entry.supersedes_id}")
            self._entries_by_id[previous_entry.entry_id] = previous_entry.model_copy(
                update={"active": False}
            )
            entry = entry.model_copy(update={"active": True})

        self._entries_by_id[entry.entry_id] = entry.model_copy(deep=True)
        self._entry_order.append(entry.entry_id)
        return self._entries_by_id[entry.entry_id]

    def append_correction(
        self,
        *,
        version_matrix: LedgerVersionMatrix,
        corrected_grams: float | None = None,
        corrected_serving_label: str | None = None,
        meal_id: str | None = None,
        component_name: str | None = None,
        note: str | None = None,
        supersedes_id: str | None = None,
        entry_id: str | None = None,
        created_at: str | None = None,
        user_accepted_wide_range: bool | None = None,
        user_decline_clarify_reason: str | None = None,
    ) -> LedgerEntry:
        new_entry = LedgerEntry(
            entry_id=entry_id or str(uuid.uuid4()),
            created_at=created_at
            or datetime.now().astimezone().isoformat(timespec="seconds"),
            meal_id=meal_id,
            component_name=component_name,
            corrected_grams=corrected_grams,
            corrected_serving_label=corrected_serving_label,
            note=note,
            supersedes_id=supersedes_id,
            user_accepted_wide_range=user_accepted_wide_range,
            user_decline_clarify_reason=user_decline_clarify_reason,
            version_matrix=version_matrix,
        )
        return self.append(new_entry)

    def append_meal_estimate(
        self,
        *,
        version_matrix: LedgerVersionMatrix,
        meal_id: str,
        user_id: str,
        trace_id: str,
        kcal_min: float,
        kcal_best: float,
        kcal_max: float,
        confidence_label: Literal["high", "medium", "low"],
        protein_best: float | None = None,
        carbs_best: float | None = None,
        fat_best: float | None = None,
        top_uncertainty_drivers: list[str] | None = None,
        user_accepted_wide_range: bool | None = None,
        user_decline_clarify_reason: str | None = None,
        meal_signature_hash: str | None = None,
        entry_id: str | None = None,
        created_at: str | None = None,
    ) -> LedgerEntry:
        new_entry = LedgerEntry(
            entry_id=entry_id or str(uuid.uuid4()),
            created_at=created_at
            or datetime.now().astimezone().isoformat(timespec="seconds"),
            meal_id=meal_id,
            user_id=user_id,
            trace_id=trace_id,
            kcal_min=kcal_min,
            kcal_best=kcal_best,
            kcal_max=kcal_max,
            protein_best=protein_best,
            carbs_best=carbs_best,
            fat_best=fat_best,
            confidence_label=confidence_label,
            top_uncertainty_drivers=top_uncertainty_drivers or [],
            user_accepted_wide_range=user_accepted_wide_range,
            user_decline_clarify_reason=user_decline_clarify_reason,
            meal_signature_hash=meal_signature_hash,
            version_matrix=version_matrix,
        )
        return self.append(new_entry)

    def get_entry(self, entry_id: str) -> LedgerEntry | None:
        entry = self._entries_by_id.get(entry_id)
        return entry.model_copy(deep=True) if entry is not None else None

    def list_entries(self, *, include_inactive: bool = True) -> tuple[LedgerEntry, ...]:
        ordered = [self._entries_by_id[entry_id] for entry_id in self._entry_order]
        if include_inactive:
            return tuple(entry.model_copy(deep=True) for entry in ordered)
        return tuple(entry.model_copy(deep=True) for entry in ordered if entry.active)


__all__ = [
    "AppendOnlyLedger",
    "LedgerEntry",
    "LedgerVersionMatrix",
]
