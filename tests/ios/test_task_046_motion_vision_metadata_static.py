from __future__ import annotations

from pathlib import Path

IOS_APP_DIR = Path("apps/ios/MacroAgentCapture")
CAPTURE_SERVICE = IOS_APP_DIR / "CaptureService.swift"
CAPTURE_SCREEN = IOS_APP_DIR / "CaptureScreenView.swift"
CAPTURE_FLOW_STORE = IOS_APP_DIR / "CaptureFlowStore.swift"
METADATA_BUILDER = IOS_APP_DIR / "MetadataBuilder.swift"
MODELS = IOS_APP_DIR / "Models.swift"
README = IOS_APP_DIR / "README.md"


def _read(path: Path) -> str:
    assert path.exists(), f"Missing required iOS file: {path.as_posix()}"
    return path.read_text(encoding="utf-8")


def test_coremotion_is_used_for_pitch_roll_near_shutter_time() -> None:
    text = _read(CAPTURE_SERVICE)

    assert "import CoreMotion" in text
    assert "let motionSampler = MotionSampler()" in text
    assert "motionSampler.start()" in text
    assert "Task.sleep(nanoseconds: 120_000_000)" in text
    assert "capturePhoto(with: runtime.photoOutput, motionSampler: motionSampler)" in text
    assert "let motionSnapshot = capturedPhoto.motionSnapshot ?? motionSampler.snapshot()" in text
    assert "pitchDegrees: motionSnapshot?.pitchDegrees ?? 0" in text
    assert "rollDegrees: motionSnapshot?.rollDegrees ?? 0" in text


def test_coremotion_sampling_primitives_and_angle_sanitization_exist() -> None:
    text = _read(CAPTURE_SERVICE)

    assert "private final class MotionSampler" in text
    assert "private let motionManager = CMMotionManager()" in text
    assert "motionManager.isDeviceMotionAvailable" in text
    assert "motionManager.deviceMotionUpdateInterval = 1.0 / 30.0" in text
    assert "motionManager.startDeviceMotionUpdates(using: .xArbitraryCorrectedZVertical)" in text
    assert "motionManager.stopDeviceMotionUpdates()" in text
    assert "motion.attitude.pitch * 180.0 / Double.pi" in text
    assert "motion.attitude.roll * 180.0 / Double.pi" in text
    assert "return max(-180, min(180, value))" in text


def test_vision_local_barcode_and_ocr_requests_are_wired() -> None:
    text = _read(CAPTURE_SERVICE)

    assert "import Vision" in text
    assert "let barcodeRequest = VNDetectBarcodesRequest()" in text
    assert "let textRequest = VNRecognizeTextRequest()" in text
    assert "textRequest.recognitionLevel = .accurate" in text
    assert "textRequest.recognitionLanguages = [\"en-US\"]" in text
    assert (
        "let handler = VNImageRequestHandler(cgImage: cgImage, orientation: .up, options: [:])"
        in text
    )
    assert "try handler.perform([barcodeRequest, textRequest])" in text


def test_barcode_and_ocr_outputs_are_filtered_for_safety() -> None:
    text = _read(CAPTURE_SERVICE)

    assert "private static func firstSafeBarcodePayload" in text
    assert "private static func isSafeBarcodePayload" in text
    assert "private static func looksSensitive(_ text: String) -> Bool" in text
    assert "trimmed.count <= 64" in text
    assert "if digitsOnly.count > 20" in text
    assert "if lowercased.contains(\"@\")" in text
    assert "if digitsOnly.count >= 10" in text
    assert "if compact.count >= 16" in text
    assert (
        "return VisionCaptureMetadata(barcodePayload: nil, barcodePayloadSafe: false, "
        "ocrTextSnippets: [])"
        in text
    )


def test_ocr_snippets_are_short_and_food_package_oriented() -> None:
    text = _read(CAPTURE_SERVICE)

    assert "private static let maxOCRSnippetCount = 6" in text
    assert "private static let maxSnippetLength = 48" in text
    assert "private static let foodPackageKeywords: [String]" in text
    assert "\"nutrition\", \"ingredient\", \"ingredients\", \"serving\"" in text
    assert "private static func shortFoodPackageSnippets" in text
    assert "if snippets.count >= maxOCRSnippetCount" in text
    assert "String(collapsed.prefix(maxSnippetLength))" in text
    assert "private static func isFoodOrPackageOriented(_ text: String) -> Bool" in text
    assert "\\\\b\\\\d{1,4}\\\\s?(kcal|cal|kj|g|mg|ml|oz|lb|l)\\\\b" in text


