import Foundation

protocol CaptureService {
    func prepareDraft() -> CaptureDraft
}

struct PlaceholderCaptureService: CaptureService {
    func prepareDraft() -> CaptureDraft {
        let imageIdentity = ImageIdentity(
            imageSHA256: String(repeating: "a", count: 64),
            imageFormat: "jpeg",
            widthPX: 3024,
            heightPX: 4032,
            byteSize: 1_048_576
        )

        let metadata = CaptureMetadata(
            deviceModel: "iPhone Placeholder",
            osVersion: "iOS 17.0",
            cameraPosition: .back,
            orientation: .portrait,
            pitchDegrees: 0,
            rollDegrees: 0,
            focalLengthMM: nil,
            lensHint: "standard",
            depthAvailable: false,
            depthQuality: .none,
            lidarAvailable: false,
            barcodePayload: nil,
            barcodePayloadSafe: false,
            ocrTextSnippets: ["placeholder text"],
            referenceObjectHint: "none",
            captureTimestamp: "2026-01-01T00:00:00Z"
        )

        return CaptureDraft(
            requestID: "ios-smoke-request-0001",
            userID: "ios-smoke-user-0001",
            imageIdentity: imageIdentity,
            captureMetadata: metadata
        )
    }
}
