from __future__ import annotations

import plistlib
from pathlib import Path

IOS_ROOT = Path("apps/ios")
PROJECT = IOS_ROOT / "MacroAgentCapture.xcodeproj"
PBXPROJ = PROJECT / "project.pbxproj"
SCHEME = PROJECT / "xcshareddata" / "xcschemes" / "MacroAgentCapture.xcscheme"
APP_DIR = IOS_ROOT / "MacroAgentCapture"
INFO_PLIST = APP_DIR / "Info.plist"
README = APP_DIR / "README.md"
RUNBOOK = Path("docs/ios_native_capture_v0_5.md")

REQUIRED_SOURCE_NAMES = (
    "APIClient.swift",
    "CaptureFlowStore.swift",
    "CaptureScreenView.swift",
    "CaptureService.swift",
    "MacroAgentCaptureApp.swift",
    "MetadataBuilder.swift",
    "MetadataPreviewView.swift",
    "Models.swift",
    "ResultDebugView.swift",
    "RootView.swift",
)


def _read(path: Path) -> str:
    assert path.exists(), f"Missing required file: {path.as_posix()}"
    return path.read_text(encoding="utf-8")


def test_xcode_project_scheme_and_runnable_app_target_exist() -> None:
    pbxproj_text = _read(PBXPROJ)
    scheme_text = _read(SCHEME)

    assert "MacroAgentCapture.app" in pbxproj_text
    assert "com.apple.product-type.application" in pbxproj_text
    assert "PBXNativeTarget" in pbxproj_text
    assert "MacroAgentCapture.app" in scheme_text
    assert 'BlueprintName = "MacroAgentCapture"' in scheme_text


def test_xcode_project_references_all_smoke_app_sources_once() -> None:
    pbxproj_text = _read(PBXPROJ)

    for source_name in REQUIRED_SOURCE_NAMES:
        assert f"{source_name} in Sources" in pbxproj_text
        assert f"path = {source_name};" in pbxproj_text


def test_xcode_target_uses_ios_17_swiftui_app_settings() -> None:
    pbxproj_text = _read(PBXPROJ)

    assert "IPHONEOS_DEPLOYMENT_TARGET = 17.0;" in pbxproj_text
    assert "SWIFT_VERSION = 5.9;" in pbxproj_text
    assert "SUPPORTED_PLATFORMS = \"iphoneos iphonesimulator\";" in pbxproj_text
    assert "TARGETED_DEVICE_FAMILY = 1;" in pbxproj_text
    assert "PRODUCT_BUNDLE_IDENTIFIER = com.chuanqiao.macroagent.capture;" in pbxproj_text
    assert "INFOPLIST_FILE = MacroAgentCapture/Info.plist;" in pbxproj_text
    assert "CODE_SIGN_STYLE = Automatic;" in pbxproj_text


def test_info_plist_has_real_device_permissions_and_local_http_exception() -> None:
    with INFO_PLIST.open("rb") as handle:
        plist = plistlib.load(handle)

    assert "NSCameraUsageDescription" in plist
    assert "NSMotionUsageDescription" in plist
    assert "NSLocalNetworkUsageDescription" in plist

    transport_security = plist["NSAppTransportSecurity"]
    assert transport_security["NSAllowsLocalNetworking"] is True
    assert transport_security["NSAllowsArbitraryLoads"] is True


def test_runbook_now_points_to_checked_in_xcode_project() -> None:
    readme_text = _read(README)
    runbook_text = _read(RUNBOOK)

    expected_open_command = (
        "open /Users/qc/Documents/Claude/Projects/NutritionAI/"
        "apps/ios/MacroAgentCapture.xcodeproj"
    )

    assert expected_open_command in readme_text
    assert expected_open_command in runbook_text
    assert "select the `MacroAgentCapture` scheme" in runbook_text
    assert "connected physical iPhone" in runbook_text
    assert "Signing & Capabilities" in readme_text
