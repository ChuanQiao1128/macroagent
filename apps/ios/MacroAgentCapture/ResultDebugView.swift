import SwiftUI

struct ResultDebugView: View {
    @ObservedObject var store: CaptureFlowStore

    var body: some View {
        Form {
            Section("Result") {
                if let response = store.latestResponse {
                    DebugRow(label: "request_id", value: response.requestID)
                    DebugRow(label: "status", value: response.status.rawValue)
                    DebugRow(label: "trace_id", value: response.traceID)
                    DebugRow(label: "ledger_entry_id", value: response.ledgerEntryID ?? "<none>")

                    if !response.reasons.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("reasons")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            ForEach(Array(response.reasons.enumerated()), id: \.offset) { index, reason in
                                Text("\(index + 1). \(reason)")
                            }
                        }
                    }

                    if !response.clarifyQuestions.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("clarify_questions")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            ForEach(response.clarifyQuestions) { question in
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(question.questionID)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                    Text(question.text)
                                }
                            }
                        }
                    }

                    if let nutrition = response.nutrition {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("nutrition (best / min / max / source)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            NutritionMetricRow(label: "kcal", metric: nutrition.kcal)
                            NutritionMetricRow(label: "protein_g", metric: nutrition.proteinG)
                            NutritionMetricRow(label: "carbs_g", metric: nutrition.carbsG)
                            NutritionMetricRow(label: "fat_g", metric: nutrition.fatG)
                            NutritionMetricRow(label: "sugar_g", metric: nutrition.sugarG)
                            NutritionMetricRow(label: "sodium_mg", metric: nutrition.sodiumMG)
                            NutritionMetricRow(label: "fiber_g", metric: nutrition.fiberG)
                        }
                    } else {
                        Text("No nutrition metrics in this response (expected when status=BLOCK).")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                } else {
                    Text("No server response yet. Run analyze from Capture tab.")
                        .foregroundStyle(.secondary)
                }
            }

            Section("Analyze Error") {
                if let error = store.latestAnalyzeError {
                    DebugRow(label: "type", value: error.title)
                    Text(error.detail)
                        .textSelection(.enabled)
                } else {
                    Text("No analyze error.")
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

private struct NutritionMetricRow: View {
    let label: String
    let metric: NutritionMetric

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(
                "\(metric.bestEstimate) / \(metric.minEstimate) / \(metric.maxEstimate) / \(metric.source)"
            )
            .font(.footnote.monospacedDigit())
            .textSelection(.enabled)
        }
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
