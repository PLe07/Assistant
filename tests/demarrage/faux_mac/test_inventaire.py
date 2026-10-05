"""Le scan contre la vérité terrain du faux Mac n° 1 : chaque élément planté est trouvé, avec ses attributs."""

import pytest

from modules.demarrage import scan
from tests.demarrage.faux_mac.construire import APPLE_AGENTS, APPLE_DAEMONS, construire


@pytest.fixture
def faux(tmp_path):
    return construire(tmp_path / "mac")


@pytest.fixture
def inventaire(faux, reglages):
    return scan.scanner(faux.mac, reglages)


def fiche(inventaire, source, label):
    trouvees = [f for f in inventaire.fiches if f.source == source and f.label == label]
    assert len(trouvees) == 1, (source, label, len(trouvees))
    return trouvees[0]


def test_tout_est_trouve_sans_panne(faux, inventaire):
    etats = {c.nom: c.etat for c in inventaire.collecteurs}
    attendus = {"S1": "ok", "S2": "ok", "S3": "ok", "S4": "ok", "S5": "dégradé", "S6": "ok", "S7": "ok", "S8": "ok"}
    assert etats == {**attendus, "S9": "ok", "S10": "ok"}
    s5 = next(c for c in inventaire.collecteurs if c.nom == "S5")
    assert "administrateur" in s5.detail and "System Events" in s5.detail
    for source, label in faux.verite:
        fiche(inventaire, source, label)


def test_apple(faux, inventaire):
    apples = [f for f in inventaire.fiches if f.est_apple]
    assert len(apples) >= 15 and len(apples) == len(APPLE_AGENTS) + len(APPLE_DAEMONS)
    vrais = {label for (s, label), a in faux.verite.items() if a.verdict == "apple"}
    assert {f.label for f in apples} == vrais


def test_attributs_des_elements_plantes(inventaire):
    adobe = fiche(inventaire, "agent_global", "com.adobe.AdobeCreativeCloud")
    assert (
        adobe.editeur == "Adobe Inc."
        and adobe.app_parente.endswith("Adobe Creative Cloud.app")
        and adobe.pids == [3001]
    )
    assert adobe.derniere_utilisation_app is not None
    docker = fiche(inventaire, "agent_utilisateur", "com.docker.socket")
    assert docker.declencheurs.garder_en_vie and docker.declencheurs.garder_conditions == ["SuccessfulExit"]
    boucle = fiche(inventaire, "agent_utilisateur", "com.radioboucle.helper")
    assert boucle.details["relances"] == 412 and boucle.details["dernier_code"] == 1 and boucle.pids == []
    parti = fiche(inventaire, "agent_utilisateur", "com.exemple.desinstalle.agent")
    assert parti.programme_existe is False and parti.app_attendue_absente
    spotify = fiche(inventaire, "agent_utilisateur", "com.spotify.webhelper")
    assert spotify.programme_existe and spotify.app_attendue_absente and spotify.editeur == "Spotify AB"
    keystone = fiche(inventaire, "agent_utilisateur", "com.google.keystone.agent")
    assert keystone.editeur == "Google LLC" and keystone.declencheurs.intervalle_s == 3523
    assert keystone.app_parente is None  # dans ~/Library : l'app (Chrome) se déduit de la base de connaissances
    assert keystone.details["app_aide"].endswith("GoogleSoftwareUpdateAgent.app")
    mystere = fiche(inventaire, "agent_utilisateur", "com.mystere.agent")
    assert mystere.signature == "non_signe" and mystere.editeur is None
    faux_apple = fiche(inventaire, "agent_utilisateur", "com.apple.mise-a-jour")
    assert not faux_apple.est_apple and faux_apple.details["se_dit_apple"]
    casse = fiche(inventaire, "agent_utilisateur", "com.exemple.casse")
    assert casse.erreurs and casse.programme is None
    accents = fiche(inventaire, "agent_utilisateur", "com.exemple.Étiquette avec espaces")
    assert accents.desactive and accents.actif is False and accents.editeur == "Café Logiciels"
    assert fiche(inventaire, "agent_utilisateur", "com.exemple.doublon").doublon
    assert fiche(inventaire, "agent_global", "com.exemple.doublon").doublon
    assert fiche(inventaire, "agent_utilisateur", "com.assistant.superviseur").c_est_moi
    vpn = fiche(inventaire, "daemon_global", "com.exemple.vpn.daemon")
    assert vpn.charge is None and vpn.editeur == "Exemple VPN SAS"
    zoom = fiche(inventaire, "daemon_app", "us.zoom.ZoomDaemon")
    assert zoom.actif is None and zoom.app_parente == "/Applications/zoom.us.app"


def test_domaine_systeme_lisible(tmp_path, reglages):
    inv = scan.scanner(construire(tmp_path / "mac", systeme_lisible=True).mac, reglages)
    zoom = fiche(inv, "daemon_app", "us.zoom.ZoomDaemon")
    assert zoom.charge is False and zoom.actif is False  # enregistré nulle part : inactif


def test_identifiants_stables_et_uniques(faux, reglages, inventaire):
    ids = [f.id for f in inventaire.fiches]
    assert len(ids) == len(set(ids))
    assert ids == [f.id for f in scan.scanner(faux.mac, reglages).fiches]


def test_les_commandes_suivent_l_horloge(faux):
    faux.a_l_instant(10)
    tot = faux.mac.executer(["ps", "-axo", "x"]).sortie
    faux.a_l_instant(700)
    tard = faux.mac.executer(["ps", "-axo", "x"]).sortie
    assert " 3501 " in tot and " 3501 " not in tard  # keystone s'arrête au bout de 10 min
    assert "PreventUserIdleSystemSleep" in faux.mac.executer(["pmset", "-g", "assertions"]).sortie
    assert faux.mac.executer(["top", "-l", "2"]).sortie.count("PID    COMMAND") == 2
