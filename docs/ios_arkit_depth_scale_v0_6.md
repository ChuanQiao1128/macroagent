# MacroAgent v0.6 ARKit Depth Scale Capture

## Decision

The iPhone capture path should use ARKit scene-depth metadata as scale evidence
before attempting consumer-facing volume estimates. v0.6 therefore captures
derived ARKit depth facts and sends them through the existing metadata contract,
but it does not persist raw depth maps and does not claim calibrated food volume.

## Implemented Slice

The current native capture flow is:

```text
AVFoundation photo
-> CoreMotion pitch/roll
-> local Vision OCR/barcode
-> ARKit scene-depth snapshot
-> capture_metadata
-> backend scale evidence adapter
-> deterministic nutrition facade
```

The ARKit snapshot records only derived metadata:

- `arkit_scene_depth_supported`
- `arkit_smoothed_scene_depth_supported`
- `arkit_depth_available`
- `arkit_depth_quality`
- `arkit_depth_map_width_px`
- `arkit_depth_map_height_px`
- `arkit_confidence_coverage`
- `camera_intrinsics_available`

Raw photo bytes remain in memory only for capture/upload work. Raw ARKit depth
maps, confidence maps, point clouds, and camera frames are not stored in trace
artifacts.

## Backend Policy

`arkit_scene_depth` is now a first-class scale evidence type. It outranks regular
AVFoundation `lidar_depth` because it includes scene-depth availability,
confidence coverage, and camera-intrinsics checks for the same capture window.

ARKit scene depth is usable only when:

- ARKit scene depth is supported or a depth frame was observed;
- `arkit_depth_quality` is `medium` or `high`;
- camera intrinsics were available.

If those checks fail, the candidate is retained for audit but rejected for scale.

## Still Not Done

This is not yet full food volume estimation. The next step after this is a
calibrated volume engine:

```text
ARKit depth map
-> table/plane estimate
-> food region estimate
-> area and height statistics
-> volume_ml interval
-> density table
-> grams interval
-> deterministic nutrition calculation
```

That engine needs segmentation and calibration tests before the app should show
"measured volume" to users.
