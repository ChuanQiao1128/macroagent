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

            Section("Capture Placeholder") {
                KeyValueRow(label: "request_id", value: store.captureDraft.requestID)
                KeyValueRow(label: "user_id", value: store.captureDraft.userID)
                KeyValueRow(label: "image_sha256", value: store.captureDraft.imageIdentity.imageSHA256)
                KeyValueRow(label: "image_size", value: "\(store.captureDraft.imageIdentity.widthPX)x\(store.captureDraft.imageIdentity.heightPX)")
                KeyValueRow(label: "bytes", value: "\(store.captureDraft.imageIdentity.byteSize)")

                Button("Refresh Placeholder Capture") { [weak store] in
                    store?.refreshDraft()
                }
            }

            Section("Actions") {
                Button("Run Health Check") {
                    Task { [weak store] in
                        guard let store else {
                            return
                        }
                        await store.runHealthCheck()
                    }
                }

                Button("Analyze Placeholder Payload") {
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