def test_capture_metadata_backend_field_names_and_population_paths_exist() -> None:
    models_text = _read(MODELS)
    capture_text = _read(CAPTURE_SERVICE)
    metadata_builder_text = _read(METADATA_BUILDER)

    expected_keys = (
        'case pitchDegrees = "pitch_degrees"',
        'case rollDegrees = "roll_degrees"',
        'case barcodePayload = "barcode_payload"',
        'case barcodePayloadSafe = "barcode_payload_safe"',
        'case ocrTextSnippets = "ocr_text_snippets"',
        'case referenceObjectHint = "reference_object_hint"',
        'case depthAvailable = "depth_available"',
        'case depthQuality = "depth_quality"',
        'case lidarAvailable = "lidar_available"',
    )
    for key in expected_keys:
        assert key in models_text

    assert "captureMetadata: draft.captureMetadata" in metadata_builder_text
    assert "depthAvailable: depthAvailable" in capture_text
    assert "depthQuality: depthQuality" in capture_text
    assert "lidarAvailable: runtime.lidarAvailable" in capture_text
    assert "barcodePayload: visionMetadata.barcodePayload" in capture_text
    assert "barcodePayloadSafe: visionMetadata.barcodePayloadSafe" in capture_text
    assert "ocrTextSnippets: visionMetadata.ocrTextSnippets" in capture_text
    assert "referenceObjectHint: referenceObjectHint" in capture_text


def test_ui_exposes_server_url_and_reference_object_hint_controls() -> None:
    text = _read(CAPTURE_SCREEN)

    assert 'Section("Server")' in text
    assert 'TextField("http://127.0.0.1:8765", text: $store.serverURLText)' in text
    assert "Use localhost on Simulator, or your Mac LAN IP on a real iPhone." in text

    assert 'Section("Reference Object")' in text
    assert 'Picker("Hint", selection: $store.selectedReferenceObjectHint)' in text
    assert "ForEach(ReferenceObjectHint.allCases)" in text
    assert "capture_metadata.reference_object_hint" in text


def test_capture_flow_store_propagates_reference_object_hint_to_metadata_preview() -> None:
    text = _read(CAPTURE_FLOW_STORE)

    assert "@Published var selectedReferenceObjectHint: ReferenceObjectHint" in text
    assert "didSet {" in text
    assert "applyReferenceHintSelection()" in text
    assert "self.selectedReferenceObjectHint = .none" in text

    assert (
        "captureService.initialDraft(referenceObjectHint: "
        "selectedReferenceObjectHint.metadataValue)"
        in text
    )
    assert "referenceObjectHint: selectedReferenceObjectHint.metadataValue" in text

    assert "let selectedHint = selectedReferenceObjectHint.metadataValue" in text
    assert "referenceObjectHint: selectedHint," in text
    assert "metadataPreview = metadataBuilder.buildRequestEnvelope(from: captureDraft)" in text


def test_reference_object_hint_contract_values_match_expected_backend_hints() -> None:
    text = _read(MODELS)

    assert "enum ReferenceObjectHint: String, Codable, CaseIterable, Identifiable" in text
    assert "case none" in text
    assert 'case standardFork = "standard_fork"' in text
    assert "case tablespoon" in text
    assert 'case sodaCan = "soda_can_330ml"' in text
    assert "var metadataValue: String?" in text
    assert "self == .none ? nil : rawValue" in text


def test_readme_documents_local_vision_and_privacy_for_barcode_and_ocr() -> None:
    text = _read(README)

    assert "## Privacy / Storage Boundary" in text
    assert "Barcode detection and OCR are executed locally on-device with Apple Vision." in text
    assert "`barcode_payload` is sent only when it passes a local safety filter." in text
    assert (
        "`ocr_text_snippets` are trimmed to short food/package-oriented snippets and filtered"
        in text
    )
