from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from services.capture.src.schemas import PhotoAnalyzeRequest
from services.meal.takeoff.schemas import LogAnywayReason, StrictModel


class NutritionInterval(StrictModel):
    best_estimate: float = Field(ge=0)
    min_estimate: float = Field(ge=0)
    max_estimate: float = Field(ge=0)
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_range(self) -> NutritionInterval:
        if not self.min_estimate <= self.best_estimate <= self.max_estimate:
            raise ValueError(
                "nutrition interval must satisfy "
                "min_estimate <= best_estimate <= max_estimate"
            )
        return self


class NutritionIntervals(StrictModel):
    kcal: NutritionInterval
    protein_g: NutritionInterval
    carbs_g: NutritionInterval
    fat_g: NutritionInterval
    sugar_g: NutritionInterval
    sodium_mg: NutritionInterval
    fiber_g: NutritionInterval


class ClarifyQuestion(StrictModel):
    question_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class UncertaintySummary(StrictModel):
    confidence_label: Literal["high", "medium", "low"]
    relative_range_width: float | None = Field(default=None, ge=0)
    uncertainty_flags: list[str] = Field(default_factory=list)


class AnalyzePhotoOptions(StrictModel):
    log_anyway: bool = False
    log_anyway_reason: LogAnywayReason | None = None

    @model_validator(mode="after")
    def _validate_reason_pairing(self) -> AnalyzePhotoOptions:
        if self.log_anyway_reason is not None and not self.log_anyway:
            raise ValueError("log_anyway_reason requires log_anyway=true")
        return self


class AnalyzePhotoFacadeRequest(StrictModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    payload: PhotoAnalyzeRequest
    options: AnalyzePhotoOptions = Field(default_factory=AnalyzePhotoOptions)

    @model_validator(mode="before")
    @classmethod
    def _accept_raw_photo_request(cls, data):
        if not isinstance(data, dict):
            return data

        # Accept TASK-038 request shape directly and wrap with default options.
        if "payload" not in data and "options" not in data:
            return {"payload": data}
        return data


class AnalyzePhotoFacadeResponse(StrictModel):
    request_id: str = Field(min_length=1)
    status: Literal["ACCEPT", "WARN", "CLARIFY", "BLOCK"]
    nutrition: NutritionIntervals | None = None
    reasons: list[str] = Field(default_factory=list)
    clarify_questions: list[ClarifyQuestion] = Field(default_factory=list)
    trace_id: str = Field(min_length=1)
    ledger_entry_id: str | None = None
    uncertainty_summary: UncertaintySummary

    @model_validator(mode="after")
    def _validate_payload(self) -> AnalyzePhotoFacadeResponse:
        if self.status != "BLOCK" and self.nutrition is None:
            raise ValueError("nutrition is required unless status=BLOCK")
        if self.status == "CLARIFY" and not self.clarify_questions:
            raise ValueError("clarify_questions are required when status=CLARIFY")
        return self


__all__ = [
    "AnalyzePhotoFacadeRequest",
    "AnalyzePhotoFacadeResponse",
    "AnalyzePhotoOptions",
    "ClarifyQuestion",
    "NutritionInterval",
    "NutritionIntervals",
    "UncertaintySummary",
]
