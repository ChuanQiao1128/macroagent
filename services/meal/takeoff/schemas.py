from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ConfidenceLabel = Literal["high", "medium", "low"]
QuantityUnit = Literal["g", "ml", "piece", "serving"]
PortionPhase = Literal["as_served", "as_consumed", "remaining"]
ScaleEvidenceType = Literal[
    "reference_object",
    "personal_container",
    "barcode_serving",
    "label_ocr_serving",
    "manual_selection",
    "phone_motion_calibration",
    "lidar_depth",
    "multi_shot_photogrammetry",
    "before_after_delta",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FoodIdentityClaim(StrictModel):
    claim_type: Literal["food_identity"]
    component_id: str
    raw_name: str
    canonical_name: str | None = None
    taxonomy_category: str | None = None
    cuisine_tags: list[str] = Field(default_factory=list)


class ComponentPresenceClaim(StrictModel):
    claim_type: Literal["component_presence"]
    component_id: str
    present: bool
    visual_status: Literal["visible", "visible_unknown_type", "suspected_hidden", "not_visible"]


class PortionQuantityClaim(StrictModel):
    claim_type: Literal["portion_quantity"]
    component_id: str
    quantity_min: float = Field(ge=0)
    quantity_best: float = Field(ge=0)
    quantity_max: float = Field(ge=0)
    quantity_unit: QuantityUnit

    @model_validator(mode="after")
    def _validate_quantity_order(self) -> PortionQuantityClaim:
        if not self.quantity_min <= self.quantity_best <= self.quantity_max:
            raise ValueError("portion quantity must satisfy min <= best <= max")
        return self


class MacroValueClaim(StrictModel):
    claim_type: Literal["macro_value"]
    component_id: str | None = None
    kcal: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    value_basis: Literal[
        "llm_raw",
        "deterministic_recompute",
        "label_ocr",
        "database_source",
        "menu_ocr",
    ]

    @model_validator(mode="after")
    def _validate_has_macro_value(self) -> MacroValueClaim:
        values = (self.kcal, self.protein_g, self.carbs_g, self.fat_g)
        if all(value is None for value in values):
            raise ValueError("macro value claim must include at least one macro value")
        return self


class SourceMatchClaim(StrictModel):
    claim_type: Literal["source_match"]
    component_id: str
    source_ref: str
    source_name: str
    source_type: Literal["usda", "off", "fsanz", "nzfcd", "personal", "label_ocr"]


class ScaleEvidenceClaim(StrictModel):
    claim_type: Literal["scale_evidence"]
    evidence_id: str
    evidence_type: ScaleEvidenceType
    usable_for_scale: bool


class ConsumptionFractionClaim(StrictModel):
    claim_type: Literal["consumption_fraction"]
    portion_phase: PortionPhase
    consumption_fraction: float | None = Field(default=None, ge=0.0, le=1.0)


EvidenceClaimValue = Annotated[
    FoodIdentityClaim
    | ComponentPresenceClaim
    | PortionQuantityClaim
    | MacroValueClaim
    | SourceMatchClaim
    | ScaleEvidenceClaim
    | ConsumptionFractionClaim,
    Field(discriminator="claim_type"),
]


class EvidenceClaim(StrictModel):
    claim_id: str
    source_type: Literal[
        "vision",
        "ocr_label",
        "ocr_menu",
        "barcode",
        "nutrition_database",
        "personal_prior",
        "user_correction",
        "manual_entry",
        "deterministic_calculator",
    ]
    confidence_label: ConfidenceLabel
    confidence_score: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str]
    evidence_timestamp: str
    payload: EvidenceClaimValue


class SourceQuality(StrictModel):
    identity_confidence: ConfidenceLabel
    nutrition_value_confidence: ConfidenceLabel
    regional_relevance: ConfidenceLabel
    verification_status: Literal[
        "official",
        "user_contributed",
        "ocr_unconfirmed",
        "user_confirmed",
        "personal",
    ]


