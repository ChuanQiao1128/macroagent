# Privacy Trace Boundary

MacroAgent trace artifacts are for debugging and auditability, not image storage.
Every takeoff trace event must be `pii_safe` before it can be appended to a
trace store.

Meal photos are represented by `image_sha256` only. The hash lets the pipeline
join intake metadata to later takeoff stages without storing or replaying the
raw image.

Trace schemas and trace payloads must not contain raw image bytes, base64 image
data, or raw image references such as `raw_image`, `raw_image_base64`,
`raw_image_bytes`, `image_base64`, `image_bytes`, or `image_data`.

Allowed trace content includes stage names, policy decisions, component ids,
claim ids, source refs, version ids, `image_sha256`, and compact numeric or
categorical summaries needed to reproduce deterministic decisions.

If a future stage needs access to the original meal photo, it must use the
image intake path outside the trace artifact boundary. The trace may record the
resulting `image_sha256` and derived non-image metadata, but not the raw image
itself.
