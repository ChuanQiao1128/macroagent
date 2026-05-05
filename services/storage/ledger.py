from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    note: str | None = None
    supersedes_id: str | None = None
    active: bool = True
    user_accepted_wide_range: bool | None = None
    user_decline_clarify_reason: str | None = None
    version_matrix: LedgerVersionMatrix

    @model_validator(mode="after")
    def _validate_entry(self) -> LedgerEntry:
        if self.supersedes_id == self.entry_id:
            raise ValueError("supersedes_id must not reference the same entry_id")
        if self.corrected_grams is None and self.corrected_serving_label is None:
            raise ValueError("either corrected_grams or corrected_serving_label is required")
        if self.user_decline_clarify_reason:
            if self.user_accepted_wide_range is False:
                return self
            if (
                self.user_accepted_wide_range is True
                and self.user_decline_clarify_reason == "in_a_hurry"
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
