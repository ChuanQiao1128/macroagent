from __future__ import annotations

import subprocess
from pathlib import Path

IOS_APP_DIR = Path("apps/ios/MacroAgentCapture")
README = IOS_APP_DIR / "README.md"
RUNBOOK = Path("docs/ios_native_capture_v0_5.md")

REQUIRED_SWIFT_FILES = (
    IOS_APP_DIR / "MacroAgentCaptureApp.swift",
    IOS_APP_DIR / "RootView.swift",
    IOS_APP_DIR / "CaptureScreenView.swift",
    IOS_APP_DIR / "MetadataPreviewView.swift",
    IOS_APP_DIR / "ResultDebugView.swift",
    IOS_APP_DIR / "CaptureService.swift",
    IOS_APP_DIR / "MetadataBuilder.swift",
    IOS_APP_DIR / "APIClient.swift",
    IOS_APP_DIR / "CaptureFlowStore.swift",
    IOS_APP_DIR / "Models.swift",
)


def _read(path: Path) -> str:
    assert path.exists(), f"Missing required iOS file: {path.as_posix()}"
    return path.read_text(encoding="utf-8")


def _slice_between(text: str, start_token: str, end_token: str) -> str:
    start = text.find(start_token)
    assert start >= 0, f"Missing token: {start_token}"

    end = text.find(end_token, start + len(start_token))
    assert end >= 0, f"Missing token after {start_token}: {end_token}"
    return text[start:end]


def test_task_045_required_swift_files_exist() -> None:
    missing = [path.as_posix() for path in REQUIRED_SWIFT_FILES if not path.exists()]
    assert not missing, f"Missing TASK-045 iOS files: {missing}"


def test_swiftui_entrypoint_and_capture_flow_store_wiring_exist() -> None:
    app_text = _read(IOS_APP_DIR / "MacroAgentCaptureApp.swift")
    root_text = _read(IOS_APP_DIR / "RootView.swift")
    flow_store_text = _read(IOS_APP_DIR / "CaptureFlowStore.swift")

    assert "@main" in app_text
    assert "struct MacroAgentCaptureApp: App" in app_text
    assert "RootView()" in app_text

    assert "struct RootView: View" in root_text
    assert "CaptureScreenView(store: store)" in root_text
    assert "MetadataPreviewView(store: store)" in root_text
    assert "ResultDebugView(store: store)" in root_text

    assert "captureService: CaptureService = AVFoundationCaptureService()" in flow_store_text
    assert "selectedCaptureMode = .camera" in flow_store_text


def test_capture_service_uses_avfoundation_camera_and_permission_primitives() -> None:
    text = _read(IOS_APP_DIR / "CaptureService.swift")

    assert "import AVFoundation" in text
    assert "AVCaptureDevice.authorizationStatus(for: .video)" in text
    assert "AVCaptureDevice.requestAccess(for: .video)" in text
    assert "AVCaptureSession()" in text
    assert "AVCapturePhotoOutput()" in text
    assert "AVCapturePhotoSettings()" in text
    assert "capturePhoto(with: settings, delegate: self)" in text
    assert "photo.fileDataRepresentation()" in text


def test_capture_service_uses_cryptokit_sha256_hex_for_image_identity() -> None:
    text = _read(IOS_APP_DIR / "CaptureService.swift")

    assert "import CryptoKit" in text
    assert "SHA256.hash(data: data)" in text
    assert "String(format: \"%02x\", $0)" in text
    assert "imageSHA256: sha256Hex(of: encodedBytes)" in text


def test_image_identity_contract_names_match_v0_4_payload_shape() -> None:
    text = _read(IOS_APP_DIR / "Models.swift")

    assert 'case imageIdentity = "image_identity"' in text
    assert 'case imageSHA256 = "image_sha256"' in text
    assert 'case imageFormat = "image_format"' in text
    assert 'case widthPX = "width_px"' in text
    assert 'case heightPX = "height_px"' in text
    assert 'case byteSize = "byte_size"' in text

    assert 'case requestID = "request_id"' in text
    assert 'case userID = "user_id"' in text
    assert 'case captureMetadata = "capture_metadata"' in text


def test_metadata_builder_wires_capture_draft_identity_and_metadata() -> None:
    text = _read(IOS_APP_DIR / "MetadataBuilder.swift")

    assert "struct PlaceholderMetadataBuilder: MetadataBuilder" in text
    assert "AnalyzePhotoRequest(" in text
    assert "requestID: draft.requestID" in text
    assert "userID: draft.userID" in text
    assert "imageIdentity: draft.imageIdentity" in text
    assert "captureMetadata: draft.captureMetadata" in text


def test_simulator_and_no_camera_fallback_mode_is_present() -> None:
    capture_text = _read(IOS_APP_DIR / "CaptureService.swift")
    models_text = _read(IOS_APP_DIR / "Models.swift")
    screen_text = _read(IOS_APP_DIR / "CaptureScreenView.swift")

    assert 'case sampleFallback = "sample_fallback"' in models_text
    assert "case .sampleFallback:" in capture_text
    assert "#if targetEnvironment(simulator)" in capture_text
    assert "simulatorRequiresSampleMode" in capture_text
    assert "cameraUnavailable" in capture_text
    assert "Sample Fallback mode" in capture_text
    assert "Use Sample Fallback for Simulator or no-camera environments." in screen_text


def test_readme_and_runbook_document_real_device_and_camera_permission() -> None:
    readme_text = _read(README)
    runbook_text = _read(RUNBOOK)

    assert "Required Capabilities / Permissions" in readme_text
    assert "NSCameraUsageDescription" in readme_text

    assert "Real Device Requirement" in readme_text
    assert "mode requires a real iPhone camera." in readme_text
    assert "iOS Simulator does not provide a real camera capture path" in readme_text

    assert "What \"Real Phone Test\" Means" in runbook_text
    assert "physical iPhone" in runbook_text


def test_encoded_image_bytes_remain_out_of_json_request_payload_contract() -> None:
    models_text = _read(IOS_APP_DIR / "Models.swift")
    api_client_text = _read(IOS_APP_DIR / "APIClient.swift")

    assert "let encodedImageBytes: Data" in models_text

    analyze_request_block = _slice_between(
        models_text,
        "struct AnalyzePhotoRequest: Codable, Hashable {",
        "struct AnalyzePhotoOptions: Codable, Hashable {",
    )
    assert "encodedImageBytes" not in analyze_request_block

    assert "func analyzePhoto(_ requestEnvelope: AnalyzePhotoRequestEnvelope)" in api_client_text
    assert "encoder.encode(requestEnvelope)" in api_client_text


def test_no_photo_file_artifacts_committed_for_ios_capture_flow() -> None:
    result = subprocess.run(
        ["git", "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    )
    tracked_files = [line.strip() for line in result.stdout.splitlines() if line.strip()]

    forbidden_suffixes = {".jpg", ".jpeg", ".heic", ".heif", ".dng", ".raw", ".tif", ".tiff"}
    forbidden_paths = [
        file_path
        for file_path in tracked_files
        if Path(file_path).suffix.lower() in forbidden_suffixes
    ]

    assert not forbidden_paths, (
        "TASK-045 forbids committed real photo files. Found image artifacts: "
        f"{forbidden_paths}"
    )
