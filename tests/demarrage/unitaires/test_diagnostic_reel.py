"""Ce que le premier diagnostic sur le vrai Mac a montré (P11), reconstruit sans aucune donnée personnelle :
une app de musique ouverte à chaque connexion (≈ 1 Go) jugée ✅, un élément de test pris pour l'Assistant, des noms
identiques côte à côte, des fichiers cassés classés avant de vrais programmes, et « environ 0 Mo » de gain."""

from modules.demarrage import rapport
from modules.demarrage.actions.instructions import verifier
from modules.demarrage.analyse import analyser
from modules.demarrage.db import Base
from modules.demarrage.modele import Fiche, Inventaire

MAINTENANT = 1_791_200_000.0


def fiche(id_, label, **k):
    base = {"source": "agent_utilisateur", "programme": f"/opt/{id_}", "programme_existe": True,
            "signature": "developpeur", "editeur": "Éditeur", "actif": True}  # fmt: skip
    base.update(k)
    return Fiche(id=id_, label=label, **base)


def bilan(tmp_path, reglages, fiches):
    b = Base(tmp_path / "d.db")
    inventaire = Inventaire(ts=MAINTENANT, fiches=fiches)
    b.enregistrer_scan(inventaire)
    resultat = analyser(inventaire, b, reglages, MAINTENANT)
    b.fermer()
    return {e.fiche.id: e for e in resultat.elements}, resultat


def test_app_ouverte_a_la_connexion_et_utilisee_hier_est_quand_meme_inutile_au_demarrage(tmp_path, reglages):
    musique = fiche("s", "com.spotify.client", source="ouverture", app_parente="/Applications/Spotify.app",
                    programme="/Applications/Spotify.app/Contents/MacOS/Spotify",
                    derniere_utilisation_app=MAINTENANT - 3600)  # fmt: skip
    inconnue = fiche("z", "com.zebre.lecteur", source="ouverture", app_parente="/Applications/Zèbre.app",
                     derniere_utilisation_app=MAINTENANT - 3600)  # fmt: skip
    par_id, _ = bilan(tmp_path, reglages, [musique, inconnue])
    s = par_id["s"]
    assert s.verdict.code == "inutile" and s.verdict.regle == "pas_au_demarrage" and s.verdict.action == "reglages"
    assert "Ouvrir Spotify automatiquement" in s.verdict.raison  # sinon Spotify se remet tout seul
    # Une app inconnue de la base qui s'ouvre à la connexion : « ouverte hier » ne prouve plus qu'elle sert.
    assert par_id["z"].utilite == "inconnue" and "s'ouvre toute seule" in par_id["z"].raison_utilite


def test_un_element_de_test_n_est_pas_l_assistant_et_les_homonymes_sont_distingues(tmp_path, reglages):
    fiches = [
        fiche("t", "com.assistant.nettoyeur.test.charge", signature="non_signe", editeur=None),
        fiche("a1", "com.assistant.superviseur", c_est_moi=True, signature="non_signe", editeur=None),
        fiche("a2", "com.assistant.icone", c_est_moi=True, signature="non_signe", editeur=None),
        fiche("z1", "us.zoom.updater", source="agent_global"),
        fiche("z2", "us.zoom.updater.login.check", source="agent_global"),
        fiche("d1", "com.exemple.double", source="agent_utilisateur", nom="Double"),
        fiche("d2", "com.exemple.double", source="agent_app", nom="Double"),
        fiche("seul", "com.exemple.seul", nom="Seul"),
    ]
    par_id, _ = bilan(tmp_path, reglages, fiches)
    assert par_id["t"].nom == "com.assistant.nettoyeur.test.charge" and par_id["t"].verdict.code == "inconnu"
    assert par_id["a1"].nom == "L'Assistant (c'est moi) · com.assistant.superviseur"
    assert par_id["a2"].nom == "L'Assistant (c'est moi) · com.assistant.icone"
    assert {par_id["z1"].nom, par_id["z2"].nom} == {"Mise à jour de Zoom · us.zoom.updater",
                                                   "Mise à jour de Zoom · us.zoom.updater.login.check"}  # fmt: skip
    assert par_id["d1"].nom == "Double · ~/Library/LaunchAgents (à toi)"  # même label : on dit d'où il vient
    assert par_id["d2"].nom.startswith("Double · dans une app")
    assert par_id["seul"].nom == "Seul"


def test_un_fichier_de_lancement_casse_ne_coute_rien_et_le_dit(tmp_path, reglages):
    casse = fiche("g", "", programme=None, programme_existe=None, signature="inconnue", editeur=None,
                  chemin_plist="/Users/u/Library/LaunchAgents/com.google.keystone.agent.plist",
                  erreurs=["pas de Label"])  # fmt: skip
    par_id, _ = bilan(tmp_path, reglages, [casse, fiche("x", "com.zebre.agent")])
    g = par_id["g"]
    assert g.nom.startswith("Google") and g.impact == 0.0 and not g.impact_estime  # plus « 3 (estimé) »
    assert g.verdict.code == "inconnu" and "il ne lance rien" in g.verdict.raison
    texte = verifier(g.nom, g.editeur, g.fiche.chemin_plist, None, None, g.verdict.raison)
    assert "plutil -p /Users/u/Library/LaunchAgents/com.google.keystone.agent.plist" in texte  # de quoi le reconnaître


def test_gain_sans_mesure_n_est_pas_environ_zero_mo(tmp_path, reglages):
    _, resultat = bilan(tmp_path, reglages, [fiche("k", "com.google.keystone.agent")])
    _, gain = rapport.resume(resultat, reglages)
    assert "0 Mo" not in gain and "pas de gain mesuré pour l'instant" in gain
    assert gain.startswith("Si tu coupes l'élément 💤 ou 👻 :")
