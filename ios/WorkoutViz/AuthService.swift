import Foundation
import Combine

/// Manages the permanent per-device Bearer token.
///
/// Token lifecycle:
///   1. On init: restore token from Keychain.
///   2. First launch (no token in Keychain): POST /api/auth/device → store
///      the returned token. No user interaction, no login screen.
///   3. Every native API call (sync, delete, export) goes through
///      authorizedRequest().
///   4. On 401 from WebView bridge: clear token → registerDeviceIfNeeded()
///      re-provisions a fresh device identity next time it runs.
///   5. Delete-all-data: server purge, then forgetDevice() clears local state.
@MainActor
final class AuthService: ObservableObject {
    static let shared = AuthService()

    private let tokenKey = "session_jwt"

    @Published private(set) var sessionToken: String? {
        didSet {
            if let t = sessionToken {
                KeychainHelper.save(t, key: tokenKey)
            } else {
                KeychainHelper.delete(key: tokenKey)
            }
        }
    }

    var isAuthenticated: Bool { sessionToken != nil }

    private var registrationTask: Task<Void, Never>?

    private init() {
        sessionToken = KeychainHelper.load(key: tokenKey)
        // Idempotent migration: re-save so an existing token picks up the
        // AfterFirstUnlock accessibility (widget/background reads need it).
        // Property observers don't fire during init, so this is explicit.
        if let t = sessionToken {
            KeychainHelper.save(t, key: tokenKey)
        }
    }

    // MARK: - Authenticated requests

    /// Single place that builds Bearer-authenticated requests.  Every native
    /// API call (sync, delete, export) must go through this so an auth-scheme
    /// change happens in exactly one spot.
    func authorizedRequest(url: URL, method: String = "GET",
                           timeout: TimeInterval = 30) -> URLRequest {
        var req = URLRequest(url: url)
        req.httpMethod = method
        if let token = sessionToken {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        req.timeoutInterval = timeout
        return req
    }

    // MARK: - Device registration

    /// Called on every app launch/foreground. No-ops if a token already
    /// exists. Safe to call concurrently — `.task` and the foreground
    /// notification handler both call this at launch; without coalescing,
    /// both would see `sessionToken == nil` before either network call
    /// completes and register two separate devices.
    func registerDeviceIfNeeded() async {
        guard sessionToken == nil else { return }

        if let existing = registrationTask {
            await existing.value
            return
        }

        let task = Task { await self.performRegistration() }
        registrationTask = task
        await task.value
        registrationTask = nil
    }

    private func performRegistration() async {
        guard let url = URL(string: "\(Config.backendURL)/api/auth/device") else { return }

        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.timeoutInterval = 30

        do {
            let (data, response) = try await URLSession.shared.data(for: req)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                print("[AuthService] device registration failed")
                return
            }
            struct Resp: Decodable { let device_token: String }
            sessionToken = try JSONDecoder().decode(Resp.self, from: data).device_token
        } catch {
            print("[AuthService] device registration error: \(error)")
        }
    }

    // MARK: - Forget device (after Delete All Data, or an unrecoverable 401
    // from the WebView bridge). registerDeviceIfNeeded() re-provisions a
    // fresh device identity the next time it runs.

    func forgetDevice() {
        sessionToken = nil
        KeychainHelper.delete(key: "hk_anchor")
        UserDefaults.standard.removeObject(forKey: "lastSyncDate")
        UserDefaults.standard.removeObject(forKey: "syncedSourceIds")
        UserDefaults.standard.removeObject(forKey: "metricsLastSyncDate")
    }
}
