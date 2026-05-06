import AVFoundation
import CryptoKit
import Foundation
import ImageIO

protocol CaptureService {
    func initialDraft() -> CaptureDraft
    func prepareDraft(mode: CaptureSourceMode) async throws -> CaptureDraft
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

    func initialDraft() -> CaptureDraft {
        SampleCaptureFactory.makeDraft(userID: defaultUserID)
    }

    func prepareDraft(mode: CaptureSourceMode) async throws -> CaptureDraft {
        SampleCaptureFactory.makeDraft(userID: defaultUserID)
    }
}

final class AVFoundationCaptureService: NSObject, CaptureService {
    private struct CameraRuntime {
        let session: AVCaptureSession
        let photoOutput: AVCapturePhotoOutput
        let cameraPosition: CameraPosition
    }

    private struct CapturedPhoto {
        let photo: AVCapturePhoto
        let suggestedFileTypeRawValue: String?
    }

    private let defaultUserID: String
    private let sessionQueue = DispatchQueue(label: "com.macroagent.capture.session")
    private let continuationLock = NSLock()
    private var pendingContinuation: CheckedContinuation<AVCapturePhoto, Error>?

    init(defaultUserID: String = "ios-smoke-user-0001") {
        self.defaultUserID = defaultUserID
    }

    func initialDraft() -> CaptureDraft {
        SampleCaptureFactory.makeDraft(userID: defaultUserID)
    }

    func prepareDraft(mode: CaptureSourceMode) async throws -> CaptureDraft {
        switch mode {
        case .sampleFallback:
            return SampleCaptureFactory.makeDraft(userID: defaultUserID)
        case .camera:
            return try await prepareCameraDraft()
        }
    }

    private func prepareCameraDraft() async throws -> CaptureDraft {
#if targetEnvironment(simulator)
        throw CaptureServiceError.simulatorRequiresSampleMode
#else
        try await ensureCameraAccess()
        let runtime = try await buildCameraRuntime()
        try await startSession(runtime.session)

        let capturedPhoto: CapturedPhoto
        do {
            capturedPhoto = try await capturePhoto(with: runtime.photoOutput)
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

        let metadata = CaptureMetadata(
            deviceModel: DeviceIdentity.hardwareModelIdentifier(),
            osVersion: ProcessInfo.processInfo.operatingSystemVersionString,
            cameraPosition: runtime.cameraPosition,
            orientation: .unknown,
            pitchDegrees: 0,
            rollDegrees: 0,
            focalLengthMM: nil,
            lensHint: "standard",
            depthAvailable: false,
            depthQuality: .none,
            lidarAvailable: false,
            barcodePayload: nil,
            barcodePayloadSafe: false,
            ocrTextSnippets: [],
            referenceObjectHint: nil,
            captureTimestamp: TimestampFormatter.iso8601Now()
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
                guard let self else {
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
                    session.commitConfiguration()

                    let runtime = CameraRuntime(
                        session: session,
                        photoOutput: output,
                        cameraPosition: CameraPosition.fromAVPosition(camera.position)
                    )
                    continuation.resume(returning: runtime)
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }

    private func startSession(_ session: AVCaptureSession) async throws {
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

    private func capturePhoto(with photoOutput: AVCapturePhotoOutput) async throws -> CapturedPhoto {
        let settings = AVCapturePhotoSettings()
        let suggestedFileTypeRawValue = settings.processedFileType?.rawValue

        let photo = try await withCheckedThrowingContinuation { [weak self] continuation in
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

        return CapturedPhoto(photo: photo, suggestedFileTypeRawValue: suggestedFileTypeRawValue)
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
    static func makeDraft(userID: String) -> CaptureDraft {
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
            barcodePayload: nil,
            barcodePayloadSafe: false,
            ocrTextSnippets: [],
            referenceObjectHint: "sample_fallback",
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
        formatter.string(from: Date())
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
