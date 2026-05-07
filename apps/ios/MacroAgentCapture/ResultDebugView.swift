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

                    if !response.quickCorrections.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("quick_corrections")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            ForEach(response.quickCorrections) { correction in
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(correction.correctionID)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                    Text(correction.label)
                                    Text(correction.options.joined(separator: " / "))
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    ForEach(correction.options, id: \.self) { option in
                                        Button(option) {
                                            Task { [weak store] in
                                                guard let store else {
                                                    return
                                                }
                                                await store.applyQuickCorrection(
                                                    correctionID: correction.correctionID,
                                                    selectedOption: option
                                                )
                                            }
                                        }
                                        .disabled(store.isAnalyzing)
                                    }
                                }
                            }
                        }
                    }

                    if let nutrition = response.nutrition {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("nutrition")
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
        .safeAreaInset(edge: .bottom) {
            Color.clear.frame(height: 96)
        }
    }
}

private struct NutritionMetricRow: View {
    let label: String
    let metric: NutritionMetric

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(label)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                Text(formatted(metric.bestEstimate))
                    .font(.body.monospacedDigit())
            }

            Text("range \(formatted(metric.minEstimate)) - \(formatted(metric.maxEstimate))")
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)

            Text(metric.source)
                .font(.caption2)
                .foregroundStyle(.tertiary)
                .textSelection(.enabled)
        }
        .padding(.vertical, 4)
    }

    private func formatted(_ value: Double) -> String {
        if label == "kcal" || label == "sodium_mg" {
            return String(format: "%.0f", value)
        }

        return String(format: "%.1f", value)
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
