import ControlesCore
import XCTest

/// Chaque suite de ControlesCore devient un test XCTest : `swift test` et `controles-core` vérifient la même chose.
final class CoreTests: XCTestCase {
    func testToutesLesSuites() {
        for (suite, controles) in Suites.toutes {
            for c in controles {
                do {
                    try c.corps()
                } catch {
                    XCTFail("\(suite) › \(c.nom) : \(error)")
                }
            }
        }
    }

    func testIlYADesControles() {
        XCTAssertGreaterThan(Suites.toutes.reduce(0) { $0 + $1.1.count }, 0)
    }
}
