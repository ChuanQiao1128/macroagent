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

## v0.8 On-Device Volume Proxy

The iOS smoke app now attempts a conservative on-device volume proxy when ARKit
scene depth is available:

```text
ARFrame sceneDepth/smoothedSceneDepth
-> center food-region proxy
-> medium/high confidence depth samples
-> support-depth estimate from far central samples
-> raised height integration with camera intrinsics
-> food_volume_estimate_ml_p10/p50/p90
```

This is not a final food segmentation model. It assumes the user places the food
near the center of the frame and it caps confidence because the algorithm has no
semantic mask yet. The output is deliberately a wide interval.

## Reducing Measurement Error

The product should guide users toward capture conditions that reduce the largest
portion-estimation errors:

- Keep the food centered so the current center-region proxy samples the actual
  portion, not the table or plate rim.
- Prefer a slightly top-down angle; side angles make table/plate support depth
  harder to infer.
- Include the whole plate or bowl and avoid cropping food edges.
- Avoid shiny liquids, transparent containers, and heavy steam when possible;
  depth maps are weaker on reflective or textureless surfaces.
- Use a known-size reference object or personal container when LiDAR/depth is
  unavailable or low quality.
- Treat volume as an intermediate estimate. Weight still depends on density:
  the same 200 ml can be much lighter for salad than rice and much heavier for
  meat or sauce.

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
