import Foundation

protocol MetadataBuilder {
    func buildRequestEnvelope(from draft: CaptureDraft) -> AnalyzePhotoRequestEnvelope
}

struct PlaceholderMetadataBuilder: MetadataBuilder {
    func buildRequestEnvelope(from draft: CaptureDraft) -> AnalyzePhotoRequestEnvelope {
        let payload = AnalyzePhotoRequest(
            requestID: draft.requestID,
            userID: draft.userID,
            imageIdentity: draft.imageIdentity,
            captureMetadata: draft.captureMetadata
        )

        let options = AnalyzePhotoOptions(
            logAnyway: false,
            logAnywayReason: nil
        )

        return AnalyzePhotoRequestEnvelope(payload: payload, options: options)
    }
}
