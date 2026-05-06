import SwiftUI

@MainActor
struct RootView: View {
    @StateObject private var store = CaptureFlowStore()

    var body: some View {
        TabView {
            NavigationStack {
                CaptureScreenView(store: store)
            }
            .tabItem {
                Label("Capture", systemImage: "camera")
            }

            NavigationStack {
                MetadataPreviewView(store: store)
            }
            .tabItem {
                Label("Metadata", systemImage: "doc.text")
            }

            NavigationStack {
                ResultDebugView(store: store)
            }
            .tabItem {
                Label("Result", systemImage: "terminal")
            }
        }
    }
}
