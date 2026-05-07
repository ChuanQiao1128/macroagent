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
- optional `food_volume_estimate_ml_p10/p50/p90`
- optional `food_volume_estimate_confidence`
- optional `food_volume_estimate_method`

Raw photo bytes remain in memory only for capture/upload work. Raw ARKit depth
maps, confidence maps, point clouds, and camera frames are not stored in trace
artifacts.

## v0.7 Volume-To-Grams Core

When the phone supplies a calibrated derived volume interval, the backend now
uses a deterministic density table before macro calculation:

```text
food_volume_estimate_ml_p10/p50/p90
-> component density profile
-> grams p10/p50/p90
-> deterministic macro calculation
```

This keeps LLMs out of calorie and macro arithmetic. If volume fields are absent,
the API falls back to the existing portion-hint parser.

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

This is still not full visual food segmentation. The next step after this is a
calibrated on-device food-region engine:

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
