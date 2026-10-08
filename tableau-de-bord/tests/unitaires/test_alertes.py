"""Les alertes (§6) : une par problème, rappel à 24 h, résolution, 3 par jour au plus, regroupées, silence de nuit
(sauf boucle qui consomme), sourdine, réveil, redémarrage du tableau de bord sans doublon."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from tableau import config, planif, systeme
from tableau.analyse import alertes
from tableau.analyse.alertes import Alertes, lire_duree
from tableau.db import Base
from tableau.module import EtatModule, Pastille, Probleme
from tableau.notifier import NotificateurMac, NotificateurMemoire, echapper_applescript


def local(annee: int, mois: int, jour: int, h: int, m: int = 0) -> float:
    return time.mktime((annee, mois, jour, h, m, 0, 0, 0, -1))


@pytest.fixture
def base(tmp_path: Path) -> Base:
    return Base(tmp_path / "t.db")


@pytest.fixture
def reglages() -> config.Reglages:
    return config.charger(Path("/nulle/part.toml"))


def boucle(nuit: bool = False) -> Probleme:
    return Probleme("bouclier", "boucle", "grave", "🔴 Bouclier s'est arrêté 5 fois en 10 min.",
                    "✅ Bouclier tourne de nouveau sans s'arrêter.", nuit_permise=nuit)  # fmt: skip


def file_trieur() -> Probleme:
    return Probleme("trieur", "file", "attention", "🟡 Trieur : 2 documents attendent depuis 45 min.",
                    "✅ Trieur : la file s'est vidée.", sous_cle="BoiteMac")  # fmt: skip


class Monde:
    """Le tableau de bord qui tourne : un tour par minute, ce que la santé voit à chaque tour."""

    def __init__(self, base: Base, reglages: config.Reglages, t: float) -> None:
        self.base = base
        self.reglages = reglages
        self.t = t
        self.notif = NotificateurMemoire()
        self.a = Alertes(base, reglages, self.notif, lambda: self.t)

    def tours(self, minutes: int, problemes: list[Probleme], observes: tuple[str, ...] = ("bouclier", "trieur"),
              **k: Any) -> list[alertes.Envoi]:  # fmt: skip
        envois = []
        for _ in range(minutes):
            self.a.suivre(problemes, observes, self.t, **k)
            e = self.a.tour(self.t)
            if e:
                envois.append(e)
            self.t += 60
        return envois


def test_une_alerte_confirmee_puis_resolution(base: Base, reglages: config.Reglages) -> None:
    m = Monde(base, reglages, local(2026, 10, 7, 10))
    assert m.tours(1, [boucle()]) == []  # vu une fois : pas encore confirmé
    envois = m.tours(10, [boucle()])
    assert len(envois) == 1 and envois[0].texte == "🔴 Bouclier s'est arrêté 5 fois en 10 min."
    assert envois[0].titre == "Tableau de bord" and envois[0].envoyee
    # Il revient à la normale : la résolution part une fois, après 150 s d'absence.
    assert m.tours(2, []) == []
    envois = m.tours(5, [])
    assert [e.texte for e in envois] == ["✅ Bouclier tourne de nouveau sans s'arrêter."]
    assert m.tours(30, []) == []
    assert len(m.notif.envoyees) == 2
    journal = [r["genre"] for r in base.evenements(0)]
    assert journal.count("boucle") == 1 and journal.count("resolution") == 1 and journal.count("notification") == 2


def test_passager_ou_revenu_avant_la_resolution(base: Base, reglages: config.Reglages) -> None:
    """Un problème vu un seul tour ne fait rien ; un problème qui revient avant 150 s n'est ni résolu ni réannoncé."""
    m = Monde(base, reglages, local(2026, 10, 7, 10))
    m.tours(1, [boucle()])
    assert m.tours(10, []) == [] and m.notif.envoyees == []
    assert base.valeur("SELECT resolution_envoyee FROM problemes") == 1  # clos sans bruit
    m.tours(5, [boucle()])
    assert len(m.notif.envoyees) == 1
    for _ in range(5):  # clignote : absent 2 min, présent 2 min
        m.tours(2, [])
        m.tours(2, [boucle()])
    assert len(m.notif.envoyees) == 1
    # Réglé sans avoir été annoncé : aucun message.
    m2 = Monde(Base(base.chemin.with_name("b.db")), reglages, m.t)
    m2.tours(1, [file_trieur()])
    m2.tours(10, [])
    assert m2.notif.envoyees == []


