import SwiftUI
import WebKit

/// WKWebView wrapper that loads the Railway-hosted web app.
struct WebView: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true
        let wv = WKWebView(frame: .zero, configuration: config)
        wv.allowsBackForwardNavigationGestures = true
        wv.scrollView.contentInsetAdjustmentBehavior = .automatic
        return wv
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        if webView.url == nil {
            webView.load(URLRequest(url: url))
        }
    }
}

struct ContentView: View {
    @EnvironmentObject var syncEngine: SyncEngine
    @State private var showPermissionPrompt = false

    private var appURL: URL {
        URL(string: Config.backendURL)!
    }

    var body: some View {
        ZStack(alignment: .top) {
            WebView(url: appURL)
                .ignoresSafeArea()

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
            } else {
                // Floating backfill button — visible when idle
                Button {
                    Task { await syncEngine.performFullBackfill() }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.clockwise")
                            .font(.caption2)
                        Text("Backfill")
                            .font(.caption2)
                    }
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(.thinMaterial, in: Capsule())
                }
                .padding(.top, 8)
            }
        }
        .task {
            await syncEngine.requestPermissionsIfNeeded()
        }
    }
}
