import SwiftUI
import AppKit

@main
struct WintripApp: App {
    init() {
        print("DEBUG: WintripApp wordt gestart...")
        // Dwing de applicatie naar de voorgrond voor directe toetsenbord-focus
        NSApplication.shared.activate(ignoringOtherApps: true)
    }

    var body: some Scene {
        // Hoofdvenster met unieke ID voor macOS vensterbeheer
        WindowGroup(id: "wintrip_main_window") {
            ContentView()
        }
        .commands {
            CommandGroup(replacing: .newItem) { } // Verwijder 'New Window' menu optie
        }

        // Menubalk item (zonder de foutieve 'id:' parameter)
        MenuBarExtra("WINTRIP AI", systemImage: "bolt.fill") {
            ContentView()
        }
    }
}
