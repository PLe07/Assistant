"""§9.2 sur le faux Mac n° 1 : 100 % des éléments plantés avec le bon verdict et la bonne action, 0 Apple avec une
action, 0 inconnu « à supprimer », les 3 plus lourds en tête, aucun plantage sur les plists corrompus."""

from tests.demarrage.faux_mac.construire import construire
from tests.demarrage.faux_mac.juge import diagnostiquer, juger


def test_criteres_du_faux_mac(tmp_path, reglages):
    faux = construire(tmp_path / "mac")
    bilan = diagnostiquer(faux, tmp_path, reglages)
    j = juger(faux, bilan)
    print()
    for label, attendu, obtenu, action, impact in sorted(j.lignes, key=lambda x: -x[4]):
        if attendu != "apple":
            print(f"   {'✅' if attendu == obtenu else '❌'} {label:<40} {obtenu:<9} {action:<13} impact {impact:5.1f}")
    assert j.reussi, "\n".join(j.erreurs)
    assert len(bilan.apple) >= 15
    casse = next(e for e in bilan.elements if e.fiche.label == "com.exemple.casse")
    assert casse.verdict.code == "inconnu" and "illisible" in casse.verdict.raison
    assert bilan.gains.memoire_mo > 1500 and bilan.gains.cpu_session_s > 250 and bilan.gains.veilles == 1
