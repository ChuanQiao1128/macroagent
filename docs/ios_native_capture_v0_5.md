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

Create a no-framework or standard-library local HTTP server wrapper around the
existing analyze photo facade. It must accept JSON metadata first, with optional
multipart/image handling deferred if needed.

### TASK-044 - iOS SwiftUI Project Skeleton

Add a minimal SwiftUI app under `apps/ios/MacroAgentCapture`. It should have a
capture screen, metadata preview, and result/debug screen. The project should be
plain source files and a clear README/runbook even if Xcode project generation is
manual in this repo.

### TASK-045 - AVFoundation Capture and Image Hash

Implement the iOS capture service: take a photo, extract encoded dimensions and
byte size, compute SHA-256, and create the request envelope expected by v0.4.

### TASK-046 - CoreMotion and Vision Metadata

Add capture-time pitch/roll and local Vision barcode/OCR metadata. Keep OCR short
and non-PII. Add a reference object hint UI control.

### TASK-047 - Phone-to-Mac Smoke Test

Wire the iOS app to the local Mac server, send the v0.4 payload, and show the
backend response. Add a runbook for using the iPhone on the same Wi-Fi network as
the Mac.

## Expected Smoke Test Command Flow

On the Mac:

```bash
cd /Users/qc/Documents/Claude/Projects/NutritionAI
python -m services.api.local_server --host 0.0.0.0 --port 8765
```

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
