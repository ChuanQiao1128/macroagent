# MacroAgent v0.5 iOS Native Capture Smoke Test

## Decision

The next milestone is a phone-to-Mac smoke test, not a polished consumer app.
The goal is to prove the critical capture path with real iPhone hardware:

```text
iPhone camera photo
-> iPhone capture metadata
-> Mac local HTTP API
-> backend contract validation
-> deterministic mock analysis response
-> iPhone result/debug view
```

This stage still uses deterministic mock nutrition output. Real food vision and
production deployment come after the capture path is proven.

## What "Real Phone Test" Means

The v0.5 smoke test should run on a physical iPhone and send:

- encoded photo bytes;
- SHA-256 image hash;
- image format, width, height, and byte size;
- `AVFoundation` camera position and orientation;
- `CoreMotion` pitch/roll at capture time;
- local Vision barcode result when present;
- local Vision OCR snippets when present;
- optional depth/LiDAR availability flags;
- user-selected reference object hint.

The Mac backend should return the existing v0.4 `AnalyzePhotoFacadeResponse`
shape so the app can render status, nutrition metrics, reasons, questions, and
trace ID.

## v0.5 Automated Tasks

### TASK-043 - Local Analyze Photo HTTP Server

Status: verified in `services/api/local_server.py`,
`tests/api/test_local_server.py`, and `tests/cli/test_local_server_cli.py`.

The local HTTP server is a standard-library wrapper around the existing analyze
photo facade. It exposes:

- `GET /health` -> `{"status":"ok"}`
- `POST /v1/meals/analyze-photo` -> deterministic `AnalyzePhotoFacadeResponse`

The POST endpoint accepts either the full `AnalyzePhotoFacadeRequest` envelope
or a raw `PhotoAnalyzeRequest` payload. It returns structured JSON errors for
invalid JSON, invalid schema, unsupported paths, and unsupported methods.
Multipart or image-byte handling is still deferred; the current smoke-test path
is JSON metadata only.

### TASK-044 - iOS SwiftUI Project Skeleton

Verified in `apps/ios/MacroAgentCapture` and `tests/ios/test_task_044_ios_swiftui_skeleton.py`.
The skeleton includes a SwiftUI entrypoint, root view, capture placeholder,
metadata preview placeholder, result/debug placeholder, and a lightweight local
server client seam. The README covers manual Xcode setup, iOS 17.0+, required
permissions, and the local server URL.

### TASK-045 - AVFoundation Capture and Image Hash

Status: verified in `apps/ios/MacroAgentCapture/CaptureService.swift`,
`apps/ios/MacroAgentCapture/MetadataBuilder.swift`,
`apps/ios/MacroAgentCapture/Models.swift`, and
`tests/ios/test_task_045_capture_identity_static.py`.

The capture service now:

- requests camera permission before entering `Camera` mode;
- uses `AVFoundation` to capture encoded image bytes from a real iPhone camera;
- computes SHA-256 with `CryptoKit`;
- extracts width, height, byte size, and normalized image format from the encoded bytes;
- keeps raw image bytes in memory only for upload;
- exposes `Sample Fallback` for Simulator and other no-camera environments;
- builds the v0.4 `image_identity` and `capture_metadata` payload shape.

Device runbook note: the app target must include `NSCameraUsageDescription`, and
`Camera` mode should only be used on a physical iPhone. Use `Sample Fallback`
when running on Simulator.

### TASK-046 - CoreMotion and Vision Metadata

Status: verified in `apps/ios/MacroAgentCapture/CaptureService.swift`,
`apps/ios/MacroAgentCapture/CaptureFlowStore.swift`,
`apps/ios/MacroAgentCapture/CaptureScreenView.swift`,
`apps/ios/MacroAgentCapture/Models.swift`, and
`tests/ios/test_task_046_motion_vision_metadata_static.py`.

The native smoke app now:

- samples CoreMotion pitch/roll near shutter time;
- runs local Vision barcode detection and OCR on-device;
- keeps OCR snippets short and food/package-oriented;
- filters barcode values through a local safety check before sending;
- exposes a reference object hint picker in the UI;
- populates the v0.4 metadata fields for pitch, roll, barcode payloads, OCR
  snippets, reference object hints, depth availability, depth quality, and
  LiDAR availability.

### TASK-047 - Phone-to-Mac Smoke Test

Wire the iOS app to the local Mac server, send the v0.4 payload, and show the
backend response. Add a runbook for using the iPhone on the same Wi-Fi network as
the Mac.

### TASK-048 - Runnable Xcode Project

Status: verified in `apps/ios/MacroAgentCapture.xcodeproj`,
`apps/ios/MacroAgentCapture/Info.plist`, and
`tests/ios/test_task_048_xcode_project_static.py`.

The smoke app now has a checked-in Xcode project, shared scheme, iOS 17.0 target,
automatic signing style, and real-device permission strings for camera, motion,
local network, and local HTTP development traffic. This converts the Swift source
folder into an app that can be opened in Xcode and installed on a connected iPhone.

## Expected Smoke Test Command Flow

On the Mac:

```bash
cd /Users/qc/Documents/Claude/Projects/NutritionAI
python -m services.api.local_server --host 0.0.0.0 --port 8765
```

Open the checked-in iOS project:

```bash
open /Users/qc/Documents/Claude/Projects/NutritionAI/apps/ios/MacroAgentCapture.xcodeproj
```

In Xcode:

- select the `MacroAgentCapture` scheme;
- select a connected physical iPhone;
- set your Apple development team in Signing & Capabilities if prompted;
- press Run to install the smoke app.

On the iPhone:

```text
Open MacroAgentCapture
Set server URL to http://<mac-lan-ip>:8765
Take photo
Review metadata
Tap Analyze
See ACCEPT/WARN/CLARIFY/BLOCK response
```

## Out of Scope

- App Store/TestFlight setup.
- Login or production auth.
- Real Claude/OpenAI vision calls from the API.
- Production image/object storage.
- Full nutrition database sync.
- Polished UI.

## Run Command

Use this command for the automated v0.5 queue:

```bash
cd /Users/qc/Documents/Claude/Projects/NutritionAI && CODEX_PROVIDER_MODE=chatgpt MAX_REPAIR_ATTEMPTS=3 UNATTENDED_MODE=branch AUTO_PUSH=1 caffeinate -dimsu bash scripts/run_ios_smoke_until_done.sh
```

If it stops, inspect the last `.codex/runs/` log, repair, then rerun the same
command. Completed tasks are skipped by the v0.5 state file.
