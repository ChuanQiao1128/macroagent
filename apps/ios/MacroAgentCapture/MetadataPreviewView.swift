import SwiftUI

struct MetadataPreviewView: View {
    @ObservedObject var store: CaptureFlowStore

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Capture metadata payload that will be sent to `/v1/meals/analyze-photo`.")
                .font(.footnote)
                .foregroundStyle(.secondary)

            ScrollView {
                Text(previewJSON)
                    .font(.system(.footnote, design: .monospaced))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .textSelection(.enabled)
            }

            Button("Rebuild From Capture Service") {
                Task { [weak store] in
                    guard let store else {
                        return
                    }
                    await store.captureNow()
                }
            }
            .buttonStyle(.bordered)
        }
        .padding()
        .navigationTitle("Metadata Preview")
    }

    private var previewJSON: String {
        JSONPreviewRenderer.render(store.metadataPreview)
    }
}

enum JSONPreviewRenderer {
    static func render<T: Encodable>(_ value: T) -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]

        guard let data = try? encoder.encode(value) else {
            return "<unable to encode payload>"
        }

        return String(decoding: data, as: UTF8.self)
    }
}
