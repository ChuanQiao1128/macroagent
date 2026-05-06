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

                Text("Optional scale hint passed as capture_metadata.reference_object_hint.")
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
