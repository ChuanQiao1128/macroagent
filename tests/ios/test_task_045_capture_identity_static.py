from __future__ import annotations

from pathlib import Path

IOS_APP_DIR = Path("apps/ios/MacroAgentCapture")
CAPTURE_SERVICE = IOS_APP_DIR / "CaptureService.swift"
MODELS = IOS_APP_DIR / "Models.swift"


def _read(path: Path) -> str:
    assert path.exists(), f"Missing required iOS file: {path.as_posix()}"
    return path.read_text(encoding="utf-8")


def test_image_identity_extractor_reads_dimensions_and_byte_size_from_image_bytes() -> None:
    text = _read(CAPTURE_SERVICE)

    assert "import ImageIO" in text
    assert "CGImageSourceCreateWithData(data as CFData, nil)" in text
    assert "CGImageSourceCopyPropertiesAtIndex(imageSource, 0, nil)" in text
    assert "kCGImagePropertyPixelWidth" in text
    assert "kCGImagePropertyPixelHeight" in text
    assert "widthPX: dimensions.width" in text
    assert "heightPX: dimensions.height" in text
    assert "byteSize: encodedBytes.count" in text


def test_image_identity_format_normalization_covers_file_type_and_magic_number_paths() -> None:
    text = _read(CAPTURE_SERVICE)

    assert (
        "normalizedFormat(fileTypeRawValue: suggestedFileTypeRawValue, imageBytes: encodedBytes)"
        in text
    )

    assert 'if raw.contains("heic") { return "heic" }' in text
    assert 'if raw.contains("heif") { return "heif" }' in text
    assert 'if raw.contains("jpeg") || raw.contains("jpg") { return "jpeg" }' in text
    assert 'if raw.contains("png") { return "png" }' in text
    assert 'if raw.contains("webp") { return "webp" }' in text

    assert "private static func sniffFromMagicNumber(_ data: Data) -> String" in text
    assert "bytes[0] == 0xFF && bytes[1] == 0xD8" in text
    assert "bytes[0] == 0x89" in text
    assert 'String(bytes: bytes[8...11], encoding: .ascii) == "WEBP"' in text
    assert 'if header.contains("ftypheic") { return "heic" }' in text
    assert 'if header.contains("ftypheif") { return "heif" }' in text


def test_capture_path_keeps_raw_image_bytes_in_memory_only_without_file_writes() -> None:
    text = _read(CAPTURE_SERVICE)

    assert "let encodedBytes = try extractEncodedBytes" in text
    assert "encodedImageBytes: encodedBytes" in text

    forbidden_persistence_tokens = (
        "write(to:",
        "createFile(atPath:",
        "FileManager.default",
        "temporaryDirectory",
    )
    for token in forbidden_persistence_tokens:
        assert token not in text, (
            "Raw image bytes should stay in memory only; "
            f"found disk token: {token}"
        )


def test_sample_fallback_mode_uses_embedded_in_memory_image_bytes() -> None:
    text = _read(CAPTURE_SERVICE)

    assert "private enum SampleCaptureFactory" in text
    assert 'let png1x1Base64 = "' in text
    assert "Data(base64Encoded: png1x1Base64)" in text
    assert "return Data([0x89, 0x50, 0x4E, 0x47])" in text
    assert "captureSourceMode: .sampleFallback" in text


def test_capture_metadata_contract_names_match_v0_4_payload_shape() -> None:
    text = _read(MODELS)

    expected_keys = (
        'case deviceModel = "device_model"',
        'case osVersion = "os_version"',
        'case cameraPosition = "camera_position"',
        "case orientation",
        'case pitchDegrees = "pitch_degrees"',
        'case rollDegrees = "roll_degrees"',
        'case focalLengthMM = "focal_length_mm"',
        'case lensHint = "lens_hint"',
        'case depthAvailable = "depth_available"',
        'case depthQuality = "depth_quality"',
        'case lidarAvailable = "lidar_available"',
        'case barcodePayload = "barcode_payload"',
        'case barcodePayloadSafe = "barcode_payload_safe"',
        'case ocrTextSnippets = "ocr_text_snippets"',
        'case referenceObjectHint = "reference_object_hint"',
        'case captureTimestamp = "capture_timestamp"',
    )
    for key in expected_keys:
        assert key in text


def test_ios_reference_picker_includes_explicit_known_container_hints() -> None:
    text = _read(MODELS)
    screen_text = _read(IOS_APP_DIR / "CaptureScreenView.swift")

    for expected in (
        'case containerCoffeeMug = "container_coffee_mug_240ml"',
        'case containerRiceBowl = "container_rice_bowl_300ml"',
        'case containerMealPrep = "container_meal_prep_750ml"',
        'case containerMeasuringCup = "container_measuring_cup_240ml"',
        'return "Container: Coffee Mug 240ml"',
        'return "Container: Rice Bowl 300ml"',
    ):
        assert expected in text

    assert "known-container hint" in screen_text
