@preconcurrency import AVFoundation
import CoreMotion
import CryptoKit
import Foundation
import ImageIO
import Vision

protocol CaptureService {
    func initialDraft(referenceObjectHint: String?) -> CaptureDraft
    func prepareDraft(mode: CaptureSourceMode, referenceObjectHint: String?) async throws -> CaptureDraft
}

extension CaptureService {
    func initialDraft() -> CaptureDraft {
        initialDraft(referenceObjectHint: nil)
    }

    func prepareDraft(mode: CaptureSourceMode) async throws -> CaptureDraft {
        try await prepareDraft(mode: mode, referenceObjectHint: nil)
    }
}

enum CaptureServiceError: LocalizedError {
    case cameraPermissionDenied
    case cameraUnavailable
    case cameraConfigurationFailed
    case simulatorRequiresSampleMode
    case captureInProgress
    case captureFailed
    case captureServiceReleased
    case invalidImageData

    var errorDescription: String? {
        switch self {
        case .cameraPermissionDenied:
            return "Camera permission denied. Enable camera access in Settings."
        case .cameraUnavailable:
            return "No camera is available on this device. Use Sample Fallback mode."
        case .cameraConfigurationFailed:
            return "Unable to configure camera capture session."
        case .simulatorRequiresSampleMode:
            return "Simulator does not provide a real camera for this flow. Switch to Sample Fallback mode."
        case .captureInProgress:
            return "A camera capture is already in progress."
        case .captureFailed:
            return "Photo capture failed before encoded bytes were produced."
        case .captureServiceReleased:
            return "Capture service was released before photo capture completed."
        case .invalidImageData:
            return "Captured image bytes were invalid or unreadable."
        }
    }
}

struct PlaceholderCaptureService: CaptureService {
    private let defaultUserID = "ios-smoke-user-0001"

    func initialDraft(referenceObjectHint: String?) -> CaptureDraft {
        SampleCaptureFactory.makeDraft(userID: defaultUserID, referenceObjectHint: referenceObjectHint)
    }

    func prepareDraft(mode: CaptureSourceMode, referenceObjectHint: String?) async throws -> CaptureDraft {
        SampleCaptureFactory.makeDraft(userID: defaultUserID, referenceObjectHint: referenceObjectHint)
    }
}

final class AVFoundationCaptureService: NSObject, CaptureService {
    private struct CameraRuntime {
        let session: AVCaptureSession
        let photoOutput: AVCapturePhotoOutput
        let camera: AVCaptureDevice
        let cameraPosition: CameraPosition
        let lidarAvailable: Bool
    }

    private struct CapturedPhoto {
        let photo: AVCapturePhoto
        let suggestedFileTypeRawValue: String?
        let captureTimestamp: Date
        let motionSnapshot: MotionSnapshot?
    }

    private let defaultUserID: String
    private let sessionQueue = DispatchQueue(label: "com.macroagent.capture.session")
    private let continuationLock = NSLock()
    private var pendingContinuation: CheckedContinuation<AVCapturePhoto, Error>?

    init(defaultUserID: String = "ios-smoke-user-0001") {
        self.defaultUserID = defaultUserID
    }

    func initialDraft(referenceObjectHint: String?) -> CaptureDraft {
        SampleCaptureFactory.makeDraft(userID: defaultUserID, referenceObjectHint: referenceObjectHint)
    }

    func prepareDraft(mode: CaptureSourceMode, referenceObjectHint: String?) async throws -> CaptureDraft {
        switch mode {
        case .sampleFallback:
            return SampleCaptureFactory.makeDraft(userID: defaultUserID, referenceObjectHint: referenceObjectHint)
        case .camera:
            return try await prepareCameraDraft(referenceObjectHint: referenceObjectHint)
        }
    }

