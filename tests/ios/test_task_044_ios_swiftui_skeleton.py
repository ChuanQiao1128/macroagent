from __future__ import annotations

from pathlib import Path

IOS_APP_DIR = Path("apps/ios/MacroAgentCapture")
README = IOS_APP_DIR / "README.md"

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


def test_task_044_required_swift_files_exist() -> None:
    missing = [path.as_posix() for path in REQUIRED_SWIFT_FILES if not path.exists()]
    assert not missing, f"Missing TASK-044 iOS files: {missing}"


def test_swiftui_entrypoint_and_placeholder_views_are_wired() -> None:
    app_text = _read(IOS_APP_DIR / "MacroAgentCaptureApp.swift")
    root_text = _read(IOS_APP_DIR / "RootView.swift")

    assert "@main" in app_text
    assert "struct MacroAgentCaptureApp: App" in app_text
    assert "RootView()" in app_text

    assert "struct RootView: View" in root_text
    assert "CaptureScreenView(store: store)" in root_text
    assert "MetadataPreviewView(store: store)" in root_text
    assert "ResultDebugView(store: store)" in root_text


def test_readme_documents_ios_version_capabilities_and_local_server_url() -> None:
    text = _read(README)

    assert "Minimum iOS Version" in text
    assert "iOS 17.0+" in text

    assert "Required Capabilities / Permissions" in text
    assert "NSCameraUsageDescription" in text
    assert "NSLocalNetworkUsageDescription" in text
    assert "NSMotionUsageDescription" in text

    assert "Local Server URL" in text
    assert "http://127.0.0.1:8765" in text
    assert "http://<mac-lan-ip>:8765" in text


def test_readme_includes_manual_xcode_project_setup_workflow() -> None:
    text = _read(README)

    assert "Create / Open Xcode Project Manually" in text
    assert "Open Xcode and create a new **iOS App** project." in text
    assert "Product Name: `MacroAgentCapture`." in text
    assert "Set the deployment target to **iOS 17.0**" in text
    assert "Add all `*.swift` files from this folder to the app target." in text


def test_source_contains_clear_capture_metadata_api_and_result_seams() -> None:
    capture_service_text = _read(IOS_APP_DIR / "CaptureService.swift")
    metadata_builder_text = _read(IOS_APP_DIR / "MetadataBuilder.swift")
    api_client_text = _read(IOS_APP_DIR / "APIClient.swift")
    result_view_text = _read(IOS_APP_DIR / "ResultDebugView.swift")
    flow_store_text = _read(IOS_APP_DIR / "CaptureFlowStore.swift")

    assert "protocol CaptureService" in capture_service_text
    assert "struct PlaceholderCaptureService: CaptureService" in capture_service_text

    assert "protocol MetadataBuilder" in metadata_builder_text
    assert "struct PlaceholderMetadataBuilder: MetadataBuilder" in metadata_builder_text

    assert "protocol MacroAgentAPIClient" in api_client_text
    assert "struct LocalServerAPIClient: MacroAgentAPIClient" in api_client_text
    assert "defaultBaseURLString = \"http://127.0.0.1:8765\"" in api_client_text

    assert "struct ResultDebugView: View" in result_view_text
    assert "latestResponse" in result_view_text

    assert "private let captureService: CaptureService" in flow_store_text
    assert "private let metadataBuilder: MetadataBuilder" in flow_store_text
    assert "private let apiClientFactory" in flow_store_text


def test_placeholder_capture_and_metadata_are_deterministic() -> None:
    capture_service_text = _read(IOS_APP_DIR / "CaptureService.swift")
    metadata_builder_text = _read(IOS_APP_DIR / "MetadataBuilder.swift")

    assert 'requestID: "ios-smoke-request-0001"' in capture_service_text
    assert 'userID: "ios-smoke-user-0001"' in capture_service_text
    assert 'captureTimestamp: "2026-01-01T00:00:00Z"' in capture_service_text
    assert "AnalyzePhotoOptions(" in metadata_builder_text
    assert "logAnyway: false" in metadata_builder_text


def test_swift_sources_do_not_introduce_third_party_imports() -> None:
    allowed_imports = {"Foundation", "SwiftUI"}

    for path in REQUIRED_SWIFT_FILES:
        text = _read(path)
        imports = [
            line.strip().split(maxsplit=1)[1]
            for line in text.splitlines()
            if line.strip().startswith("import ")
        ]

        disallowed = [item for item in imports if item not in allowed_imports]
        assert not disallowed, (
            f"{path.as_posix()} imports non-standard modules: {disallowed}. "
            "TASK-044 must avoid third-party package dependencies."
        )


def test_source_does_not_implement_camera_capture_yet() -> None:
    camera_api_tokens = (
        "AVCaptureSession",
        "AVCaptureDevice",
        "AVCapturePhotoOutput",
        "UIImagePickerController",
        "PhotosPicker",
        "PHPickerViewController",
    )

    for path in REQUIRED_SWIFT_FILES:
        text = _read(path)
        matches = [token for token in camera_api_tokens if token in text]
        assert not matches, (
            f"{path.as_posix()} appears to implement camera capture primitives: {matches}. "
            "TASK-044 forbids camera capture implementation at this stage."
        )
