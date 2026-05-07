import SwiftUI

struct ResultView: View {
    @ObservedObject var store: CaptureFlowStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let response = store.latestResponse {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(alignment: .center, spacing: 10) {
                            Text(response.status.rawValue)
                                .font(.subheadline.weight(.semibold))
                                .padding(.horizontal, 10)
                                .padding(.vertical, 6)
                                .background(statusColor(for: response.status).opacity(0.18))
                                .foregroundStyle(statusColor(for: response.status))
                                .clipShape(Capsule())

                            Text("Confidence: \(response.uncertaintySummary.confidenceLabel.capitalized)")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)

                            Spacer()
                        }

                        Text(statusMessage(for: response.status))
                            .font(.subheadline)

                        if let relativeRangeWidth = response.uncertaintySummary.relativeRangeWidth {
                            Text("Relative interval width: \(Int((relativeRangeWidth * 100).rounded()))%")
                                .font(.footnote.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }

                        if !response.reasons.isEmpty {
                            Text(response.reasons.joined(separator: " • "))
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.blue.opacity(0.08))
                    .clipShape(RoundedRectangle(cornerRadius: 14))

                    if let nutrition = response.nutrition {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Nutrition estimate")
                                .font(.headline)
                            Text("Best estimate with conservative range.")
                                .font(.footnote)
                                .foregroundStyle(.secondary)

                            UserNutritionMetricRow(
                                metricKey: "kcal",
                                displayName: "Energy",
                                unit: "kcal",
                                metric: nutrition.kcal,
                                decimals: 0
                            )
                            UserNutritionMetricRow(
                                metricKey: "protein_g",
                                displayName: "Protein",
                                unit: "g",
                                metric: nutrition.proteinG,
                                decimals: 1
                            )
                            UserNutritionMetricRow(
                                metricKey: "carbs_g",
                                displayName: "Carbohydrates",
                                unit: "g",
                                metric: nutrition.carbsG,
                                decimals: 1
                            )
                            UserNutritionMetricRow(
                                metricKey: "fat_g",
                                displayName: "Fat",
                                unit: "g",
                                metric: nutrition.fatG,
                                decimals: 1
                            )
                            UserNutritionMetricRow(
                                metricKey: "sugar_g",
                                displayName: "Sugar",
                                unit: "g",
                                metric: nutrition.sugarG,
                                decimals: 1
                            )
                            UserNutritionMetricRow(
                                metricKey: "sodium_mg",
                                displayName: "Sodium",
                                unit: "mg",
                                metric: nutrition.sodiumMG,
                                decimals: 0
                            )
                            UserNutritionMetricRow(
                                metricKey: "fiber_g",
                                displayName: "Fiber",
                                unit: "g",
                                metric: nutrition.fiberG,
                                decimals: 1
                            )
                        }
                    } else {
                        Text("No nutrition estimate is available for this response.")
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }

