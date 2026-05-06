import SwiftUI

struct ResultDebugView: View {
    @ObservedObject var store: CaptureFlowStore

    var body: some View {
        Form {
            Section("Result Placeholder") {
                if let response = store.latestResponse {
                    DebugRow(label: "request_id", value: response.requestID)
                    DebugRow(label: "status", value: response.status.rawValue)
                    DebugRow(label: "trace_id", value: response.traceID)

                    if !response.reasons.isEmpty {
                        ForEach(response.reasons, id: \.self) { reason in
                            Text("- \(reason)")
                        }
                    }

                    if let nutrition = response.nutrition {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("kcal best/min/max")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text("\(nutrition.kcal.bestEstimate) / \(nutrition.kcal.minEstimate) / \(nutrition.kcal.maxEstimate)")
                                .font(.body)
                        }
                    }
                } else {
                    Text("No server response yet. Run analyze from Capture tab.")
                        .foregroundStyle(.secondary)
                }
            }

            Section("Debug") {
                Text(store.debugMessage)
                    .textSelection(.enabled)
            }

            Section("Actions") {
                Button("Analyze Again") {
                    Task { [weak store] in
                        guard let store else {
                            return
                        }
                        await store.analyze()
                    }
                }
                .disabled(store.isAnalyzing)
            }
        }
        .navigationTitle("Result / Debug")
    }
}

private struct DebugRow: View {
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
