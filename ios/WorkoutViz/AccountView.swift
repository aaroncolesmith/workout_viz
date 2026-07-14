import SwiftUI

/// Native account management sheet — required by App Store guidelines.
/// Accessible via the gear button overlay in ContentView or the JS bridge
/// command `window.WorkoutVizNative.openAccount()`.
struct AccountView: View {
    @EnvironmentObject var authService: AuthService
    @Environment(\.dismiss) private var dismiss

    @State private var showDeleteConfirm = false
    @State private var isExporting = false
    @State private var exportError: String?
    @State private var exportItem: ExportItem?
    @State private var isDeleting = false
    @State private var deleteError: String?
    @State private var morningReport = UserDefaults.standard.bool(
        forKey: NotificationManager.morningReportKey)

    var body: some View {
        NavigationStack {
            List {
                // ── Notifications (RDY-3) ───────────────────────────────────
                Section {
                    Toggle(isOn: Binding(
                        get: { morningReport },
                        set: { newVal in
                            morningReport = newVal
                            Task {
                                let ok = await NotificationManager.shared
                                    .setMorningReportEnabled(newVal)
                                if newVal && !ok { morningReport = false }
                            }
                        }
                    )) {
                        Label("Morning Readiness Report", systemImage: "sunrise")
                    }
                } header: {
                    Text("Notifications")
                } footer: {
                    Text("A daily readiness score with the why — sent when last night's sleep data syncs.")
                }

                // ── Data ─────────────────────────────────────────────────────
                Section("Your Data") {
                    Button {
                        Task { await exportData() }
                    } label: {
                        HStack {
                            Label("Export Data", systemImage: "arrow.down.circle")
                            Spacer()
                            if isExporting {
                                ProgressView().scaleEffect(0.8)
                            }
                        }
                    }
                    .disabled(isExporting)
                }

                // ── Data reset ────────────────────────────────────────────────
                Section {
                    Button(role: .destructive) {
                        showDeleteConfirm = true
                    } label: {
                        HStack {
                            Label("Delete All Data", systemImage: "trash")
                            Spacer()
                            if isDeleting { ProgressView().scaleEffect(0.8) }
                        }
                    }
                    .disabled(isDeleting)
                }

                if let err = exportError ?? deleteError {
                    Section {
                        Text(err).foregroundStyle(.red).font(.caption)
                    }
                }
            }
            .navigationTitle("Account")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .confirmationDialog(
                "Delete All Data",
                isPresented: $showDeleteConfirm,
                titleVisibility: .visible
            ) {
                Button("Delete All Data", role: .destructive) {
                    Task { await deleteAccount() }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("This permanently deletes all your workout data from this device and the server. This cannot be undone.")
            }
            .sheet(item: $exportItem) { item in
                ShareSheet(items: [item.url])
            }
        }
    }

    // MARK: - Export

    private func exportData() async {
        isExporting = true
        exportError = nil
        defer { isExporting = false }

        guard let url = URL(string: "\(Config.backendURL)/api/auth/account/export") else { return }
        let req = authService.authorizedRequest(url: url, timeout: 60)

        do {
            let (data, response) = try await URLSession.shared.data(for: req)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                exportError = "Export failed — try again."
                return
            }
            let tmp = FileManager.default.temporaryDirectory
                .appendingPathComponent("volken_export.zip")
            try data.write(to: tmp)
            exportItem = ExportItem(url: tmp)
        } catch {
            exportError = error.localizedDescription
        }
    }

    // MARK: - Delete

    private func deleteAccount() async {
        isDeleting = true
        deleteError = nil
        defer { isDeleting = false }

        guard let url = URL(string: "\(Config.backendURL)/api/auth/account") else { return }
        let req = authService.authorizedRequest(url: url, method: "DELETE", timeout: 30)

        do {
            let (_, response) = try await URLSession.shared.data(for: req)
            if let http = response as? HTTPURLResponse, http.statusCode == 204 {
                // Server purged; clear local state and dismiss
                authService.forgetDevice()
                dismiss()
            } else {
                deleteError = "Deletion failed — contact support."
            }
        } catch {
            deleteError = error.localizedDescription
        }
    }
}

// MARK: - Helpers

/// Identifiable wrapper so .sheet(item:) works with a URL.
private struct ExportItem: Identifiable {
    let id = UUID()
    let url: URL
}

/// UIActivityViewController wrapper for the share sheet.
private struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ vc: UIActivityViewController, context: Context) {}
}