                    let uncertaintyDrivers = Array(response.uncertaintySummary.uncertaintyFlags.prefix(3))
                    if !uncertaintyDrivers.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("High-impact uncertainty drivers")
                                .font(.headline)
                            ForEach(uncertaintyDrivers, id: \.self) { driver in
                                Text("• \(driverLabel(driver))")
                                    .font(.subheadline)
                            }
                        }
                        .padding(14)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.orange.opacity(0.10))
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                    }

                    let primaryQuestions = primaryQuestions(for: response)
                    if !primaryQuestions.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Primary question\(primaryQuestions.count > 1 ? "s" : "")")
                                .font(.headline)
                            ForEach(Array(primaryQuestions.enumerated()), id: \.offset) { index, question in
                                Text("\(index + 1). \(question)")
                                    .font(.subheadline)
                            }
                        }
                        .padding(14)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.yellow.opacity(0.12))
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                    }

                    if !response.quickCorrections.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Quick corrections")
                                .font(.headline)
                            Text("Update key assumptions and rerun analysis.")
                                .font(.footnote)
                                .foregroundStyle(.secondary)

                            ForEach(sortedQuickCorrections(response.quickCorrections)) { correction in
                                UserQuickCorrectionCard(
                                    title: correctionTitle(correction),
                                    correction: correction,
                                    selectedOption: selectedOption(for: correction),
                                    isAnalyzing: store.isAnalyzing
                                ) { option in
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
                            }
                        }
                    }
                } else {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("No result yet")
                            .font(.headline)
                        Text("Capture a photo and run Analyze from the Capture tab to see nutrition estimates.")
                            .foregroundStyle(.secondary)
                    }
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.gray.opacity(0.12))
                    .clipShape(RoundedRectangle(cornerRadius: 14))

                    if let analyzeError = store.latestAnalyzeError {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(analyzeError.title)
                                .font(.headline)
                            Text(analyzeError.detail)
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                        }
                        .padding(14)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.red.opacity(0.10))
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                    }
                }

                Text("Need raw request/response details? Open the Debug tab.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .padding(.top, 4)
            }
            .padding()
        }
        .navigationTitle("Result")
        .safeAreaInset(edge: .bottom) {
            Color.clear.frame(height: 96)
        }
    }

    private func selectedOption(for correction: QuickCorrection) -> String? {
        store.quickCorrectionSelections.first { selection in
            selection.correctionID == correction.correctionID
        }?.selectedOption
    }

    private func sortedQuickCorrections(_ corrections: [QuickCorrection]) -> [QuickCorrection] {
        corrections.sorted { lhs, rhs in
            let lhsPriority = correctionPriority(lhs)
            let rhsPriority = correctionPriority(rhs)
            if lhsPriority == rhsPriority {
                return lhs.correctionID < rhs.correctionID
            }
            return lhsPriority < rhsPriority
        }
    }

    private func correctionPriority(_ correction: QuickCorrection) -> Int {
        switch correction.correctionID {
        case "portion_size_quick_adjust":
            return 0
        case "consumed_amount_check":
            return 1
        case "hidden_sauce_oil_check":
            return 2
        case "drink_add_ins_check":
            return 3
        default:
            switch correction.correctionType {
            case "portion_size":
                return 0
            case "consumed_amount":
                return 1
            case "hidden_ingredient":
                return 2
            default:
                return 4
            }
        }
    }

    private func correctionTitle(_ correction: QuickCorrection) -> String {
        switch correction.correctionID {
        case "portion_size_quick_adjust":
            return "Portion size"
        case "consumed_amount_check":
            return "Amount consumed"
        case "hidden_sauce_oil_check":
            return "Sauce/oil"
        case "drink_add_ins_check":
            return "Drink add-ins"
        default:
            if correction.correctionType == "portion_size" {
                return "Portion size"
            }
            if correction.correctionType == "consumed_amount" {
                return "Amount consumed"
            }
            return correction.label
        }
    }

    private func primaryQuestions(for response: AnalyzePhotoResponse) -> [String] {
        if !response.clarifyQuestions.isEmpty {
            return Array(response.clarifyQuestions.map(\.text).prefix(2))
        }

        let derived = sortedQuickCorrections(response.quickCorrections).compactMap { correction in
            switch correction.correctionID {
            case "portion_size_quick_adjust":
                return "Does the visible portion look smaller, about right, or larger than estimated?"
            case "consumed_amount_check":
                return "How much of this did you actually consume?"
            case "hidden_sauce_oil_check":
                return "Was there sauce or cooking oil that is not obvious in the photo?"
            case "drink_add_ins_check":
                return "Did the drink include sugar, milk, or cream?"
            default:
                return nil
            }
        }
        return Array(derived.prefix(2))
    }

    private func driverLabel(_ rawValue: String) -> String {
        switch rawValue {
        case "wide_portion_range":
            return "Portion-size estimate is still wide."
        case "volume_geometry_estimate":
            return "Volume was inferred from photo geometry."
        case "volume_density_estimate":
            return "Food density assumptions affect the macro estimate."
        case "manual_container_volume_estimate":
            return "Container-size assumptions affect the estimate."
        case "approximate_quantity":
            return "Input quantity appears approximate."
        case "unknown_portion_hint":
            return "Portion hint could not be mapped confidently."
        case "missing_portion_hint":
            return "No direct portion hint was available."
        case "blocked_input":
            return "Input quality is too uncertain for a safe estimate."
        case "user_corrected_portion_size":
            return "Portion size was manually adjusted."
        case "user_corrected_hidden_sauce_oil":
            return "Hidden sauce/oil was manually adjusted."
        case "user_corrected_consumed_amount":
            return "Consumed amount was manually adjusted."
        default:
            return rawValue.replacingOccurrences(of: "_", with: " ")
        }
    }

    private func statusColor(for status: AnalysisDecision) -> Color {
        switch status {
        case .accept:
            return .green
        case .warn:
            return .orange
        case .clarify:
            return .yellow
        case .block:
            return .red
        }
    }

    private func statusMessage(for status: AnalysisDecision) -> String {
        switch status {
        case .accept:
            return "Estimate is suitable for logging."
        case .warn:
            return "Estimate is usable but uncertainty is higher than target."
        case .clarify:
            return "A quick confirmation is needed before trusting this estimate."
        case .block:
            return "Unable to provide a safe estimate from this capture."
        }
    }
}

private struct UserNutritionMetricRow: View {
    let metricKey: String
    let displayName: String
    let unit: String
    let metric: NutritionMetric
    let decimals: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(displayName)
                        .font(.subheadline.weight(.semibold))
                    Text(metricKey)
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text("~\(formatted(metric.bestEstimate)) \(unit)")
                    .font(.body.monospacedDigit())
            }

            Text("Range \(formatted(metric.minEstimate)) - \(formatted(metric.maxEstimate)) \(unit)")
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)

            Text("Source: \(metric.source)")
                .font(.caption2)
                .foregroundStyle(.tertiary)
                .textSelection(.enabled)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.gray.opacity(0.10))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func formatted(_ value: Double) -> String {
        if decimals == 0 {
            return String(format: "%.0f", value)
        }
        return String(format: "%.1f", value)
    }
}

private struct UserQuickCorrectionCard: View {
    let title: String
    let correction: QuickCorrection
    let selectedOption: String?
    let isAnalyzing: Bool
    let onSelect: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.subheadline.weight(.semibold))
            Text(correction.label)
                .font(.footnote)
                .foregroundStyle(.secondary)

            ForEach(correction.options, id: \.self) { option in
                let isSelected = selectedOption == option
                Button {
                    onSelect(option)
                } label: {
                    HStack {
                        Text(option)
                            .font(.footnote)
                            .foregroundStyle(.primary)
                        Spacer()
                        if isSelected {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(Color.accentColor)
                        }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(isSelected ? Color.accentColor.opacity(0.18) : Color.gray.opacity(0.10))
                    .clipShape(RoundedRectangle(cornerRadius: 10))
                }
                .buttonStyle(.plain)
                .disabled(isAnalyzing)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.gray.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

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
