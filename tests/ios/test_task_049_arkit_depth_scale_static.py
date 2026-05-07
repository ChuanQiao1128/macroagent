from __future__ import annotations

from pathlib import Path

IOS_APP_DIR = Path("apps/ios/MacroAgentCapture")
CAPTURE_SERVICE = IOS_APP_DIR / "CaptureService.swift"
CAPTURE_SCREEN = IOS_APP_DIR / "CaptureScreenView.swift"
CAPTURE_FLOW_STORE = IOS_APP_DIR / "CaptureFlowStore.swift"
MODELS = IOS_APP_DIR / "Models.swift"


def _read(path: Path) -> str:
    assert path.exists(), f"Missing required iOS file: {path.as_posix()}"
    return path.read_text(encoding="utf-8")


def test_capture_metadata_adds_arkit_scene_depth_contract_fields() -> None:
    models_text = _read(MODELS)

    expected_keys = (
        'case arkitSceneDepthSupported = "arkit_scene_depth_supported"',
        'case arkitSmoothedSceneDepthSupported = "arkit_smoothed_scene_depth_supported"',
        'case arkitDepthAvailable = "arkit_depth_available"',
        'case arkitDepthQuality = "arkit_depth_quality"',
        'case arkitDepthMapWidthPX = "arkit_depth_map_width_px"',
        'case arkitDepthMapHeightPX = "arkit_depth_map_height_px"',
        'case arkitConfidenceCoverage = "arkit_confidence_coverage"',
        'case cameraIntrinsicsAvailable = "camera_intrinsics_available"',
    )
    for key in expected_keys:
        assert key in models_text


def test_capture_service_samples_arkit_scene_depth_without_persisting_depth_maps() -> None:
    text = _read(CAPTURE_SERVICE)

    assert "import ARKit" in text
    assert "private final class ARKitDepthSnapshotSampler" in text
    assert "ARWorldTrackingConfiguration.isSupported" in text
    assert "ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth)" in text
    assert "supportsFrameSemantics(.smoothedSceneDepth)" in text
    assert "configuration.frameSemantics.insert(.smoothedSceneDepth)" in text
    assert "configuration.frameSemantics.insert(.sceneDepth)" in text
    assert "frame?.smoothedSceneDepth ?? frame?.sceneDepth" in text
    assert "cameraIntrinsicsAvailable: frame != nil" in text
    assert "ARKitConfidenceEstimator.mediumOrHighCoverage" in text
    assert "let arDepthSnapshot = await ARKitDepthSnapshotSampler.capture()" in text
    assert "encodedImageBytes: encodedBytes" in text
    assert "depthMap" not in _read(MODELS)


def test_capture_screen_exposes_arkit_debug_fields_for_real_device_testing() -> None:
    text = _read(CAPTURE_SCREEN)

    for field in (
        "arkit_scene_depth_supported",
        "arkit_smoothed_scene_depth_supported",
        "arkit_depth_available",
        "arkit_depth_quality",
        "arkit_depth_map_size",
        "arkit_confidence_coverage",
        "camera_intrinsics_available",
    ):
        assert field in text


def test_reference_hint_rebuild_preserves_arkit_depth_fields() -> None:
    text = _read(CAPTURE_FLOW_STORE)

    expected_preserved_fields = (
        "arkitSceneDepthSupported: currentMetadata.arkitSceneDepthSupported",
        "arkitSmoothedSceneDepthSupported: currentMetadata.arkitSmoothedSceneDepthSupported",
        "arkitDepthAvailable: currentMetadata.arkitDepthAvailable",
        "arkitDepthQuality: currentMetadata.arkitDepthQuality",
        "arkitDepthMapWidthPX: currentMetadata.arkitDepthMapWidthPX",
        "arkitDepthMapHeightPX: currentMetadata.arkitDepthMapHeightPX",
        "arkitConfidenceCoverage: currentMetadata.arkitConfidenceCoverage",
        "cameraIntrinsicsAvailable: currentMetadata.cameraIntrinsicsAvailable",
    )
    for field in expected_preserved_fields:
        assert field in text
