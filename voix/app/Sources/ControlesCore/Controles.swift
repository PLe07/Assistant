import Foundation
import CommandesVocalesCore

/// Une vérification qui échoue lève `Echec`. Les mêmes vérifications sont lancées par XCTest (`swift test`) et par
/// l'exécutable `controles-core` (sans XCTest).
public struct Echec: Error, CustomStringConvertible {
    public let description: String
}

public struct Controle {
    public let nom: String
    public let corps: () throws -> Void

    public init(_ nom: String, _ corps: @escaping () throws -> Void) {
        self.nom = nom
        self.corps = corps
    }
}

public func verifier(
    _ condition: Bool, _ message: @autoclosure () -> String = "", fichier: StaticString = #fileID, ligne: UInt = #line
) throws {
    if !condition { throw Echec(description: "\(message()) [\(fichier):\(ligne)]") }
}

public func egal<T: Equatable>(
    _ obtenu: T, _ attendu: T, _ message: @autoclosure () -> String = "", fichier: StaticString = #fileID,
    ligne: UInt = #line
) throws {
    if obtenu != attendu {
        throw Echec(description: "\(message()) obtenu \(obtenu), attendu \(attendu) [\(fichier):\(ligne)]")
    }
}

public enum Suites {
    /// Toutes les suites, dans l'ordre.
    public static var toutes: [(String, [Controle])] {
        [
            ("Lignes", ControlesLignes.tous),
        ]
    }

    /// Lance tout ; rend le nombre de réussites et les échecs (« suite › contrôle : raison »).
    public static func lancer(_ suites: [(String, [Controle])] = toutes) -> (reussis: Int, echecs: [String]) {
        var reussis = 0
        var echecs: [String] = []
        for (suite, controles) in suites {
            for c in controles {
                do {
                    try c.corps()
                    reussis += 1
                } catch {
                    echecs.append("\(suite) › \(c.nom) : \(error)")
                }
            }
        }
        return (reussis, echecs)
    }
}

enum ControlesLignes {
    static let tous: [Controle] = [
        Controle("lignes complètes et morceaux") {
            var d = DecoupeurLignes(tailleMax: 64)
            try egal(d.ajouter(Data("{\"v\":1}\n{\"v\"".utf8)), [Data("{\"v\":1}".utf8)])
            try egal(d.ajouter(Data(":2}\r\n\n".utf8)), [Data("{\"v\":2}".utf8)])
            try egal(d.ajouter(Data()), [])
        },
        Controle("une ligne trop longue est jetée sans casser la suivante") {
            var d = DecoupeurLignes(tailleMax: 8)
            try egal(d.ajouter(Data("0123456789abcdef".utf8)), [])
            try egal(d.ajouter(Data("encore\nok\n".utf8)), [Data("ok".utf8)])
            try egal(d.rejetees, 1)
            try egal(d.ajouter(Data("12345678\n".utf8)), [Data("12345678".utf8)], "8 octets : la limite exacte")
        },
    ]
}
