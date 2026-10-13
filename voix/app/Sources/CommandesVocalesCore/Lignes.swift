import Foundation

/// Le protocole entre l'app et le moteur : une ligne JSON par message, en UTF-8, avec `"v": 1`.
public enum Protocole {
    public static let version = 1
    /// Une ligne plus longue est refusée (un message normal fait moins de 10 Ko ; l'audio part par morceaux de 100 ms).
    public static let tailleMaxLigne = 1 << 20
}

/// Découpe un flux d'octets en lignes complètes, sans jamais garder plus de `tailleMax` octets en attente.
public struct DecoupeurLignes {
    private var tampon = Data()
    public let tailleMax: Int
    /// Lignes trop longues jetées depuis le début (une ligne cassée ne casse pas les suivantes).
    public private(set) var rejetees = 0
    private var enRejet = false

    public init(tailleMax: Int = Protocole.tailleMaxLigne) {
        self.tailleMax = tailleMax
    }

    /// Ajoute des octets reçus et rend les lignes complètes (sans le `\n`, `\r` final retiré, vides ignorées).
    public mutating func ajouter(_ octets: Data) -> [Data] {
        var lignes: [Data] = []
        for octet in octets {
            if octet == 0x0A {
                if enRejet {
                    enRejet = false
                } else {
                    var ligne = tampon
                    if ligne.last == 0x0D { ligne.removeLast() }
                    if !ligne.isEmpty { lignes.append(ligne) }
                }
                tampon.removeAll(keepingCapacity: true)
                continue
            }
            if enRejet { continue }
            if tampon.count >= tailleMax {
                tampon.removeAll(keepingCapacity: false)
                enRejet = true
                rejetees += 1
                continue
            }
            tampon.append(octet)
        }
        return lignes
    }
}
