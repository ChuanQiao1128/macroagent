import Foundation
import SwiftUI

@MainActor
final class CaptureFlowStore: ObservableObject {
    @Published var serverURLText: String
    @Published private(set) var captureDraft: CaptureDraft
    @Published private(set) var metadataPreview: AnalyzePhotoRequestEnvelope
    @Published private(set) var latestHealth: HealthResponse?
    @Published private(set) var latestResponse: AnalyzePhotoResponse?
    @Published private(set) var debugMessage: String
    @Published private(set) var isAnalyzing: Bool

    private let captureService: CaptureService
    private let metadataBuilder: MetadataBuilder
    private let apiClientFactory: (LocalServerConfiguration) -> MacroAgentAPIClient

    init(
        captureService: CaptureService = PlaceholderCaptureService(),
        metadataBuilder: MetadataBuilder = PlaceholderMetadataBuilder(),
        initialServerURL: String = LocalServerConfiguration.defaultBaseURLString,
        apiClientFactory: @escaping (LocalServerConfiguration) -> MacroAgentAPIClient = { configuration in
            LocalServerAPIClient(configuration: configuration)
        }
    ) {
        self.captureService = captureService
        self.metadataBuilder = metadataBuilder
        self.apiClientFactory = apiClientFactory
        self.serverURLText = initialServerURL

        let draft = captureService.prepareDraft()
        self.captureDraft = draft
        self.metadataPreview = metadataBuilder.buildRequestEnvelope(from: draft)

        self.latestHealth = nil
        self.latestResponse = nil
        self.debugMessage = "Ready"
        self.isAnalyzing = false
    }

    func refreshDraft() {
        let draft = captureService.prepareDraft()
        captureDraft = draft
        metadataPreview = metadataBuilder.buildRequestEnvelope(from: draft)
        latestResponse = nil
        debugMessage = "Prepared deterministic placeholder capture draft."
    }

    func runHealthCheck() async {
        debugMessage = "Checking server health..."
        do {
            let health = try await currentAPIClient().healthCheck()
            latestHealth = health
            debugMessage = "Health check succeeded with status: \(health.status)."
        } catch {
            latestHealth = nil
            debugMessage = "Health check failed: \(error.localizedDescription)"
        }
    }

    func analyze() async {
        isAnalyzing = true
        debugMessage = "Submitting metadata payload to local server..."

        do {
            let response = try await currentAPIClient().analyzePhoto(metadataPreview)
            latestResponse = response
            debugMessage = "Received \(response.status.rawValue) response for request \(response.requestID)."
        } catch {
            latestResponse = nil
            debugMessage = "Analyze request failed: \(error.localizedDescription)"
        }

        isAnalyzing = false
    }

    private func currentAPIClient() -> MacroAgentAPIClient {
        let configuration = LocalServerConfiguration(baseURLString: serverURLText)
        return apiClientFactory(configuration)
    }
}
