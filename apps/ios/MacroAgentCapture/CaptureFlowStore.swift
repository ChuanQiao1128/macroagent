import Foundation
import SwiftUI

enum AnalyzeErrorState: Equatable {
    case invalidServerURL(String)
    case networkFailure(String)
    case invalidResponse(String)
    case serverFailure(String)
    case unknown(String)

    var title: String {
        switch self {
        case .invalidServerURL:
            return "Invalid server URL"
        case .networkFailure:
            return "Network failure"
        case .invalidResponse:
            return "Invalid response"
        case .serverFailure:
            return "Server failure"
        case .unknown:
            return "Unknown error"
        }
    }

    var detail: String {
        switch self {
        case .invalidServerURL(let detail),
             .networkFailure(let detail),
             .invalidResponse(let detail),
             .serverFailure(let detail),
             .unknown(let detail):
            return detail
        }
    }
}

@MainActor
final class CaptureFlowStore: ObservableObject {
    @Published var serverURLText: String
    @Published var selectedCaptureMode: CaptureSourceMode
    @Published var selectedReferenceObjectHint: ReferenceObjectHint {
        didSet {
            applyReferenceHintSelection()
        }
    }
    @Published private(set) var captureDraft: CaptureDraft
    @Published private(set) var metadataPreview: AnalyzePhotoRequestEnvelope
    @Published private(set) var latestHealth: HealthResponse?
    @Published private(set) var latestResponse: AnalyzePhotoResponse?
    @Published private(set) var latestAnalyzeError: AnalyzeErrorState?
    @Published private(set) var debugMessage: String
    @Published private(set) var isAnalyzing: Bool
    @Published private(set) var quickCorrectionSelections: [QuickCorrectionSelection]

    private let captureService: CaptureService
    private let metadataBuilder: MetadataBuilder
    private let apiClientFactory: (LocalServerConfiguration) -> MacroAgentAPIClient

    init(
        captureService: CaptureService = AVFoundationCaptureService(),
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
        self.selectedCaptureMode = .camera
        let selectedReferenceObjectHint = ReferenceObjectHint.none
        self.selectedReferenceObjectHint = .none

        let draft = captureService.initialDraft(referenceObjectHint: selectedReferenceObjectHint.metadataValue)
        self.captureDraft = draft
        self.quickCorrectionSelections = []
        self.metadataPreview = Self.envelopeWithCorrections(
            metadataBuilder.buildRequestEnvelope(from: draft),
            selections: []
        )

        self.latestHealth = nil
        self.latestResponse = nil
        self.latestAnalyzeError = nil
        self.debugMessage = "Ready"
        self.isAnalyzing = false
    }

    func captureNow() async {
        debugMessage = selectedCaptureMode == .camera
            ? "Capturing photo with AVFoundation..."
            : "Preparing sample fallback capture..."

        do {
            let draft = try await captureService.prepareDraft(
                mode: selectedCaptureMode,
                referenceObjectHint: selectedReferenceObjectHint.metadataValue
            )
            captureDraft = draft
            quickCorrectionSelections = []
            rebuildMetadataPreview()
            latestResponse = nil
            latestAnalyzeError = nil
            debugMessage = "Prepared \(draft.captureSourceMode.displayName.lowercased()) draft with \(draft.imageIdentity.byteSize) bytes."
        } catch {
            debugMessage = "Capture failed: \(error.localizedDescription)"
        }
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
        if selectedCaptureMode == .camera, captureDraft.captureSourceMode != .camera {
            debugMessage = "Capture a real camera photo before analyze while Camera mode is selected."
            latestResponse = nil
            latestAnalyzeError = nil
            return
        }

        isAnalyzing = true
        latestAnalyzeError = nil
        debugMessage = "Submitting metadata payload to local server..."

        do {
            let response = try await currentAPIClient().analyzePhoto(metadataPreview)
            latestResponse = response
            latestAnalyzeError = nil
            debugMessage = "Received \(response.status.rawValue) response for request \(response.requestID)."
        } catch {
            latestResponse = nil
            let errorState = classifyAnalyzeError(error)
            latestAnalyzeError = errorState
            debugMessage = "Analyze request failed (\(errorState.title)): \(errorState.detail)"
        }

        isAnalyzing = false
    }

    func applyQuickCorrection(correctionID: String, selectedOption: String) async {
        upsertQuickCorrectionSelection(
            QuickCorrectionSelection(
                correctionID: correctionID,
                selectedOption: selectedOption
            )
        )
        debugMessage = "Applying quick correction: \(correctionID)=\(selectedOption)."
        await analyze()
    }

    private func currentAPIClient() -> MacroAgentAPIClient {
        let configuration = LocalServerConfiguration(baseURLString: serverURLText)
        return apiClientFactory(configuration)
    }