    private func prepareCameraDraft(referenceObjectHint: String?) async throws -> CaptureDraft {
#if targetEnvironment(simulator)
        throw CaptureServiceError.simulatorRequiresSampleMode
#else
        try await ensureCameraAccess()
        let runtime = try await buildCameraRuntime()
        try await startSession(runtime.session)

        let motionSampler = MotionSampler()
        motionSampler.start()
        defer {
            motionSampler.stop()
        }

        // Allow CoreMotion updates to warm up so we can sample near shutter time.
        try? await Task.sleep(nanoseconds: 120_000_000)

        let capturedPhoto: CapturedPhoto
        do {
            capturedPhoto = try await capturePhoto(with: runtime.photoOutput, motionSampler: motionSampler)
        } catch {
            await stopSession(runtime.session)
            throw error
        }

        await stopSession(runtime.session)

        let encodedBytes = try extractEncodedBytes(from: capturedPhoto.photo)
        let imageIdentity = try ImageIdentityExtractor.build(
            from: encodedBytes,
            suggestedFileTypeRawValue: capturedPhoto.suggestedFileTypeRawValue
        )

        let motionSnapshot = capturedPhoto.motionSnapshot ?? motionSampler.snapshot()
        let depthAvailable = capturedPhoto.photo.depthData != nil
        let depthQuality = DepthQualityEstimator.from(depthData: capturedPhoto.photo.depthData)
        let visionMetadata = VisionMetadataExtractor.extract(from: encodedBytes)

        let metadata = CaptureMetadata(
            deviceModel: DeviceIdentity.hardwareModelIdentifier(),
            osVersion: ProcessInfo.processInfo.operatingSystemVersionString,
            cameraPosition: runtime.cameraPosition,
            orientation: .unknown,
            pitchDegrees: motionSnapshot?.pitchDegrees ?? 0,
            rollDegrees: motionSnapshot?.rollDegrees ?? 0,
            focalLengthMM: nil,
            lensHint: LensHintResolver.resolve(for: runtime.camera.deviceType),
            depthAvailable: depthAvailable,
            depthQuality: depthQuality,
            lidarAvailable: runtime.lidarAvailable,
            barcodePayload: visionMetadata.barcodePayload,
            barcodePayloadSafe: visionMetadata.barcodePayloadSafe,
            ocrTextSnippets: visionMetadata.ocrTextSnippets,
            referenceObjectHint: referenceObjectHint,
            captureTimestamp: TimestampFormatter.iso8601(from: capturedPhoto.captureTimestamp)
        )

        return CaptureDraft(
            requestID: RequestIDFactory.newID(prefix: "ios-camera"),
            userID: defaultUserID,
            captureSourceMode: .camera,
            imageIdentity: imageIdentity,
            captureMetadata: metadata,
            encodedImageBytes: encodedBytes
        )
#endif
    }

    private func ensureCameraAccess() async throws {
        let status = AVCaptureDevice.authorizationStatus(for: .video)
        switch status {
        case .authorized:
            return
        case .notDetermined:
            let granted = await withCheckedContinuation { continuation in
                AVCaptureDevice.requestAccess(for: .video) { granted in
                    continuation.resume(returning: granted)
                }
            }
            if !granted {
                throw CaptureServiceError.cameraPermissionDenied
            }
        case .denied, .restricted:
            throw CaptureServiceError.cameraPermissionDenied
        @unknown default:
            throw CaptureServiceError.cameraPermissionDenied
        }
    }

