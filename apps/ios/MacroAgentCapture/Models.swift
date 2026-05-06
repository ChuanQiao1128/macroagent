import Foundation

enum AnalysisDecision: String, Codable, CaseIterable {
    case accept = "ACCEPT"
    case warn = "WARN"
    case clarify = "CLARIFY"
    case block = "BLOCK"
}

enum CameraPosition: String, Codable, CaseIterable {
    case front
    case back
    case unknown
}

enum CaptureOrientation: String, Codable, CaseIterable {
    case portrait
    case portraitUpsideDown = "portrait_upside_down"
    case landscapeLeft = "landscape_left"
    case landscapeRight = "landscape_right"
    case faceUp = "face_up"
    case faceDown = "face_down"
    case unknown
}

enum DepthQuality: String, Codable, CaseIterable {
    case none
    case low
    case medium
    case high
    case unknown
}

struct ImageIdentity: Codable, Hashable {
    let imageSHA256: String
    let imageFormat: String
    let widthPX: Int
    let heightPX: Int
    let byteSize: Int

    enum CodingKeys: String, CodingKey {
        case imageSHA256 = "image_sha256"
        case imageFormat = "image_format"
        case widthPX = "width_px"
        case heightPX = "height_px"
        case byteSize = "byte_size"
    }
}

struct CaptureMetadata: Codable, Hashable {
    let deviceModel: String
    let osVersion: String
    let cameraPosition: CameraPosition
    let orientation: CaptureOrientation
    let pitchDegrees: Double
    let rollDegrees: Double
    let focalLengthMM: Double?
    let lensHint: String?
    let depthAvailable: Bool
    let depthQuality: DepthQuality
    let lidarAvailable: Bool
    let barcodePayload: String?
    let barcodePayloadSafe: Bool
    let ocrTextSnippets: [String]
    let referenceObjectHint: String?
    let captureTimestamp: String

    enum CodingKeys: String, CodingKey {
        case deviceModel = "device_model"
        case osVersion = "os_version"
        case cameraPosition = "camera_position"
        case orientation
        case pitchDegrees = "pitch_degrees"
        case rollDegrees = "roll_degrees"
        case focalLengthMM = "focal_length_mm"
        case lensHint = "lens_hint"
        case depthAvailable = "depth_available"
        case depthQuality = "depth_quality"
        case lidarAvailable = "lidar_available"
        case barcodePayload = "barcode_payload"
        case barcodePayloadSafe = "barcode_payload_safe"
        case ocrTextSnippets = "ocr_text_snippets"
        case referenceObjectHint = "reference_object_hint"
        case captureTimestamp = "capture_timestamp"
    }
}

struct CaptureDraft: Hashable {
    let requestID: String
    let userID: String
    let imageIdentity: ImageIdentity
    let captureMetadata: CaptureMetadata
}

struct AnalyzePhotoRequest: Codable, Hashable {
    let requestID: String
    let userID: String
    let imageIdentity: ImageIdentity
    let captureMetadata: CaptureMetadata

    enum CodingKeys: String, CodingKey {
        case requestID = "request_id"
        case userID = "user_id"
        case imageIdentity = "image_identity"
        case captureMetadata = "capture_metadata"
    }
}

struct AnalyzePhotoOptions: Codable, Hashable {
    let logAnyway: Bool
    let logAnywayReason: String?

    enum CodingKeys: String, CodingKey {
        case logAnyway = "log_anyway"
        case logAnywayReason = "log_anyway_reason"
    }
}

struct AnalyzePhotoRequestEnvelope: Codable, Hashable {
    let payload: AnalyzePhotoRequest
    let options: AnalyzePhotoOptions
}

struct NutritionMetric: Codable, Hashable {
    let bestEstimate: Double
    let minEstimate: Double
    let maxEstimate: Double
    let source: String

    enum CodingKeys: String, CodingKey {
        case bestEstimate = "best_estimate"
        case minEstimate = "min_estimate"
        case maxEstimate = "max_estimate"
        case source
    }
}

struct NutritionMetrics: Codable, Hashable {
    let kcal: NutritionMetric
    let proteinG: NutritionMetric
    let carbsG: NutritionMetric
    let fatG: NutritionMetric
    let sugarG: NutritionMetric
    let sodiumMG: NutritionMetric
    let fiberG: NutritionMetric

    enum CodingKeys: String, CodingKey {
        case kcal
        case proteinG = "protein_g"
        case carbsG = "carbs_g"
        case fatG = "fat_g"
        case sugarG = "sugar_g"
        case sodiumMG = "sodium_mg"
        case fiberG = "fiber_g"
    }
}

struct ClarifyQuestion: Codable, Hashable, Identifiable {
    let questionID: String
    let text: String

    var id: String { questionID }

    enum CodingKeys: String, CodingKey {
        case questionID = "question_id"
        case text
    }
}

struct UncertaintySummary: Codable, Hashable {
    let confidenceLabel: String
    let relativeRangeWidth: Double?
    let uncertaintyFlags: [String]

    enum CodingKeys: String, CodingKey {
        case confidenceLabel = "confidence_label"
        case relativeRangeWidth = "relative_range_width"
        case uncertaintyFlags = "uncertainty_flags"
    }
}

struct AnalyzePhotoResponse: Codable, Hashable {
    let requestID: String
    let status: AnalysisDecision
    let nutrition: NutritionMetrics?
    let reasons: [String]
    let clarifyQuestions: [ClarifyQuestion]
    let traceID: String
    let ledgerEntryID: String?
    let uncertaintySummary: UncertaintySummary

    enum CodingKeys: String, CodingKey {
        case requestID = "request_id"
        case status
        case nutrition
        case reasons
        case clarifyQuestions = "clarify_questions"
        case traceID = "trace_id"
        case ledgerEntryID = "ledger_entry_id"
        case uncertaintySummary = "uncertainty_summary"
    }
}

struct HealthResponse: Codable, Hashable {
    let status: String
}
