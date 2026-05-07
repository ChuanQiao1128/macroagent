import SwiftUI

struct CaptureScreenView: View {
    @ObservedObject var store: CaptureFlowStore

    var body: some View {
        Form {
            Section("Server") {
                TextField("http://127.0.0.1:8765", text: $store.serverURLText)

                Text("Use localhost on Simulator, or your Mac LAN IP on a real iPhone.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            Section("Capture Mode") {
                Picker("Mode", selection: $store.selectedCaptureMode) {
                    ForEach(CaptureSourceMode.allCases) { mode in
                        Text(mode.displayName).tag(mode)
                    }
                }
                .pickerStyle(.segmented)

                Text("Use Camera mode on a real iPhone. Use Sample Fallback for Simulator or no-camera environments.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            Section("Reference Object") {
                Picker("Hint", selection: $store.selectedReferenceObjectHint) {
                    ForEach(ReferenceObjectHint.allCases) { hint in
                        Text(hint.displayName).tag(hint)
                    }
                }

                Text("Optional scale or known-container hint passed as capture_metadata.reference_object_hint.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            Section("Capture Draft") {
                KeyValueRow(label: "request_id", value: store.captureDraft.requestID)
                KeyValueRow(label: "user_id", value: store.captureDraft.userID)
                KeyValueRow(label: "capture_source", value: store.captureDraft.captureSourceMode.rawValue)
                KeyValueRow(label: "image_sha256", value: store.captureDraft.imageIdentity.imageSHA256)
                KeyValueRow(label: "image_format", value: store.captureDraft.imageIdentity.imageFormat)
                KeyValueRow(label: "image_size", value: "\(store.captureDraft.imageIdentity.widthPX)x\(store.captureDraft.imageIdentity.heightPX)")
                KeyValueRow(label: "bytes", value: "\(store.captureDraft.imageIdentity.byteSize)")
                KeyValueRow(label: "pitch_degrees", value: formatted(store.captureDraft.captureMetadata.pitchDegrees))
                KeyValueRow(label: "roll_degrees", value: formatted(store.captureDraft.captureMetadata.rollDegrees))
                KeyValueRow(label: "depth_available", value: "\(store.captureDraft.captureMetadata.depthAvailable)")
                KeyValueRow(label: "depth_quality", value: store.captureDraft.captureMetadata.depthQuality.rawValue)
                KeyValueRow(label: "lidar_available", value: "\(store.captureDraft.captureMetadata.lidarAvailable)")
                KeyValueRow(
                    label: "arkit_scene_depth_supported",
                    value: "\(store.captureDraft.captureMetadata.arkitSceneDepthSupported)"
                )
                KeyValueRow(
                    label: "arkit_smoothed_scene_depth_supported",
                    value: "\(store.captureDraft.captureMetadata.arkitSmoothedSceneDepthSupported)"
                )
                KeyValueRow(
                    label: "arkit_depth_available",
                    value: "\(store.captureDraft.captureMetadata.arkitDepthAvailable)"
                )
                KeyValueRow(
                    label: "arkit_depth_quality",
                    value: store.captureDraft.captureMetadata.arkitDepthQuality.rawValue
                )
                KeyValueRow(
                    label: "arkit_depth_map_size",
                    value: arkitDepthMapSize(store.captureDraft.captureMetadata)
                )
                KeyValueRow(
                    label: "arkit_confidence_coverage",
                    value: formattedOptional(store.captureDraft.captureMetadata.arkitConfidenceCoverage)
                )
                KeyValueRow(
                    label: "camera_intrinsics_available",
                    value: "\(store.captureDraft.captureMetadata.cameraIntrinsicsAvailable)"
                )
                KeyValueRow(
                    label: "food_volume_estimate_ml",
                    value: volumeEstimateRange(store.captureDraft.captureMetadata)
                )
                KeyValueRow(
                    label: "food_volume_estimate_confidence",
                    value: formattedOptional(store.captureDraft.captureMetadata.foodVolumeEstimateConfidence)
                )
                KeyValueRow(
                    label: "food_volume_estimate_method",
                    value: store.captureDraft.captureMetadata.foodVolumeEstimateMethod ?? "<none>"
                )
                KeyValueRow(label: "barcode_payload", value: store.captureDraft.captureMetadata.barcodePayload ?? "<none>")
                KeyValueRow(
                    label: "ocr_text_snippets",
                    value: store.captureDraft.captureMetadata.ocrTextSnippets.isEmpty
                        ? "<none>"
                        : store.captureDraft.captureMetadata.ocrTextSnippets.joined(separator: " | ")
                )
                KeyValueRow(label: "reference_object_hint", value: store.captureDraft.captureMetadata.referenceObjectHint ?? "<none>")

                Button("Capture Now") {
                    Task { [weak store] in
                        guard let store else {
                            return
                        }
                        await store.captureNow()
                    }
                }
            }

            Section("Actions") {
                Text("Review the Metadata tab preview before sending Analyze.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)

                Button("Run Health Check") {
                    Task { [weak store] in
                        guard let store else {
                            return
                        }
                        await store.runHealthCheck()
                    }
                }

                Button("Analyze Captured Payload") {
                    Task { [weak store] in
                        guard let store else {
                            return
                        }
                        await store.analyze()
                    }
                }
                .disabled(store.isAnalyzing)
            }

            Section("Status") {
                if let health = store.latestHealth {
                    KeyValueRow(label: "health", value: health.status)
                }
                if let analyzeError = store.latestAnalyzeError {
                    KeyValueRow(
                        label: "analyze_error",
                        value: "\(analyzeError.title): \(analyzeError.detail)"
                    )
                }
                KeyValueRow(label: "debug", value: store.debugMessage)
            }
        }
        .navigationTitle("Capture")
        .safeAreaInset(edge: .bottom) {
            Color.clear.frame(height: 96)
        }
    }

    private func formatted(_ value: Double) -> String {
        String(format: "%.1f", value)
    }

    private func formattedOptional(_ value: Double?) -> String {
        guard let value else {
            return "<none>"
        }

        return String(format: "%.2f", value)
    }

    private func arkitDepthMapSize(_ metadata: CaptureMetadata) -> String {
        guard let width = metadata.arkitDepthMapWidthPX,
              let height = metadata.arkitDepthMapHeightPX
        else {
            return "<none>"
        }

        return "\(width)x\(height)"
    }

    private func volumeEstimateRange(_ metadata: CaptureMetadata) -> String {
        guard let p10 = metadata.foodVolumeEstimateMLP10,
              let p50 = metadata.foodVolumeEstimateMLP50,
              let p90 = metadata.foodVolumeEstimateMLP90
        else {
            return "<none>"
        }

        return "\(formatted(p10)) / \(formatted(p50)) / \(formatted(p90))"
    }
}

private struct KeyValueRow: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.body)
                .textSelection(.enabled)
        }
        .padding(.vertical, 2)
    }
}