    private func buildCameraRuntime() async throws -> CameraRuntime {
        try await withCheckedThrowingContinuation { [weak self] continuation in
            guard let self else {
                continuation.resume(throwing: CaptureServiceError.captureServiceReleased)
                return
            }

            sessionQueue.async { [weak self] in
                guard self != nil else {
                    continuation.resume(throwing: CaptureServiceError.captureServiceReleased)
                    return
                }

                do {
                    guard let camera = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back)
                        ?? AVCaptureDevice.default(for: .video)
                    else {
                        throw CaptureServiceError.cameraUnavailable
                    }

                    let input = try AVCaptureDeviceInput(device: camera)
                    let output = AVCapturePhotoOutput()

                    let session = AVCaptureSession()
                    session.beginConfiguration()
                    if session.canSetSessionPreset(.photo) {
                        session.sessionPreset = .photo
                    }

                    guard session.canAddInput(input), session.canAddOutput(output) else {
                        session.commitConfiguration()
                        throw CaptureServiceError.cameraConfigurationFailed
                    }

                    session.addInput(input)
                    session.addOutput(output)

                    if output.isDepthDataDeliverySupported {
                        output.isDepthDataDeliveryEnabled = true
                    }

                    session.commitConfiguration()

                    let runtime = CameraRuntime(
                        session: session,
                        photoOutput: output,
                        camera: camera,
                        cameraPosition: CameraPosition.fromAVPosition(camera.position),
                        lidarAvailable: DeviceCapabilities.hasLiDARCamera()
                    )
                    continuation.resume(returning: runtime)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    private func startSession(_ session: AVCaptureSession) async throws {
        try await withCheckedThrowingContinuation {
            [weak self] (continuation: CheckedContinuation<Void, Error>) in
            guard let self else {
                continuation.resume(throwing: CaptureServiceError.captureServiceReleased)
                return
            }

            sessionQueue.async { [weak self] in
                guard self != nil else {
                    continuation.resume(throwing: CaptureServiceError.captureServiceReleased)
                    return
                }

                if !session.isRunning {
                    session.startRunning()
                }
                continuation.resume(returning: ())
            }
        }
    }

    private func stopSession(_ session: AVCaptureSession) async {
        await withCheckedContinuation { [weak self] continuation in
            guard let self else {
                continuation.resume(returning: ())
                return
            }

            sessionQueue.async { [weak self] in
                guard self != nil else {
                    continuation.resume(returning: ())
                    return
                }

                if session.isRunning {
                    session.stopRunning()
                }
                continuation.resume(returning: ())
            }
        }
    }

    private func capturePhoto(with photoOutput: AVCapturePhotoOutput, motionSampler: MotionSampler) async throws -> CapturedPhoto {
        let settings = AVCapturePhotoSettings()
        if photoOutput.isDepthDataDeliverySupported {
            settings.isDepthDataDeliveryEnabled = true
        }

        let suggestedFileTypeRawValue = settings.processedFileType?.rawValue
        let captureTimestamp = Date()
        let motionSnapshot = motionSampler.snapshot()

        let photo: AVCapturePhoto = try await withCheckedThrowingContinuation {
            [weak self] (continuation: CheckedContinuation<AVCapturePhoto, Error>) in
            guard let self else {
                continuation.resume(throwing: CaptureServiceError.captureServiceReleased)
                return
            }

            continuationLock.lock()
            let hasPendingCapture = pendingContinuation != nil
            if !hasPendingCapture {
                pendingContinuation = continuation
            }
            continuationLock.unlock()

            if hasPendingCapture {
                continuation.resume(throwing: CaptureServiceError.captureInProgress)
                return
            }

            sessionQueue.async { [weak self] in
                guard let self else {
                    continuation.resume(throwing: CaptureServiceError.captureServiceReleased)
                    return
                }

                photoOutput.capturePhoto(with: settings, delegate: self)
            }
        }

        return CapturedPhoto(
            photo: photo,
            suggestedFileTypeRawValue: suggestedFileTypeRawValue,
            captureTimestamp: captureTimestamp,
            motionSnapshot: motionSnapshot
        )
    }

    private func extractEncodedBytes(from photo: AVCapturePhoto) throws -> Data {
        guard let encodedData = photo.fileDataRepresentation() else {
            throw CaptureServiceError.captureFailed
        }
        return encodedData
    }

    private func finishPendingCapture(with result: Result<AVCapturePhoto, Error>) {
        continuationLock.lock()
        let continuation = pendingContinuation
        pendingContinuation = nil
        continuationLock.unlock()

        continuation?.resume(with: result)
    }
}

extension AVFoundationCaptureService: AVCapturePhotoCaptureDelegate {
    func photoOutput(_ output: AVCapturePhotoOutput, didFinishProcessingPhoto photo: AVCapturePhoto, error: Error?) {
        if let error {
            finishPendingCapture(with: .failure(error))
            return
        }

        finishPendingCapture(with: .success(photo))
    }

    func photoOutput(_ output: AVCapturePhotoOutput, didFinishCaptureFor resolvedSettings: AVCaptureResolvedPhotoSettings, error: Error?) {
        if let error {
            finishPendingCapture(with: .failure(error))
        }
    }
}

private struct MotionSnapshot {
    let pitchDegrees: Double
    let rollDegrees: Double
}

private final class MotionSampler {
    private let motionManager = CMMotionManager()

    func start() {
        guard motionManager.isDeviceMotionAvailable else {
            return
        }

        motionManager.deviceMotionUpdateInterval = 1.0 / 30.0
        motionManager.startDeviceMotionUpdates(using: .xArbitraryCorrectedZVertical)
    }

    func stop() {
        if motionManager.isDeviceMotionActive {
            motionManager.stopDeviceMotionUpdates()
        }
    }

    func snapshot() -> MotionSnapshot? {
        guard let motion = motionManager.deviceMotion else {
            return nil
        }

        let pitchDegrees = sanitizeAngleDegrees(motion.attitude.pitch * 180.0 / Double.pi)
        let rollDegrees = sanitizeAngleDegrees(motion.attitude.roll * 180.0 / Double.pi)
        return MotionSnapshot(pitchDegrees: pitchDegrees, rollDegrees: rollDegrees)
    }

    private func sanitizeAngleDegrees(_ value: Double) -> Double {
        guard value.isFinite else {
            return 0
        }

        return max(-180, min(180, value))
    }
}

private struct VisionCaptureMetadata {
    let barcodePayload: String?
    let barcodePayloadSafe: Bool
    let ocrTextSnippets: [String]
}

private enum VisionMetadataExtractor {
    private static let maxOCRSnippetCount = 6
    private static let maxSnippetLength = 48
    private static let supportedBarcodeSymbologies: [VNBarcodeSymbology] = [
        .ean8, .ean13, .upce
    ]
    private static let blockedBarcodePayloadPrefixes: [String] = [
        "mailto:", "tel:", "sms:", "smsto:", "mms:", "mmsto:",
        "geo:", "wifi:", "http://", "https://", "otpauth:"
    ]
    private static let blockedBarcodePayloadTokens: [String] = [
        "begin:vcard", "mecard:"
    ]

    private static let foodPackageKeywords: [String] = [
        "nutrition", "ingredient", "ingredients", "serving", "calorie", "calories", "kcal",
        "protein", "carb", "carbs", "fat", "fiber", "sugar", "sodium", "net wt", "energy",
        "portion", "grams", "ounces", "ml", "kg", "mg"
    ]

    static func extract(from encodedBytes: Data) -> VisionCaptureMetadata {
        guard let image = decodedImage(from: encodedBytes) else {
            return VisionCaptureMetadata(barcodePayload: nil, barcodePayloadSafe: false, ocrTextSnippets: [])
        }

        let barcodeRequest = VNDetectBarcodesRequest()
        barcodeRequest.symbologies = supportedBarcodeSymbologies
        let textRequest = VNRecognizeTextRequest()
        textRequest.recognitionLevel = .accurate
        textRequest.usesLanguageCorrection = false
        textRequest.recognitionLanguages = ["en-US"]

        do {
            let cgImage = image.cgImage
            if image.orientation == .up {
                let handler = VNImageRequestHandler(cgImage: cgImage, orientation: .up, options: [:])
                try handler.perform([barcodeRequest, textRequest])
            } else {
                let handler = VNImageRequestHandler(cgImage: cgImage, orientation: image.orientation, options: [:])
                try handler.perform([barcodeRequest, textRequest])
            }
        } catch {
            return VisionCaptureMetadata(barcodePayload: nil, barcodePayloadSafe: false, ocrTextSnippets: [])
        }

        let barcodeObservations = barcodeRequest.results ?? []
        let barcodeResult = firstSafeBarcodePayload(in: barcodeObservations)

        let rawTextCandidates = (textRequest.results ?? []).compactMap { observation in
            observation.topCandidates(1).first?.string
        }
        let snippets = shortFoodPackageSnippets(from: rawTextCandidates)

        return VisionCaptureMetadata(
            barcodePayload: barcodeResult.payload,
            barcodePayloadSafe: barcodeResult.safe,
            ocrTextSnippets: snippets
        )
    }

    private static func decodedImage(from data: Data) -> (cgImage: CGImage, orientation: CGImagePropertyOrientation)? {
        guard let imageSource = CGImageSourceCreateWithData(data as CFData, nil),
              let image = CGImageSourceCreateImageAtIndex(imageSource, 0, nil)
        else {
            return nil
        }

        let properties = CGImageSourceCopyPropertiesAtIndex(imageSource, 0, nil) as? [CFString: Any]
        let orientation = imageOrientation(from: properties)
        return (image, orientation)
    }

    private static func imageOrientation(from properties: [CFString: Any]?) -> CGImagePropertyOrientation {
        if let rawValue = properties?[kCGImagePropertyOrientation] as? UInt32,
           let orientation = CGImagePropertyOrientation(rawValue: rawValue) {
            return orientation
        }

        if let rawNumber = properties?[kCGImagePropertyOrientation] as? NSNumber,
           let orientation = CGImagePropertyOrientation(rawValue: rawNumber.uint32Value) {
            return orientation
        }

        return .up
    }

    private static func firstSafeBarcodePayload(in observations: [VNBarcodeObservation]) -> (payload: String?, safe: Bool) {
        for observation in observations {
            guard supportedBarcodeSymbologies.contains(observation.symbology),
                  let payload = observation.payloadStringValue?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !payload.isEmpty
            else {
                continue
            }

            if isSafeBarcodePayload(payload) {
                return (payload, true)
            }
        }

        return (nil, false)
    }

    private static func isSafeBarcodePayload(_ payload: String) -> Bool {
        let trimmed = payload.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed.count <= 64 else {
            return false
        }

        if looksLikeNonProductBarcodePayload(trimmed) {
            return false
        }

        if looksSensitive(trimmed) {
            return false
        }

        let allowedScalars = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-._:/+()"))
        for scalar in trimmed.unicodeScalars where !allowedScalars.contains(scalar) {
            return false
        }

        let digitsOnly = trimmed.filter(\.isNumber)
        if digitsOnly.count > 20 {
            return false
        }

        return true
    }

    private static func looksLikeNonProductBarcodePayload(_ payload: String) -> Bool {
        let lowercased = payload.lowercased()
        if blockedBarcodePayloadPrefixes.contains(where: { lowercased.hasPrefix($0) }) {
            return true
        }

        if blockedBarcodePayloadTokens.contains(where: { lowercased.contains($0) }) {
            return true
        }

        return false
    }

    private static func shortFoodPackageSnippets(from rawCandidates: [String]) -> [String] {
        var snippets: [String] = []
        var seen: Set<String> = []

        for candidate in rawCandidates {
            let lines = candidate.split(whereSeparator: \.isNewline).map(String.init)
            for line in lines {
                guard let normalized = normalizeOCRLine(line) else {
                    continue
                }

                let signature = normalized.lowercased()
                if seen.contains(signature) {
                    continue
                }

                seen.insert(signature)
                snippets.append(normalized)

                if snippets.count >= maxOCRSnippetCount {
                    return snippets
                }
            }
        }

        return snippets
    }

    private static func normalizeOCRLine(_ text: String) -> String? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return nil
        }

        let collapsed = collapseWhitespace(trimmed)
        guard collapsed.count >= 2 else {
            return nil
        }

        let shortened = collapsed.count > maxSnippetLength
            ? String(collapsed.prefix(maxSnippetLength))
            : collapsed

        guard !looksSensitive(shortened) else {
            return nil
        }

        guard isFoodOrPackageOriented(shortened) else {
            return nil
        }

        return shortened
    }

    private static func collapseWhitespace(_ text: String) -> String {
        text
            .components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    private static func looksSensitive(_ text: String) -> Bool {
        let lowercased = text.lowercased()

        if lowercased.contains("@") || lowercased.contains("http://") || lowercased.contains("https://") {
            return true
        }

        let digitsOnly = text.filter(\.isNumber)
        if digitsOnly.count >= 10,
           (text.contains("+") || text.contains("(") || text.contains(")") || text.contains("-") || text.contains(" ")) {
            return true
        }

        let compact = text.replacingOccurrences(of: " ", with: "")
        if compact.count >= 16,
           compact.range(of: "^[A-Za-z0-9_./:-]+$", options: .regularExpression) != nil {
            return true
        }

        return false
    }

    private static func isFoodOrPackageOriented(_ text: String) -> Bool {
        let lowercased = text.lowercased()

        if foodPackageKeywords.contains(where: { containsKeyword(lowercased, keyword: $0) }) {
            return true
        }

        if lowercased.range(of: "\\b\\d{1,4}\\s?(kcal|cal|kj|g|mg|ml|oz|lb|l)\\b", options: .regularExpression) != nil {
            return true
        }

        if lowercased.range(of: "\\b(total|per|serving|servings|ingredients?|nutrition|energy|net)\\b", options: .regularExpression) != nil {
            return true
        }

        return false
    }

    private static func containsKeyword(_ text: String, keyword: String) -> Bool {
        let tokens = keyword
            .split(whereSeparator: \.isWhitespace)
            .map { NSRegularExpression.escapedPattern(for: String($0)) }
        guard !tokens.isEmpty else {
            return false
        }

        let pattern = "\\b" + tokens.joined(separator: "\\s+") + "\\b"
        return text.range(of: pattern, options: .regularExpression) != nil
    }
}

private enum DepthQualityEstimator {
    static func from(depthData: AVDepthData?) -> DepthQuality {
        guard let depthData else {
            return .none
        }

        let pixelBuffer = depthData.depthDataMap
        let width = CVPixelBufferGetWidth(pixelBuffer)
        let height = CVPixelBufferGetHeight(pixelBuffer)

        guard width > 0, height > 0 else {
            return .unknown
        }

        let shorterSide = min(width, height)
        if shorterSide >= 960 {
            return .high
        }

        if shorterSide >= 480 {
            return .medium
        }

        return .low
    }
}

private enum LensHintResolver {
    static func resolve(for deviceType: AVCaptureDevice.DeviceType) -> String {
        switch deviceType {
        case .builtInUltraWideCamera:
            return "ultra_wide"
        case .builtInTelephotoCamera:
            return "telephoto"
        case .builtInDualCamera, .builtInDualWideCamera, .builtInTripleCamera:
            return "multi"
        case .builtInWideAngleCamera:
            return "standard"
        default:
            return "standard"
        }
    }
}

private enum DeviceCapabilities {
    static func hasLiDARCamera() -> Bool {
        let discovery = AVCaptureDevice.DiscoverySession(
            deviceTypes: [.builtInLiDARDepthCamera],
            mediaType: .video,
            position: .back
        )
        return !discovery.devices.isEmpty
    }
}

private enum ImageIdentityExtractor {
    static func build(from encodedBytes: Data, suggestedFileTypeRawValue: String?) throws -> ImageIdentity {
        guard let dimensions = pixelDimensions(from: encodedBytes) else {
            throw CaptureServiceError.invalidImageData
        }

        return ImageIdentity(
            imageSHA256: sha256Hex(of: encodedBytes),
            imageFormat: normalizedFormat(fileTypeRawValue: suggestedFileTypeRawValue, imageBytes: encodedBytes),
            widthPX: dimensions.width,
            heightPX: dimensions.height,
            byteSize: encodedBytes.count
        )
    }

    private static func sha256Hex(of data: Data) -> String {
        let digest = SHA256.hash(data: data)
        return digest.map { String(format: "%02x", $0) }.joined()
    }

    private static func pixelDimensions(from data: Data) -> (width: Int, height: Int)? {
        guard let imageSource = CGImageSourceCreateWithData(data as CFData, nil),
              let properties = CGImageSourceCopyPropertiesAtIndex(imageSource, 0, nil) as? [CFString: Any]
        else {
            return nil
        }

        let widthNumber = properties[kCGImagePropertyPixelWidth] as? NSNumber
        let heightNumber = properties[kCGImagePropertyPixelHeight] as? NSNumber

        guard let width = widthNumber?.intValue,
              let height = heightNumber?.intValue,
              width > 0,
              height > 0
        else {
            return nil
        }

        return (width, height)
    }

    private static func normalizedFormat(fileTypeRawValue: String?, imageBytes: Data) -> String {
        if let fileTypeRawValue {
            let raw = fileTypeRawValue.lowercased()
            if raw.contains("heic") { return "heic" }
            if raw.contains("heif") { return "heif" }
            if raw.contains("jpeg") || raw.contains("jpg") { return "jpeg" }
            if raw.contains("png") { return "png" }
            if raw.contains("webp") { return "webp" }
        }

        return sniffFromMagicNumber(imageBytes)
    }

    private static func sniffFromMagicNumber(_ data: Data) -> String {
        let bytes = [UInt8](data.prefix(16))
        if bytes.count >= 2 && bytes[0] == 0xFF && bytes[1] == 0xD8 {
            return "jpeg"
        }

        if bytes.count >= 4,
           bytes[0] == 0x89,
           bytes[1] == 0x50,
           bytes[2] == 0x4E,
           bytes[3] == 0x47 {
            return "png"
        }

        if bytes.count >= 12,
           String(bytes: bytes[8...11], encoding: .ascii) == "WEBP" {
            return "webp"
        }

        if data.count >= 12 {
            let header = String(decoding: data.prefix(12), as: UTF8.self).lowercased()
            if header.contains("ftypheic") { return "heic" }
            if header.contains("ftypheif") { return "heif" }
        }

        return "jpeg"
    }
}

private enum SampleCaptureFactory {
    static func makeDraft(userID: String, referenceObjectHint: String?) -> CaptureDraft {
        let encodedBytes = sampleImageBytes()
        let imageIdentity: ImageIdentity

        do {
            imageIdentity = try ImageIdentityExtractor.build(
                from: encodedBytes,
                suggestedFileTypeRawValue: nil
            )
        } catch {
            imageIdentity = ImageIdentity(
                imageSHA256: String(repeating: "0", count: 64),
                imageFormat: "png",
                widthPX: 1,
                heightPX: 1,
                byteSize: encodedBytes.count
            )
        }

        let visionMetadata = VisionMetadataExtractor.extract(from: encodedBytes)

        let metadata = CaptureMetadata(
            deviceModel: "sample-fallback",
            osVersion: ProcessInfo.processInfo.operatingSystemVersionString,
            cameraPosition: .unknown,
            orientation: .unknown,
            pitchDegrees: 0,
            rollDegrees: 0,
            focalLengthMM: nil,
            lensHint: "sample",
            depthAvailable: false,
            depthQuality: .none,
            lidarAvailable: false,
            barcodePayload: visionMetadata.barcodePayload,
            barcodePayloadSafe: visionMetadata.barcodePayloadSafe,
            ocrTextSnippets: visionMetadata.ocrTextSnippets,
            referenceObjectHint: referenceObjectHint,
            captureTimestamp: TimestampFormatter.iso8601Now()
        )

        return CaptureDraft(
            requestID: RequestIDFactory.newID(prefix: "ios-sample"),
            userID: userID,
            captureSourceMode: .sampleFallback,
            imageIdentity: imageIdentity,
            captureMetadata: metadata,
            encodedImageBytes: encodedBytes
        )
    }

    private static func sampleImageBytes() -> Data {
        let png1x1Base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+0R8AAAAASUVORK5CYII="
        if let decoded = Data(base64Encoded: png1x1Base64) {
            return decoded
        }

        return Data([0x89, 0x50, 0x4E, 0x47])
    }
}

private enum RequestIDFactory {
    static func newID(prefix: String) -> String {
        "\(prefix)-\(UUID().uuidString.lowercased())"
    }
}

private enum TimestampFormatter {
    private static let formatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    static func iso8601Now() -> String {
        iso8601(from: Date())
    }

    static func iso8601(from date: Date) -> String {
        formatter.string(from: date)
    }
}

private enum DeviceIdentity {
    static func hardwareModelIdentifier() -> String {
        var systemInfo = utsname()
        uname(&systemInfo)

        return withUnsafePointer(to: &systemInfo.machine) { pointer in
            pointer.withMemoryRebound(to: CChar.self, capacity: 1) { machinePointer in
                String(cString: machinePointer)
            }
        }
    }
}

private extension CameraPosition {
    static func fromAVPosition(_ position: AVCaptureDevice.Position) -> CameraPosition {
        switch position {
        case .front:
            return .front
        case .back:
            return .back
        default:
            return .unknown
        }
    }
}
