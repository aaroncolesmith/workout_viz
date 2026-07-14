import SwiftUI
import WebKit

/// WKWebView wrapper.
///
/// JWT injection (IOS-2): A WKUserScript runs at document-start and writes the
/// session token into localStorage so the React app can attach it as
/// `Authorization: Bearer` on every API call.  The script also installs
/// `window.WorkoutVizNative` so the web app can call back into native code.
///
/// 401 handler: the React app posts `{ cmd: "unauthorized" }` via the bridge
/// whenever it receives a 401 from the backend, which triggers a sign-out and
/// returns the user to the auth gate.
struct WebView: UIViewRepresentable {
    let url: URL
    @EnvironmentObject var syncEngine: SyncEngine
    @EnvironmentObject var authService: AuthService
    @EnvironmentObject var notificationManager: NotificationManager

    func makeCoordinator() -> Coordinator {
        Coordinator(syncEngine: syncEngine, authService: authService)
    }

    func makeUIView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        cfg.allowsInlineMediaPlayback = true

        let userContent = WKUserContentController()
        userContent.add(context.coordinator, name: "wv")
        cfg.userContentController = userContent

        Self.installUserScripts(on: userContent, token: authService.sessionToken)
        context.coordinator.lastInjectedToken = authService.sessionToken

        let wv = WKWebView(frame: .zero, configuration: cfg)
        wv.allowsBackForwardNavigationGestures = true
        wv.scrollView.contentInsetAdjustmentBehavior = .automatic
        wv.scrollView.alwaysBounceHorizontal = false
        wv.scrollView.bounces = true
        wv.scrollView.showsHorizontalScrollIndicator = false
        return wv
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        if webView.url == nil {
            webView.load(URLRequest(url: url))
        }
        // Token rotation (refresh revokes the old jti): push the current token
        // into the live page AND the document-start script, otherwise the web
        // layer keeps a revoked token, gets a 401, and force-signs-out.
        context.coordinator.syncToken(authService.sessionToken, in: webView)

        // Notification deep link (CMP-5): navigate to the tapped workout.
        if let path = notificationManager.pendingDeepLink,
           path != context.coordinator.lastHandledDeepLink,
           let dest = URL(string: Config.backendURL + path) {
            context.coordinator.lastHandledDeepLink = path
            webView.load(URLRequest(url: dest))
            DispatchQueue.main.async {
                notificationManager.pendingDeepLink = nil
            }
        }
    }

    // MARK: - Scripts

    fileprivate static func installUserScripts(on controller: WKUserContentController, token: String?) {
        // Write the JWT into localStorage before any JS runs, so api.js picks it
        // up on the first fetch.  Safe to call with nil (clears the key).
        // Runs at document start for every navigation.
        controller.addUserScript(WKUserScript(
            source: Self.tokenScript(token),
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        ))

        // Native bridge: keeps existing backfill commands + account + 401 handler.
        let bridgeScript = """
        window.WorkoutVizNative = {
            backfill:      function() { window.webkit.messageHandlers.wv.postMessage({cmd:'backfill'}); },
            resetBackfill: function() { window.webkit.messageHandlers.wv.postMessage({cmd:'resetBackfill'}); },
            unauthorized:  function() { window.webkit.messageHandlers.wv.postMessage({cmd:'unauthorized'}); },
            openAccount:   function() { window.webkit.messageHandlers.wv.postMessage({cmd:'openAccount'}); },
            available: true
        };
        """
        controller.addUserScript(WKUserScript(
            source: bridgeScript,
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        ))
    }

    fileprivate static func tokenScript(_ token: String?) -> String {
        let tokenValue = token.map { "'\($0)'" } ?? "null"
        return """
        (function() {
            var t = \(tokenValue);
            if (t) { localStorage.setItem('volken_session_token', t); }
            else    { localStorage.removeItem('volken_session_token'); }
        })();
        """
    }

    // MARK: - Bridge delegate

    final class Coordinator: NSObject, WKScriptMessageHandler {
        let syncEngine: SyncEngine
        let authService: AuthService
        var lastInjectedToken: String?
        var lastHandledDeepLink: String?

        init(syncEngine: SyncEngine, authService: AuthService) {
            self.syncEngine = syncEngine
            self.authService = authService
        }

        /// Re-inject when the session token changes (e.g. after a refresh).
        /// Updates both the live page's localStorage and the document-start
        /// script used by future navigations.
        func syncToken(_ token: String?, in webView: WKWebView) {
            guard token != lastInjectedToken else { return }
            lastInjectedToken = token

            webView.evaluateJavaScript(WebView.tokenScript(token), completionHandler: nil)

            let controller = webView.configuration.userContentController
            controller.removeAllUserScripts()
            WebView.installUserScripts(on: controller, token: token)
        }

        func userContentController(
            _ userContentController: WKUserContentController,
            didReceive message: WKScriptMessage
        ) {
            guard let body = message.body as? [String: Any],
                  let cmd = body["cmd"] as? String else { return }
            switch cmd {
            case "backfill":
                Task { await syncEngine.performFullBackfill() }
            case "resetBackfill":
                syncEngine.resetBackfillProgress()
            case "unauthorized":
                authService.forgetDevice()
            case "openAccount":
                syncEngine.showingAccount = true
            default:
                break
            }
        }
    }
}

struct ContentView: View {
    @EnvironmentObject var syncEngine: SyncEngine
    @EnvironmentObject var authService: AuthService

    private var appURL: URL { URL(string: Config.backendURL)! }

    var body: some View {
        ZStack(alignment: .top) {
            WebView(url: appURL)
                .ignoresSafeArea()

            // Sync progress banner
            if syncEngine.isSyncing {
                HStack(spacing: 6) {
                    ProgressView().scaleEffect(0.7)
                    Text(syncEngine.syncProgress.isEmpty ? "Syncing…" : syncEngine.syncProgress)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 4)
                .background(.thinMaterial, in: Capsule())
                .padding(.top, 8)
                .allowsHitTesting(false)
            }

        }
        .task {
            await syncEngine.requestPermissionsIfNeeded()
        }
        .sheet(isPresented: $syncEngine.showingAccount) {
            AccountView()
                .environmentObject(authService)
        }
    }
}