def test_redemarrage_du_tableau_de_bord_sans_doublon(base: Base, reglages: config.Reglages) -> None:
    m = Monde(base, reglages, local(2026, 10, 7, 10))
    m.tours(5, [boucle()])
    assert len(m.notif.envoyees) == 1
    # Le démon redémarre : nouvelle instance, même base.
    m.a = Alertes(Base(base.chemin), reglages, m.notif, lambda: m.t)
    m.tours(60, [boucle()])
    assert len(m.notif.envoyees) == 1


def test_rappel_au_bout_de_24_h(base: Base, reglages: config.Reglages) -> None:
    m = Monde(base, reglages, local(2026, 10, 7, 10))
    m.tours(5, [file_trieur()])
    m.t += 24 * 3600 - 10 * 60
    assert m.tours(4, [file_trieur()]) == []
    envois = m.tours(5, [file_trieur()])
    assert len(envois) == 1 and envois[0].texte.startswith("Toujours en cours depuis 1 j : 🟡 Trieur")
    m.t += 3600
    assert m.tours(5, [file_trieur()]) == []  # pas de second rappel avant 24 h de plus


def test_trois_par_jour_au_plus(base: Base, reglages: config.Reglages) -> None:
    m = Monde(base, reglages, local(2026, 10, 7, 9))
    for i in range(5):
        p = Probleme("trieur", "attente", "attention", f"🟡 attente {i}", f"✅ attente {i}", sous_cle=str(i))
        m.tours(10, [p])
        m.t += 3600
    assert len(m.notif.envoyees) == 3
    assert m.a.retenue(m.t) == "3 notifications aujourd'hui : la suite attend demain"
    # Une résolution sur le point d'arriver part avec l'alerte suivante : 0 seule, puis (1 + fin de 0), (2 + fin de 1).
    assert [t.splitlines() for _, t in m.notif.envoyees] == [
        ["🟡 attente 0"],
        ["🟡 attente 1", "✅ attente 0"],
        ["🟡 attente 2", "✅ attente 1"],
    ]
    # Le lendemain à 8 h, ce qui a attendu et reste vrai part, en une seule notification. L'attente 3, réglée sans
    # avoir été annoncée, ne fait aucun bruit.
    m.t = local(2026, 10, 8, 8, 1)
    envois = m.tours(1, [], observes=())
    assert len(envois) == 1 and envois[0].titre == "Tableau de bord : 2 points"
    assert envois[0].texte.splitlines() == ["🟡 attente 4", "✅ attente 2"]


def test_regroupees_si_ensemble(base: Base, reglages: config.Reglages) -> None:
    m = Monde(base, reglages, local(2026, 10, 7, 10))
    m.tours(1, [boucle()])
    m.tours(1, [boucle(), file_trieur()])  # le second arrive une minute après
    envois = m.tours(10, [boucle(), file_trieur()])
    assert len(envois) == 1 and envois[0].titre == "Tableau de bord : 2 points"
    assert envois[0].texte.splitlines()[0].startswith("🔴")  # le grave d'abord
    # Beaucoup à la fois : 4 lignes au plus, puis un renvoi vers la page.
    m2 = Monde(Base(base.chemin.with_name("b.db")), reglages, m.t)
    beaucoup = [Probleme("trieur", "file", "attention", f"🟡 file {i}", "✅", sous_cle=str(i)) for i in range(6)]
    envois = m2.tours(5, beaucoup, observes=("trieur",))
    assert len(envois) == 1
    assert envois[0].texte.splitlines()[-1] == "… et 2 autres : ouvre le tableau de bord."


