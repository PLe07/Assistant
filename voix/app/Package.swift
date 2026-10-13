// swift-tools-version:5.9
// Commandes Vocales : l'app de barre des menus de Voix (micro, raccourci global, bulle, sons, Apple Speech).
// - CommandesVocalesCore : la logique sans macOS (protocole, découpage des lignes, états, raccourci, suspension),
//   compilée et vérifiée partout, y compris dans le conteneur de construction (Linux).
// - ControlesCore + controles-core : les vérifications du Core, lançables sans XCTest (les seuls Command Line Tools
//   du Mac n'ont pas toujours XCTest) ; le même code est appelé par les tests XCTest.
// - CommandesVocales : l'app macOS (AppKit, SwiftUI, AVFoundation, Speech, Carbon, CoreAudio).
import PackageDescription

let package = Package(
    name: "CommandesVocales",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "CommandesVocales", targets: ["CommandesVocales"]),
        .executable(name: "controles-core", targets: ["controles-core"]),
    ],
    targets: [
        .target(name: "CommandesVocalesCore", path: "Sources/CommandesVocalesCore"),
        .target(name: "ControlesCore", dependencies: ["CommandesVocalesCore"], path: "Sources/ControlesCore"),
        .executableTarget(name: "controles-core", dependencies: ["ControlesCore"], path: "Sources/controles-core"),
        .executableTarget(
            name: "CommandesVocales", dependencies: ["CommandesVocalesCore"], path: "Sources/CommandesVocales"),
        .testTarget(
            name: "CommandesVocalesCoreTests", dependencies: ["ControlesCore"],
            path: "Tests/CommandesVocalesCoreTests"),
    ]
)
