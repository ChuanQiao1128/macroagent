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
                ResultView(store: store)
            }
            .tabItem {
                Label("Result", systemImage: "fork.knife.circle")
            }

            NavigationStack {
                ResultDebugView(store: store)
            }
            .tabItem {
                Label("Debug", systemImage: "terminal")
            }

            NavigationStack {
                MetadataPreviewView(store: store)
            }
            .tabItem {
                Label("Metadata", systemImage: "doc.text")
            }
        }
    }
}
