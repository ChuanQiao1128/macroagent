# MacroAgentCapture (iOS SwiftUI Skeleton)

This folder contains a minimal native iOS SwiftUI source skeleton for TASK-044.
It is intentionally placeholder-only for capture metadata flow and local server wiring.

## Minimum iOS Version

- iOS 17.0+
- Xcode 15+

## Required Capabilities / Permissions

For smoke testing on a real iPhone, configure these in your Xcode target:

- Camera permission: `NSCameraUsageDescription` (camera capture is not implemented yet, but required for upcoming tasks).
- Local network permission: `NSLocalNetworkUsageDescription` (for calling Mac LAN server).
- Motion permission: `NSMotionUsageDescription` (for upcoming pitch/roll metadata).
- App Transport Security exception for local HTTP development traffic as needed.

## Local Server URL

- Default in source: `http://127.0.0.1:8765`
- For real device testing on Wi-Fi: `http://<mac-lan-ip>:8765`

Backend run command on Mac:

```bash
cd /Users/qc/Documents/Claude/Projects/NutritionAI
python -m services.api.local_server --host 0.0.0.0 --port 8765
```

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

- `CaptureService.swift`: placeholder capture service seam.
- `MetadataBuilder.swift`: request envelope construction seam.
- `APIClient.swift`: local-server API client abstraction seam.
- `ResultDebugView.swift`: result/debug rendering seam.

## Current Status

- No camera or AVFoundation implementation yet.
- No third-party Swift packages required.
- Deterministic placeholder metadata is used for smoke wiring.
