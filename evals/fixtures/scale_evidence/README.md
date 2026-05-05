# Scale Evidence Fixture Set

This fixture family evaluates whether portion ranges shrink appropriately when
scale evidence is available, and whether unsafe or weak scale evidence is
rejected.

Minimum examples:

- reference object: fork or spoon beside a plate;
- personal container: saved rice bowl with known volume;
- barcode serving: packaged food with serving size;
- label OCR serving: nutrition label with serving grams;
- manual selection: user chooses 150 g or one bowl;
- phone motion calibration: weak candidate that may be unavailable;
- lidar depth: supported device candidate;
- multi-shot photogrammetry: before/side image pair;
- before_after_delta: plate before and after consumption;
- rejected PII: object with face, ID card, address, or unrelated document.

Each fixture should record:

- evidence id and evidence type;
- expected `usable_for_scale` decision;
- expected scale confidence;
- component ids affected by the evidence;
- expected range reduction direction;
- rejection reason when applicable;
- trace-safe artifact references only.

Raw meal images should not be stored in trace artifacts. Fixtures may reference
an image file or hash, but trace events should carry `image_sha256` and derived
metadata only.