    private func upsertQuickCorrectionSelection(_ selection: QuickCorrectionSelection) {
        var selections = quickCorrectionSelections.filter {
            $0.correctionID != selection.correctionID
        }
        selections.append(selection)
        quickCorrectionSelections = selections
        rebuildMetadataPreview()
    }

    private func rebuildMetadataPreview() {
        metadataPreview = Self.envelopeWithCorrections(
            metadataBuilder.buildRequestEnvelope(from: captureDraft),
            selections: quickCorrectionSelections
        )
    }

    private func applyReferenceHintSelection() {
        let selectedHint = selectedReferenceObjectHint.metadataValue
        let currentMetadata = captureDraft.captureMetadata

        if currentMetadata.referenceObjectHint == selectedHint {
            return
        }

        let updatedMetadata = CaptureMetadata(
            deviceModel: currentMetadata.deviceModel,
            osVersion: currentMetadata.osVersion,
            cameraPosition: currentMetadata.cameraPosition,
            orientation: currentMetadata.orientation,
            pitchDegrees: currentMetadata.pitchDegrees,
            rollDegrees: currentMetadata.rollDegrees,
            focalLengthMM: currentMetadata.focalLengthMM,
            lensHint: currentMetadata.lensHint,
            depthAvailable: currentMetadata.depthAvailable,
            depthQuality: currentMetadata.depthQuality,
            lidarAvailable: currentMetadata.lidarAvailable,
            arkitSceneDepthSupported: currentMetadata.arkitSceneDepthSupported,
            arkitSmoothedSceneDepthSupported: currentMetadata.arkitSmoothedSceneDepthSupported,
            arkitDepthAvailable: currentMetadata.arkitDepthAvailable,
            arkitDepthQuality: currentMetadata.arkitDepthQuality,
            arkitDepthMapWidthPX: currentMetadata.arkitDepthMapWidthPX,
            arkitDepthMapHeightPX: currentMetadata.arkitDepthMapHeightPX,
            arkitConfidenceCoverage: currentMetadata.arkitConfidenceCoverage,
            cameraIntrinsicsAvailable: currentMetadata.cameraIntrinsicsAvailable,
            foodVolumeEstimateMLP10: currentMetadata.foodVolumeEstimateMLP10,
            foodVolumeEstimateMLP50: currentMetadata.foodVolumeEstimateMLP50,
            foodVolumeEstimateMLP90: currentMetadata.foodVolumeEstimateMLP90,
            foodVolumeEstimateConfidence: currentMetadata.foodVolumeEstimateConfidence,
            foodVolumeEstimateMethod: currentMetadata.foodVolumeEstimateMethod,
            barcodePayload: currentMetadata.barcodePayload,
            barcodePayloadSafe: currentMetadata.barcodePayloadSafe,
            ocrTextSnippets: currentMetadata.ocrTextSnippets,
            referenceObjectHint: selectedHint,
            captureTimestamp: currentMetadata.captureTimestamp
        )

        captureDraft = CaptureDraft(
            requestID: captureDraft.requestID,
            userID: captureDraft.userID,
            captureSourceMode: captureDraft.captureSourceMode,
            imageIdentity: captureDraft.imageIdentity,
            captureMetadata: updatedMetadata,
            encodedImageBytes: captureDraft.encodedImageBytes
        )
        rebuildMetadataPreview()
    }

    private static func envelopeWithCorrections(
        _ envelope: AnalyzePhotoRequestEnvelope,
        selections: [QuickCorrectionSelection]
    ) -> AnalyzePhotoRequestEnvelope {
        AnalyzePhotoRequestEnvelope(
            payload: envelope.payload,
            options: AnalyzePhotoOptions(
                logAnyway: envelope.options.logAnyway,
                logAnywayReason: envelope.options.logAnywayReason,
                quickCorrectionSelections: selections
            )
        )
    }

    private func classifyAnalyzeError(_ error: Error) -> AnalyzeErrorState {
        if let apiError = error as? APIClientError {
            switch apiError {
            case .invalidBaseURL(let raw):
                return .invalidServerURL("Invalid server URL: \(raw)")
            case .unexpectedStatusCode(let code):
                return .serverFailure("Server returned HTTP \(code).")
            case .encodingFailed:
                return .invalidResponse("Unable to encode request payload.")
            case .invalidResponse(let detail):
                return .invalidResponse(detail)
            }
        }

        if let urlError = error as? URLError {
            return .networkFailure(urlError.localizedDescription)
        }

        if error is DecodingError {
            return .invalidResponse("Response JSON did not match expected fields.")
        }

        return .unknown(error.localizedDescription)
    }
}