def test_regroupement_ne_retient_pas_indefiniment(base: Base, reglages: config.Reglages) -> None:
    """Un problème qui reparaît sans cesse (jamais confirmé) ne bloque pas les autres plus de 2 min."""
    m = Monde(base, reglages, local(2026, 10, 7, 10))
    m.tours(1, [boucle()])
    envois: list[alertes.Envoi] = []
    for i in range(8):
        p = Probleme("trieur", "file", "attention", f"🟡 file {i}", "✅", sous_cle=str(i))
        envois += m.tours(1, [boucle(), p])
    assert len(envois) == 1 and "Bouclier" in envois[0].texte


def test_silence_de_nuit_sauf_boucle_qui_consomme(base: Base, reglages: config.Reglages) -> None:
    m = Monde(base, reglages, local(2026, 10, 7, 23, 30))
    m.tours(10, [file_trieur()])
    assert m.notif.envoyees == [] and m.a.retenue(m.t) == "silence de nuit jusqu'à 8h"
    m.tours(10, [file_trieur(), boucle(nuit=True)])
    assert [t for _, t in m.notif.envoyees] == ["🔴 Bouclier s'est arrêté 5 fois en 10 min."]
    m.t = local(2026, 10, 8, 7, 55)
    assert m.tours(4, [file_trieur(), boucle(nuit=True)]) == []
    envois = m.tours(3, [file_trieur(), boucle(nuit=True)])
    assert len(envois) == 1 and envois[0].texte == "🟡 Trieur : 2 documents attendent depuis 45 min."
    # Une boucle qui ne consomme pas attend le matin.
    m2 = Monde(Base(base.chemin.with_name("b.db")), reglages, local(2026, 10, 9, 2))
    assert m2.tours(30, [boucle(nuit=False)]) == []


def test_silence_reglable_et_sans_silence(base: Base, reglages: config.Reglages) -> None:
    a = Alertes(base, reglages, NotificateurMemoire())
    assert a.en_silence(local(2026, 10, 7, 23)) and a.en_silence(local(2026, 10, 7, 7, 59))
    assert not a.en_silence(local(2026, 10, 7, 8)) and not a.en_silence(local(2026, 10, 7, 22, 59))
    a.r["silence_debut"], a.r["silence_fin"] = 13, 14
    assert a.en_silence(local(2026, 10, 7, 13, 30)) and not a.en_silence(local(2026, 10, 7, 14))
    a.r["silence_debut"] = a.r["silence_fin"] = 0
    assert not a.en_silence(local(2026, 10, 7, 3))


def test_pas_d_alerte_juste_apres_le_reveil(base: Base, reglages: config.Reglages) -> None:
    m = Monde(base, reglages, local(2026, 10, 7, 10))
    planif.noter_veille(base, m.t - 8 * 3600, m.t)
    assert m.tours(9, [file_trieur()]) == []
    assert m.a.retenue(m.t) == "le Mac vient de se réveiller : on laisse tout se remettre en route"
    assert len(m.tours(3, [file_trieur()])) == 1


def test_sourdine(base: Base, reglages: config.Reglages) -> None:
    m = Monde(base, reglages, local(2026, 10, 7, 10))
    fin = m.a.sourdine(3600, m.t)
    assert fin == m.t + 3600 and m.a.sourdine_jusqua(m.t) == fin
    assert m.a.retenue(m.t) == "en sourdine jusqu'à 11h00"
    assert m.tours(59, [boucle()]) == []
    envois = m.tours(2, [boucle()])
    assert len(envois) == 1  # encore vrai à la fin : il part
    m.a.sourdine(1800, m.t)
    m.a.sourdine(0, m.t)
    assert m.a.sourdine_jusqua(m.t) is None and m.a.retenue(m.t) is None
    base.ecrire_meta("sourdine_jusqua", "abîmé")
    assert m.a.sourdine_jusqua(m.t) is None
    assert [r["message"] for r in base.evenements(0) if r["genre"] == "sourdine"][0] == "Sourdine levée"


