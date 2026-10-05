from modules.demarrage.modele import Collecteur, Declencheurs, Fiche, Inventaire, identifiant


def test_identifiant_stable_et_distinct():
    assert identifiant("agent_utilisateur", "com.x") == identifiant("agent_utilisateur", "com.x")
    assert identifiant("agent_utilisateur", "com.x") != identifiant("agent_global", "com.x")
    assert identifiant("agent_utilisateur", "com.x") != identifiant("agent_utilisateur", "com.x", "/a.plist")
    assert len(identifiant("s", "l")) == 8


def test_resume_des_declencheurs():
    assert Declencheurs().resume() == "à la demande"
    d = Declencheurs(au_chargement=True, garder_en_vie=True, garder_conditions=["SuccessfulExit"], intervalle_s=7200,
                     calendrier=[{"Hour": 9}], chemins_surveilles=["/x"], au_montage=True)  # fmt: skip
    texte = d.resume()
    assert "ouverture de session" in texte and "(sous conditions)" in texte and "toutes les 2 h" in texte
    assert "1 horaire" in texte and "1 dossier" in texte and "disque" in texte
    assert "toutes les 1 j" in Declencheurs(intervalle_s=86400).resume()
    assert "toutes les 5 min" in Declencheurs(intervalle_s=300).resume()
    assert "toutes les 45 s" in Declencheurs(intervalle_s=45).resume()


def test_aller_retour_en_dictionnaire():
    f = Fiche(id="a", label="com.x", source="agent_utilisateur", declencheurs=Declencheurs(au_chargement=True),
              pids=[3], details={"relances": 4})  # fmt: skip
    inv = Inventaire(ts=1.0, fiches=[f], collecteurs=[Collecteur("S1", "ok", "", 1)])
    d = inv.vers_dict()
    d["fiches"][0]["champ_futur"] = 1  # une version plus récente a pu ajouter un champ : ignoré
    retour = Inventaire.depuis_dict(d)
    assert retour.fiches[0] == f and retour.collecteurs == inv.collecteurs
    assert retour.fiche("a") == f and retour.fiche("z") is None
    assert retour.par_label("com.x") == [f]
