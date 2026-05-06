# iOS Capture Field Guide (Backend Contract)

This guide maps iPhone capture APIs to backend `PhotoAnalyzeRequest.capture_metadata` fields.
It is intended for SwiftUI/AVFoundation/CoreMotion capture clients.

## Request Envelope

- `request_id`: Client-generated stable id for one capture analysis request.
- `user_id`: App user identifier (no email/phone values).
- `image_identity.image_sha256`: SHA-256 hash of encoded image bytes.
- `image_identity.image_format`: Encoded payload format (`heic`, `jpg`, `jpeg`, `png`, `webp`).
- `image_identity.width_px`/`height_px`: Encoded image dimensions.
- `image_identity.byte_size`: Encoded image byte length.

## Response Contract

The backend facade response is the canonical source of truth. The committed
example field `photo_analyze_response` is a Swift-facing projection generated
from `analyze_photo_facade_response`:

- `status` maps to `decision`.
- `nutrition` maps to `metrics`.
- `request_id` and `reasons` are copied exactly.
- `BLOCK` responses carry no nutrition/metrics.

## Capture Metadata Mapping

- `device_model`
  - Source: `UIDevice.current.model` plus hardware identifier from sysctl (for example `iPhone15,3`).
- `os_version`
  - Source: `UIDevice.current.systemName` + `UIDevice.current.systemVersion`.
- `camera_position`
  - Source: `AVCaptureDevice.Position` from active camera.
  - Map: `.back -> "back"`, `.front -> "front"`, unknown/unset -> `"unknown"`.
- `orientation`
  - Source: `UIDeviceOrientation` or `AVCaptureVideoOrientation` at shutter time.
  - Map to backend enum: `portrait`, `portrait_upside_down`, `landscape_left`, `landscape_right`, `face_up`, `face_down`, `unknown`.
- `pitch_degrees` / `roll_degrees`
  - Source: `CMMotionManager.deviceMotion?.attitude` (radians).
  - Convert radians to degrees before sending.
- `focal_length_mm`
  - Source: `AVCaptureDevice.activeFormat` camera calibration metadata when available.
  - Send null if unavailable.
- `lens_hint`
  - Source: Active lens selection (for example ultra-wide/wide/telephoto) from `AVCaptureDevice` and virtual device switch-over state.
- `depth_available`
  - Source: `AVCapturePhotoOutput.isDepthDataDeliverySupported` and session config.
- `depth_quality`
  - Source: app policy derived from depth delivery status and confidence.
  - Suggested mapping: unsupported/off=`none`, noisy=`low`, usable=`medium`, strong=`high`, indeterminate=`unknown`.
- `lidar_available`
  - Source: `ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth)` or `.smoothedSceneDepth`.
- `barcode_payload`
  - Source: local Vision barcode detection (`VNDetectBarcodesRequest`) string value.
  - Do not send raw image bytes.
- `barcode_payload_safe`
  - Source: client safety gate for barcode persistence (true only when value deemed safe to store).
- `ocr_text_snippets`
  - Source: local Vision OCR (`VNRecognizeTextRequest`) short snippets.
  - Keep to non-PII food/package context only.
- `reference_object_hint`
  - Source: user-selected known-size helper (coin/card/fork/plate) in UI.
- `capture_timestamp`
  - Source: capture time in RFC3339/ISO-8601 with timezone offset.

## Privacy and Safety Constraints

- Never include raw image bytes, base64 blobs, or local file paths in request fields.
- Do not send PII in OCR snippets (emails, phone numbers, long identifiers).
- Use synthetic identifiers in examples and test payloads only.
