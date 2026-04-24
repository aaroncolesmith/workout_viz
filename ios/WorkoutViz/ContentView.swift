import SwiftUI
import WebKit

/// WKWebView wrapper with a JS bridge so the web app can trigger
/// native-only actions (e.g. HealthKit backfill).
struct WebView: UIViewRepresentable {
    let url: URL
    @EnvironmentObject var syncEngine: SyncEngine

    func makeCoordinator() -> Coordinator {
        Coordinator(syncEngine: syncEngine)
    }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true

        // Register a message handler so the web app can call:
        //   window.webkit.messageHandlers.wv.postMessage({ cmd: 'backfill' })
        let userContent = WKUserContentController()
        userContent.add(context.coordinator, name: "wv")
        config.userContentController = userContent

        // Inject a small convenience bridge so Settings JS doesn't have to
        // know about webkit.messageHandlers directly.
        let bridgeJS = """
        window.WorkoutVizNative = {
            backfill: function() { window.webkit.messageHandlers.wv.postMessage({cmd:'backfill'}); },
            resetBackfill: function() { window.webkit.messageHandlers.wv.postMessage({cmd:'resetBackfill'}); },
            available: true
        };
        """
        let script = WKUserScript(source: bridgeJS, injectionTime: .atDocumentStart, forMainFrameOnly: true)
        userContent.addUserScript(script)

        let wv = WKWebView(frame: .zero, configuration: config)
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
    }

    final class Coordinator: NSObject, WKScriptMessageHandler {
        let syncEngine: SyncEngine
        init(syncEngine: SyncEngine) { self.syncEngine = syncEngine }

        func userContentController(_ userContentController: WKUserContentController,
                                   didReceive message: WKScriptMessage) {
            guard let body = message.body as? [String: Any],
                  let cmd = body["cmd"] as? String else { return }
            switch cmd {
            case "backfill":
                Task { await syncEngine.performFullBackfill() }
            case "resetBackfill":
                syncEngine.resetBackfillProgress()
            default:
                break
            }
        }
    }
}

struct ContentView: View {
    @EnvironmentObject var syncEngine: SyncEngine

    private var appURL: URL {
        URL(string: Config.backendURL)!
    }

    var body: some View {
        ZStack(alignment: .top) {
            WebView(url: appURL)
                .ignoresSafeArea()

            // Only a thin syncing banner — no floating action button anymore.
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
    }
}
