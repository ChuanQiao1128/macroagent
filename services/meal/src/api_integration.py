from __future__ import annotations

from services.storage.ledger import LedgerVersionMatrix


def build_default_ledger_version_matrix() -> LedgerVersionMatrix:
    """Build deterministic default version metadata for API facade ledger writes."""
    return LedgerVersionMatrix(
        calculator_version="macro_interval_v1",
        uncertainty_policy_version="uncertainty_policy_v0.3",
        energy_density_policy_version="energy_density_policy_v0.3",
        scale_evidence_policy_version="scale_evidence_policy_v0.3",
        contract_yaml_version="capture_photo_contract_v0.1",
        source_dataset_versions={"usda_seed": "core7_v3", "personal_seed": "core7_v1"},
        takeoff_pipeline_version="analyze_photo_facade_v0.1",
        semantic_judge_version="disabled_mock",
    )


__all__ = ["build_default_ledger_version_matrix"]
