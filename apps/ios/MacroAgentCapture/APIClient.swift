import Foundation

protocol MacroAgentAPIClient {
    func healthCheck() async throws -> HealthResponse
    func analyzePhoto(_ requestEnvelope: AnalyzePhotoRequestEnvelope) async throws -> AnalyzePhotoResponse
    func fetchMealHistory(
        userID: String,
        localDate: String?,
        includeInactive: Bool,
        limit: Int
    ) async throws -> UserMealHistoryResponse
    func fetchDailyTotals(
        userID: String,
        localDate: String
    ) async throws -> UserDailyNutritionTotalsResponse
    func prepareHealthKitExport(
        userID: String,
        localDate: String
    ) async throws -> HealthKitExportPreparationResponse
}

struct LocalServerConfiguration: Equatable {
    static let defaultBaseURLString = "http://127.0.0.1:8765"

    var baseURLString: String

    init(baseURLString: String = LocalServerConfiguration.defaultBaseURLString) {
        self.baseURLString = baseURLString.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var baseURL: URL? {
        URL(string: baseURLString)
    }

    func endpoint(path: String) -> URL? {
        guard var components = baseURL.flatMap({ URLComponents(url: $0, resolvingAgainstBaseURL: false) }) else {
            return nil
        }

        let normalizedPath = path.hasPrefix("/") ? path : "/\(path)"
        let trimmedBasePath = components.path.hasSuffix("/") ? String(components.path.dropLast()) : components.path
        components.path = trimmedBasePath + normalizedPath
        return components.url
    }
}

enum APIClientError: LocalizedError {
    case invalidBaseURL(String)
    case unexpectedStatusCode(Int)
    case encodingFailed
    case invalidResponse(String)

    var errorDescription: String? {
        switch self {
        case .invalidBaseURL(let raw):
            return "Invalid server URL: \(raw)"
        case .unexpectedStatusCode(let code):
            return "Server returned HTTP \(code)."
        case .encodingFailed:
            return "Unable to encode request payload."
        case .invalidResponse(let detail):
            return "Invalid response payload: \(detail)"
        }
    }
}

struct LocalServerAPIClient: MacroAgentAPIClient {
    private let configuration: LocalServerConfiguration
    private let urlSession: URLSession
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    init(
        configuration: LocalServerConfiguration,
        urlSession: URLSession = .shared,
        encoder: JSONEncoder = JSONEncoder(),
        decoder: JSONDecoder = JSONDecoder()
    ) {
        self.configuration = configuration
        self.urlSession = urlSession
        self.encoder = encoder
        self.decoder = decoder
    }

    func healthCheck() async throws -> HealthResponse {
        var request = URLRequest(url: try makeURL(path: "/health"))
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await urlSession.data(for: request)
        try validate(response: response)
        return try decoder.decode(HealthResponse.self, from: data)
    }

    func analyzePhoto(_ requestEnvelope: AnalyzePhotoRequestEnvelope) async throws -> AnalyzePhotoResponse {
        var request = URLRequest(url: try makeURL(path: "/v1/meals/analyze-photo"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        guard let body = try? encoder.encode(requestEnvelope) else {
            throw APIClientError.encodingFailed
        }
        request.httpBody = body

        let (data, response) = try await urlSession.data(for: request)
        try validate(response: response)
        do {
            return try decoder.decode(AnalyzePhotoResponse.self, from: data)
        } catch {
            throw APIClientError.invalidResponse("response body does not match AnalyzePhotoResponse")
        }
    }

    func fetchMealHistory(
        userID: String,
        localDate: String?,
        includeInactive: Bool,
        limit: Int
    ) async throws -> UserMealHistoryResponse {
        var queryItems = [
            URLQueryItem(name: "user_id", value: userID),
            URLQueryItem(name: "include_inactive", value: includeInactive ? "true" : "false"),
            URLQueryItem(name: "limit", value: String(limit)),
        ]
        if let localDate {
            queryItems.append(URLQueryItem(name: "local_date", value: localDate))
        }

        var request = URLRequest(
            url: try makeURL(path: "/v1/users/history", queryItems: queryItems)
        )
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await urlSession.data(for: request)
        try validate(response: response)
        do {
            return try decoder.decode(UserMealHistoryResponse.self, from: data)
        } catch {
            throw APIClientError.invalidResponse("response body does not match UserMealHistoryResponse")
        }
    }

    func fetchDailyTotals(
        userID: String,
        localDate: String
    ) async throws -> UserDailyNutritionTotalsResponse {
        let queryItems = [
            URLQueryItem(name: "user_id", value: userID),
            URLQueryItem(name: "local_date", value: localDate),
        ]
        var request = URLRequest(
            url: try makeURL(path: "/v1/users/daily-totals", queryItems: queryItems)
        )
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await urlSession.data(for: request)
        try validate(response: response)
        do {
            return try decoder.decode(UserDailyNutritionTotalsResponse.self, from: data)
        } catch {
            throw APIClientError.invalidResponse(
                "response body does not match UserDailyNutritionTotalsResponse"
            )
        }
    }

    func prepareHealthKitExport(
        userID: String,
        localDate: String
    ) async throws -> HealthKitExportPreparationResponse {
        let queryItems = [
            URLQueryItem(name: "user_id", value: userID),
            URLQueryItem(name: "local_date", value: localDate),
        ]
        var request = URLRequest(
            url: try makeURL(path: "/v1/users/healthkit-export-prep", queryItems: queryItems)
        )
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await urlSession.data(for: request)
        try validate(response: response)
        do {
            return try decoder.decode(HealthKitExportPreparationResponse.self, from: data)
        } catch {
            throw APIClientError.invalidResponse(
                "response body does not match HealthKitExportPreparationResponse"
            )
        }
    }

    private func makeURL(path: String, queryItems: [URLQueryItem] = []) throws -> URL {
        guard let url = configuration.endpoint(path: path) else {
            throw APIClientError.invalidBaseURL(configuration.baseURLString)
        }
        guard !queryItems.isEmpty else {
            return url
        }
        guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            throw APIClientError.invalidBaseURL(configuration.baseURLString)
        }
        components.queryItems = queryItems
        guard let withQuery = components.url else {
            throw APIClientError.invalidBaseURL(configuration.baseURLString)
        }
        return withQuery
    }

    private func validate(response: URLResponse) throws {
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIClientError.unexpectedStatusCode(-1)
        }
        guard (200...299).contains(httpResponse.statusCode) else {
            throw APIClientError.unexpectedStatusCode(httpResponse.statusCode)
        }
    }
}
