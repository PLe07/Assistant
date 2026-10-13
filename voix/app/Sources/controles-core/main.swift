import ControlesCore

#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

// Les vérifications du Core, sans XCTest : code 0 si tout passe, 1 sinon.
let resultat = Suites.lancer()
for echec in resultat.echecs {
    print("✗ \(echec)")
}
print("controles-core : \(resultat.reussis) réussi(s), \(resultat.echecs.count) échec(s)")
exit(resultat.echecs.isEmpty ? 0 : 1)