class EvidenceConflict(StrictModel):
    conflict_id: str
    claim_type: str
    claim_ids: list[str] = Field(min_length=1)
    severity: Literal["low", "medium", "high"]
    metric: str
    metric_value: float | str
    decision: Literal[
        "prefer_claim",
        "merge_claims",
        "downgrade_confidence",
        "clarify_user",
        "block_ledger_write",
    ]
    selected_claim_id: str | None = None
    reason: str


class ScaleEvidenceCandidate(StrictModel):
    evidence_id: str
    evidence_type: ScaleEvidenceType
    object_type: str | None = None
    detection_source: Literal[
        "vision_agent",
        "user_selected",
        "personal_container_db",
        "barcode",
        "restaurant_source",
        "label_ocr",
        "manual",
    ]
    bbox: list[float] | None = None
    known_dimension_mm: float | None = None
    dimension_basis: str | None = None
    confidence_label: ConfidenceLabel
    confidence_score: float = Field(ge=0, le=1)
    pii_risk: bool = False
    usable_for_scale: bool
    rejection_reason: str | None = None


class ScaleEvidenceResolution(StrictModel):
    resolution_id: str
    status: Literal[
        "confirmed",
        "weak",
        "missing_but_acceptable",
        "missing_needs_reference",
        "rejected_due_to_pii",
        "rejected_geometry",
    ]
    candidate_ids: list[str]
    selected_candidate_id: str | None = None
    scale_confidence: Literal["high", "medium", "low", "none"]
    expected_range_reduction_kcal: float | None = None
    prompt_user_for_reference: bool
    trace_message: str
    policy_refs: list[str]


class MealScaleEvidence(StrictModel):
    candidates: list[ScaleEvidenceCandidate]
    resolutions: list[ScaleEvidenceResolution]


class PersonalContainer(StrictModel):
    container_id: str
    user_id: str
    name: str
    volume_ml: float | None = None
    dimensions_mm: dict[str, float] = Field(default_factory=dict)
    calibration_source: Literal[
        "user_measured",
        "reference_object_back_calibrated",
        "barcode_inferred",
        "user_estimated",
    ]
    calibration_confidence: ConfidenceLabel
    sample_image_hash: str | None = None
    created_at: str
    updated_at: str


class PortionRange(StrictModel):
    component_id: str
    quantity_unit: QuantityUnit
    quantity_min: float = Field(ge=0)
    quantity_best: float = Field(ge=0)
    quantity_max: float = Field(ge=0)
    primary_basis: Literal[
        "photo_only_heuristic",
        "reference_object_calibrated",
        "personal_container",
        "barcode_serving",
        "label_ocr_serving",
        "manual_user_selection",
        "personal_prior",
        "lidar_depth",
        "multi_shot",
        "before_after_delta",
    ]
    scale_evidence_ids: list[str]
    portion_phase: PortionPhase = "as_served"
    consumption_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_label: ConfidenceLabel
    confidence_score: float = Field(ge=0, le=1)
    uncertainty_drivers: list[str]

    @model_validator(mode="after")
    def _validate_quantity_order(self) -> PortionRange:
        if not self.quantity_min <= self.quantity_best <= self.quantity_max:
            raise ValueError("portion range must satisfy min <= best <= max")
        return self


class MealSignature(StrictModel):
    signature_hash: str
    component_categories: list[str]
    normalized_components: list[str]
    cuisine_tags: list[str]
    meal_type: Literal[
        "packaged_food",
        "single_visible_item",
        "plated_meal",
        "mixed_bowl",
        "recipe_like",
        "drink",
        "unclear",
    ]
    source_family: str | None = None
    container_id: str | None = None
    restaurant_or_brand: str | None = None
    embedding_ref: str | None = None


class TraceEvent(StrictModel):
    trace_id: str = Field(..., min_length=1)
    stage: str = Field(..., min_length=1)
    event_name: str = Field(..., min_length=1)
    event_at: str = Field(
        default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds")
    )
    pii_safe: bool = True
    image_sha256: str | None = None
    meal_id: str | None = None
    component_id: str | None = None
    user_accepted_wide_range: bool | None = None
    user_decline_clarify_reason: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_decline_reason_pairing(self) -> TraceEvent:
        if not self.user_decline_clarify_reason:
            return self
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