def test_lire_duree() -> None:
    assert lire_duree("1h") == 3600 and lire_duree("1 h") == 3600 and lire_duree("30min") == 1800
    assert lire_duree("2h30") == 9000 and lire_duree("45") == 2700 and lire_duree("90 minutes") == 5400
    assert lire_duree("0") == 0 and lire_duree("fin") == 0
    assert lire_duree("demain") is None and lire_duree("") is None and lire_duree("9999h") is None


def test_familles_boucle_devenue_arret_et_budget(base: Base, reglages: config.Reglages) -> None:
    m = Monde(base, reglages, local(2026, 10, 7, 10))
    m.tours(5, [boucle()])
    arret = Probleme("bouclier", "arrete", "grave", "🔴 Bouclier est arrêté.", "✅ Bouclier tourne de nouveau.")
    envois = m.tours(5, [arret])
    assert [e.texte for e in envois] == ["🔴 Bouclier est arrêté."]  # jamais « tourne de nouveau » à tort
    envois = m.tours(5, [])
    assert [e.texte for e in envois] == ["✅ Bouclier tourne de nouveau."]
    b80 = Probleme("trieur", "budget80", "attention", "🟡 Trieur : 85 % du budget.", "✅ Trieur sous 80 %.")
    b100 = Probleme("trieur", "budget100", "grave", "🔴 Trieur a dépassé son budget.", "✅ Trieur sous son budget.")
    m.t = local(2026, 10, 8, 9)  # le lendemain : le quota du jour est neuf
    m.tours(5, [b80])
    envois = m.tours(5, [b100])
    assert [e.texte for e in envois] == ["🔴 Trieur a dépassé son budget."]
    assert len(m.notif.envoyees) == 5  # 3 la veille, 2 aujourd'hui


def test_module_eteint_retire_ou_code_accepte(base: Base, reglages: config.Reglages) -> None:
    m = Monde(base, reglages, local(2026, 10, 7, 10))
    m.tours(5, [boucle(), file_trieur()])
    # Bouclier mis en pause par toi : l'alerte est close avec un message ; le Trieur retiré du registre : en silence.
    envois = m.tours(1, [], observes=(), eteints=["bouclier"], connus=["bouclier"], noms={"bouclier": "Bouclier"})
    assert [e.texte for e in envois] == ["⚪ Bouclier est éteint, en pause ou désinstallé : l'alerte est close."]
    assert m.a.ouverts() == []
    code = Probleme("trieur", "integrite", "attention", "⚠️ Le code du Trieur a changé.", "✅ Code de référence.")
    m.t += 3 * 3600
    m.tours(5, [code])
    m.a.accepter("trieur", m.t)
    assert m.tours(10, []) == [] and m.a.ouverts() == []
    # Un problème jamais annoncé, module éteint : rien.
    m.tours(1, [file_trieur()])
    assert m.tours(1, [], observes=(), eteints=["trieur"]) == []


def test_echec_du_notificateur_note_sans_boucle(base: Base, reglages: config.Reglages) -> None:
    m = Monde(base, reglages, local(2026, 10, 7, 10))
    m.notif.en_panne = True
    envois = m.tours(10, [boucle()])
    assert len(envois) == 1 and not envois[0].envoyee and "panne" in envois[0].motif
    assert m.a.dernieres_notifications()[0]["envoyee"] == 0
    assert m.a.envoyees_aujourdhui(m.t) == 0
    notes = [r for r in base.evenements(0) if r["genre"] == "notification"]
    assert notes[0]["details"].startswith("non affichée")


