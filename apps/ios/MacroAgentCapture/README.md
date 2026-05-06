# MacroAgentCapture (iOS Camera Smoke App)

This folder contains the native iOS SwiftUI smoke app source for capture metadata flow.
TASK-045 adds a real AVFoundation photo capture path and SHA-256 image identity generation.

## Minimum iOS Version

- iOS 17.0+
- Xcode 15+

## Required Capabilities / Permissions

For smoke testing on a real iPhone, configure these in your Xcode target:

- Camera permission: `NSCameraUsageDescription`
- Local network permission: `NSLocalNetworkUsageDescription` (for calling Mac LAN server)
- Motion permission: `NSMotionUsageDescription` (used for pitch/roll near shutter time)
- App Transport Security exception for local HTTP development traffic as needed

## Real Device Requirement

- `Camera` mode requires a real iPhone camera.
- The iOS Simulator does not provide a real camera capture path for this smoke test.
- On Simulator (or no-camera environments), switch capture mode to `Sample Fallback`.

## Capture Modes

- `Camera`: Uses `AVFoundation` to request camera access and capture encoded image bytes.
- `Sample Fallback`: Uses a synthetic in-memory sample image for simulator/no-camera development.

Both modes produce:

- `image_identity.image_sha256` via `CryptoKit` SHA-256 on encoded bytes
- `image_identity.image_format`
- `image_identity.width_px`
- `image_identity.height_px`
- `image_identity.byte_size`
- v0.4 `capture_metadata` fields including motion, depth, OCR, barcode, and reference hint values

## Mock-First Backend Behavior (Explicit)

- `POST /v1/meals/analyze-photo` is currently backed by deterministic mock-first analysis in the local Mac server.
- The smoke test goal is transport and contract validation (photo metadata -> backend -> response rendering), not production vision inference.
- Expect deterministic `ACCEPT`/`WARN`/`CLARIFY`/`BLOCK` fixture-style behavior keyed by request data.

## Privacy / Storage Boundary

- Raw image bytes are kept in memory only (`CaptureDraft.encodedImageBytes`).
- Raw photo files are not written to the repository.
- Raw image bytes are not serialized into metadata payload fields.
- Barcode detection and OCR are executed locally on-device with Apple Vision.
- `barcode_payload` is sent only when it passes a local safety filter.
- `ocr_text_snippets` are trimmed to short food/package-oriented snippets and filtered to avoid likely email/phone/long-identifier values.

## Local Server URL

- Default in source: `http://127.0.0.1:8765`
- For real device testing on Wi-Fi: `http://<mac-lan-ip>:8765`

Backend run command on Mac:

```bash
cd /Users/qc/Documents/Claude/Projects/NutritionAI
python -m services.api.local_server --host 0.0.0.0 --port 8765
```

## Manual Phone-to-Mac Smoke Test Runbook

1. Find your Mac LAN IP (same Wi-Fi network as iPhone).

```bash
ipconfig getifaddr en0
```

If `en0` is not your active interface, list interfaces and pick the active LAN/Wi-Fi IP:

```bash
ifconfig | rg "inet "
```

2. Start the local server on your Mac.

```bash
cd /Users/qc/Documents/Claude/Projects/NutritionAI
python -m services.api.local_server --host 0.0.0.0 --port 8765
```

3. Configure server URL on iPhone.
- Open `MacroAgentCapture`.
- In `Capture` tab, set server URL to `http://<mac-lan-ip>:8765`.

4. Take a photo.
- Keep `Capture Mode` as `Camera` on a real iPhone.
- Tap `Capture Now`.

5. Send request.
- Open `Metadata` tab and confirm the request preview for `/v1/meals/analyze-photo`.
- Return to `Capture` or `Result` tab and tap `Analyze`.

6. Verify response.
- Confirm `status`, `trace_id`, and `reasons`.
- Confirm seven nutrition metrics render when status is not `BLOCK`:
  `kcal`, `protein_g`, `carbs_g`, `fat_g`, `sugar_g`, `sodium_mg`, `fiber_g`.
- Confirm `clarify_questions` are shown when status is `CLARIFY`.

## Troubleshooting

- Same Wi-Fi/LAN: confirm iPhone and Mac are on the same SSID and subnet.
- URL format: use `http://<mac-lan-ip>:8765` (not `127.0.0.1`) on physical iPhone.
- Server bind: ensure server is started with `--host 0.0.0.0`.
- macOS firewall: System Settings -> Network -> Firewall; allow incoming connections for Terminal/Python (or temporarily disable firewall for local test), then retry.
- Health check: use `Run Health Check` in app before `Analyze`; if health fails, fix network path first.

## Create / Open Xcode Project Manually

If this repo does not generate an Xcode project automatically:

1. Open Xcode and create a new **iOS App** project.
2. Product Name: `MacroAgentCapture`.
3. Interface: **SwiftUI**. Language: **Swift**.
4. Set the deployment target to **iOS 17.0** (or newer).
5. Add all `*.swift` files from this folder to the app target.
6. Remove or ignore the default generated `ContentView.swift`/`<App>.swift` files if duplicates exist.
7. Confirm target includes the permission keys listed above.

## Included Seams

- `CaptureService.swift`: AVFoundation capture service + sample fallback mode.
- `MetadataBuilder.swift`: request envelope construction seam.
- `APIClient.swift`: local-server API client abstraction seam.
- `ResultDebugView.swift`: result/debug rendering seam.

## Current Status

- Real camera capture path implemented for smoke testing on iPhone.
- Simulator-safe sample fallback mode implemented.
- No third-party Swift packages required.
