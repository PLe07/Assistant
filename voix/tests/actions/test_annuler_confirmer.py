"""« Annule » remet exactement l'état d'avant ; la confirmation : « oui » dans le délai, sinon annulation (§9.3)."""

from __future__ import annotations

from tests.faux_mac import FauxMac
from voix.actions.confirmation import Confirmations
from voix.nlu.comprendre import Comprehension
from voix.nlu.intentions import INTENTIONS
from voix.session import Session


class Horloge:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_annuler_le_volume_remet_niveau_et_sourdine_exacts(mac: FauxMac) -> None:
    mac.regler(volume=37, muet=True)
    s = Session(mac.outils())
    s.entendre("volume à 80")
    assert mac.etat["volume"] == 80 and mac.etat["muet"] is False  # régler le volume enlève la sourdine
    s.entendre("annule")
    assert (mac.etat["volume"], mac.etat["muet"]) == (37, True)


def test_annuler_dans_l_ordre_inverse(mac: FauxMac) -> None:
    s = Session(mac.outils())
    s.entendre("volume à 20")
    s.entendre("monte le son de 30")
    s.entendre("coupe le son")
    assert (mac.etat["volume"], mac.etat["muet"]) == (50, True)
    assert s.entendre("annule").texte == "✓ Annulé : Volume remis à 50 %"
    assert (mac.etat["volume"], mac.etat["muet"]) == (50, False)
    s.entendre("annule")
    assert mac.etat["volume"] == 20
    s.entendre("annule")
    assert mac.etat["volume"] == 45
    assert s.entendre("annule").texte == "Il n'y a rien à annuler."


def test_annuler_apparence_wifi_concentration(mac: FauxMac) -> None:
    s = Session(mac.outils())
    s.entendre("mode sombre")
    assert mac.etat["sombre"] is True
    s.entendre("annule")
    assert mac.etat["sombre"] is False
    s.entendre("coupe le wifi")
    s.entendre("oui")
    assert mac.etat["wifi"] is False
    assert s.entendre("annule").texte == "✓ Annulé : Wi-Fi rallumé"
    assert mac.etat["wifi"] is True
    mac.vider()
    s.entendre("active la concentration")
    s.entendre("annule")
    assert mac.appels() == [("shortcuts", ["run", "Activer concentration"]),
                            ("shortcuts", ["run", "Désactiver concentration"])]  # fmt: skip


def test_rien_a_annuler_si_rien_n_a_change(mac: FauxMac) -> None:
    s = Session(mac.outils())
    s.entendre("mode clair")  # déjà clair : rien à défaire
    assert s.entendre("annule").texte == "Il n'y a rien à annuler."
    s.entendre("ouvre Notion")  # ouvrir une app ne s'annule pas
    assert s.entendre("annule").texte == "Il n'y a rien à annuler."


def test_un_echec_d_annulation_garde_l_annulation(mac: FauxMac) -> None:
    s = Session(mac.outils())
    s.entendre("volume à 10")
    mac.regler(codes={"osascript": 1})
    assert s.entendre("annule").statut == "erreur"
    mac.regler(codes={})
    assert s.entendre("annule").statut == "fait" and mac.etat["volume"] == 45


def test_confirmation_oui_non_silence(mac: FauxMac) -> None:
    h = Horloge()
    s = Session(mac.outils(), horloge=h)
    assert s.entendre("mets le Mac en veille").texte == "Je mets le Mac en veille, tu confirmes ?"
    assert s.entendre("non").texte == "D'accord, je ne fais rien."
    assert mac.appels() == []
    s.entendre("mets le Mac en veille")
    h.t += 4.9
    assert s.tic() == []
    assert s.entendre("oui").statut == "fait"
    assert mac.appels() == [("pmset", ["sleepnow"])]
    mac.vider()
    s.entendre("ferme tout")
    h.t += 5.1
    assert [r.texte for r in s.tic()] == ["Pas de réponse : je ne fais rien."]
    assert s.entendre("oui").texte == "Il n'y a rien à confirmer."
    assert mac.pont.ordres == []


def test_oui_trop_tard_sans_tic(mac: FauxMac) -> None:
    h = Horloge()
    s = Session(mac.outils(), horloge=h)
    s.entendre("coupe le wifi")
    h.t += 6
    assert s.entendre("oui").texte == "Trop tard : je n'ai rien fait."
    assert mac.appels() == []


def test_autre_chose_qu_un_oui_annule_et_passe_a_la_suite(mac: FauxMac) -> None:
    s = Session(mac.outils())
    s.entendre("ferme tout")
    assert s.entendre("ouvre Notion").texte == "✓ Notion ouvert"
    assert s.entendre("oui").texte == "Il n'y a rien à confirmer."
    assert mac.pont.ordres == []


def test_toutes_les_sensibles_passent_par_la_confirmation(mac: FauxMac) -> None:
    for phrase in ("mets le Mac en veille", "ferme tout", "ferme tout sauf Safari", "coupe le wifi", "fin de journée"):
        s = Session(mac.outils())
        assert s.entendre(phrase).statut == "question", phrase
    assert mac.appels() == [] and mac.pont.ordres == []


def test_confirmations_seules() -> None:
    h = Horloge()
    c = Confirmations(5.0, h)
    assert c.expirer() is None and not c.en_attente()
    c.demander(Comprehension("compris", "systeme.veille"))
    assert c.en_attente()
    assert c.repondre(False) is None and not c.en_attente()
    c.demander(Comprehension("compris", "systeme.veille"))
    assert c.repondre(True) is not None
    r = c.demander(Comprehension("compris", "systeme.batterie"))
    assert r.texte == f"{INTENTIONS['systeme.batterie'].titre} : tu confirmes ?"