def test_info_du_rapport_une_seule_fois(base: Base, reglages: config.Reglages) -> None:
    m = Monde(base, reglages, local(2026, 10, 11, 20))
    m.a.ajouter_info("rapport:2026-10-11", "📊 Ta semaine : aucun souci.", m.t)
    m.a.ajouter_info("rapport:2026-10-11", "📊 doublon", m.t)
    envois = m.tours(1, [], observes=())
    assert [e.texte for e in envois] == ["📊 Ta semaine : aucun souci."]
    m.a.ajouter_info("rapport:2026-10-11", "📊 encore", m.t)
    assert m.tours(5, [], observes=()) == []
    base.ecrire_meta("infos_en_attente", "abîmé")
    base.ecrire_meta("infos_parties", "abîmé")
    assert m.a.candidats(m.t) == []


def test_traiter_depuis_les_etats(base: Base, reglages: config.Reglages) -> None:
    m = Monde(base, reglages, local(2026, 10, 7, 10))
    rouge = EtatModule("bouclier", "Bouclier", "🛡️", Pastille.ROUGE, "", problemes=[boucle()])
    gris = EtatModule("corvees", "Corvées", "🧹", Pastille.GRIS, "Éteint")
    for _ in range(5):
        m.a.traiter([rouge, gris], m.t, connus=["bouclier", "corvees"])
        m.t += 60
    assert len(m.notif.envoyees) == 1
    assert m.a.ouverts()[0]["cle"] == "bouclier:boucle"


def test_notificateur_mac(monkeypatch: pytest.MonkeyPatch) -> None:
    assert echapper_applescript('Dit "oui" \\ non\nfin\x07') == 'Dit \\"oui\\" \\\\ non\\nfin '
    assert len(echapper_applescript("x" * 1000)) == 400
    monkeypatch.setattr(systeme, "est_un_mac", lambda: False)
    assert NotificateurMac().envoyer("t", "x") == (False, "pas un Mac : notification seulement notée")
    vues: list[list[str]] = []

    def executer(args: list[str], delai: float = 15) -> systeme.Resultat:
        systeme.verifier(args)  # la liste blanche l'accepte
        vues.append(args)
        return systeme.Resultat(0 if len(vues) == 1 else 1, "", "execution error: refusé\n")

    monkeypatch.setattr(systeme, "est_un_mac", lambda: True)
    monkeypatch.setattr(systeme, "executer", executer)
    assert NotificateurMac().envoyer("Tableau de bord", 'Le "Trieur"') == (True, "")
    assert vues[0] == ["osascript", "-e", 'display notification "Le \\"Trieur\\"" with title "Tableau de bord"']
    assert NotificateurMac().envoyer("t", "x") == (False, "execution error: refusé")


def test_demon_qui_meurt_pendant_l_envoi_jamais_de_doublon(base: Base, reglages: config.Reglages) -> None:
    """Noté d'abord, envoyé ensuite : un arrêt brutal entre les deux perd une notification, jamais ne la double."""

    class Coupure(Exception):
        pass

    class MeurtEnEnvoyant:
        def envoyer(self, titre: str, texte: str) -> tuple[bool, str]:
            raise Coupure

    m = Monde(base, reglages, local(2026, 10, 7, 10))
    m.a = Alertes(base, reglages, MeurtEnEnvoyant(), lambda: m.t)
    m.tours(1, [boucle()])
    with pytest.raises(Coupure):
        m.tours(5, [boucle()])
    note = m.a.dernieres_notifications()[0]
    assert note["envoyee"] == 0 and note["motif"] == "envoi en cours"
    # Le démon redémarre : rien n'est renvoyé.
    m.a = Alertes(base, reglages, m.notif, lambda: m.t)
    m.tours(20, [boucle()])
    assert m.notif.envoyees == []
