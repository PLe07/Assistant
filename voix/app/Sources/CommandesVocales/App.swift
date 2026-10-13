#if os(macOS)
import SwiftUI

/// Point d'entrée de « Commandes Vocales » (barre des menus, LSUIElement=1 : pas d'icône dans le Dock).
@main
struct CommandesVocalesApp: App {
    var body: some Scene {
        MenuBarExtra("Voix", systemImage: "mic") {
            Text("Voix")
        }
    }
}
#else
/// Hors macOS (conteneur de construction), l'app n'a rien à faire : seul le Core est vérifié.
@main
enum CommandesVocalesApp {
    static func main() {
        print("Commandes Vocales ne tourne que sur macOS.")
    }
}
#endif
