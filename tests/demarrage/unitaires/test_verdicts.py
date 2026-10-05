"""Chaque règle de verdict, seule, avec ses cas positifs et négatifs ; puis l'ordre et les garde-fous."""

import pytest

from modules.demarrage.analyse import connaissances
from modules.demarrage.analyse import verdicts as v
from modules.demarrage.analyse.scores import Metriques
from modules.demarrage.modele import Declencheurs, Fiche


def fiche(**k):
    base = {"id": "x", "label": "com.exemple.agent", "source": "agent_utilisateur", "programme": "/opt/x/agent",
            "programme_existe": True, "signature": "developpeur", "editeur": "Exemple SAS", "actif": True}  # fmt: skip
    base.update(k)
    return Fiche(**base)


def ctx(reglages, f=None, impact=0.0, utilite="inconnue", connaissance=None, metriques=None):
    return v.Contexte(f or fiche(), metriques or Metriques(), impact, utilite, "raison", connaissance, reglages)


def kb(label):
    return connaissances.trouver(Fiche(id="k", label=label, source="agent_utilisateur"))


# --- 🍎 -----------------------------------------------------------------------------------------------------------


def test_apple(reglages):
    assert v.regle_apple(ctx(reglages, fiche(est_apple=True))).code == "apple"
    assert v.regle_apple(ctx(reglages, fiche(chemin_plist="/System/Library/LaunchAgents/x.plist"))).code == "apple"
    assert v.regle_apple(ctx(reglages, fiche(programme="/System/Library/x"))).code == "apple"
    assert v.regle_apple(ctx(reglages, fiche())) is None
    assert v.regle_apple(ctx(reglages, fiche(est_apple=True, details={"se_dit_apple": True}))) is None


def test_apple_n_a_jamais_d_action_meme_si_lourd_et_inutile(reglages):
    reglages["verdicts"]["ordre"] = ["lourd_inutile", "apple"]  # même dans le mauvais ordre
    f = fiche(est_apple=True, source="apple")
    verdict = v.juger(ctx(reglages, f, impact=99.0, utilite="faible"))
    assert verdict.code == "inutile" or verdict.action != "desactiver"
    reglages["verdicts"]["ordre"] = ["apple", "lourd_inutile"]
    assert v.juger(ctx(reglages, f, impact=99.0, utilite="faible")).action == "aucune"
    assert v.action_pour(f, "apple") == "aucune"


# --- c'est moi -----------------------------------------------------------------------------------------------------


def test_moi(reglages):
    verdict = v.regle_moi(ctx(reglages, fiche(c_est_moi=True)))
    assert verdict.code == "utile" and verdict.action == "aucune"
    assert v.regle_moi(ctx(reglages)) is None


# --- 👻 ----------------------------------------------------------------------------------------------------------


def test_orphelin(reglages):
    absent = fiche(programme_existe=False, details={"absent_certain": True})
    assert v.regle_orphelin(ctx(reglages, absent)).code == "orphelin"
    assert v.regle_orphelin(ctx(reglages, absent)).action == "quarantaine"
    deplace = fiche(
        programme_existe=False, details={"absent_certain": True, "app_deplacee_vers": "/Applications/B/A.app"}
    )
    assert "déplacée" in v.regle_orphelin(ctx(reglages, deplace)).raison
    assert v.regle_orphelin(ctx(reglages, fiche(app_attendue_absente=True))).code == "orphelin"
    assert (
        v.regle_orphelin(ctx(reglages, fiche(source="assistant_privilegie", details={"sans_plist": True}))).action
        == "instructions"
    )
    # Négatifs : programme présent ; dossier illisible ; app disparue mais programme non signé ; assistant non signé.
    assert v.regle_orphelin(ctx(reglages, fiche())) is None
    assert v.regle_orphelin(ctx(reglages, fiche(programme_existe=False, details={"absent_certain": False}))) is None
    assert v.regle_orphelin(ctx(reglages, fiche(app_attendue_absente=True, signature="non_signe"))) is None
    assert v.regle_orphelin(ctx(reglages, fiche(details={"sans_plist": True}, signature="non_signe"))) is None


def test_actions_d_un_orphelin_selon_la_source(reglages):
    for source, action in [("ouverture", "reglages"), ("agent_global", "instructions"), ("cron", "instructions"),
                           ("launchd", "desactiver"), ("agent_utilisateur", "quarantaine")]:  # fmt: skip
        f = fiche(source=source, programme_existe=False, details={"absent_certain": True}, actif=False)
        assert v.regle_orphelin(ctx(reglages, f)).action == action, source


# --- ⚠️ ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("modifs", "morceau"),
    [
        ({"erreurs": ["plist corrompu"], "programme": None}, "illisible"),
        ({"details": {"se_dit_apple": True}}, "Apple"),
        ({"programme": None}, "programme"),
        ({"programme_existe": False}, "pas lisible"),
        ({"signature": "non_signe", "editeur": None}, "non signé"),
        ({"signature": "invalide", "editeur": None}, "invalide"),
        ({"signature": "adhoc", "editeur": None}, "ad hoc"),
        ({"signature": "inconnue", "editeur": None}, "inconnu"),
        ({"signature": "apple", "editeur": None, "details": {"programme_systeme": True}}, "macOS"),
    ],
)
def test_inconnu(reglages, modifs, morceau):
    verdict = v.regle_inconnu(ctx(reglages, fiche(**modifs)))
    assert verdict.code == "inconnu" and morceau in verdict.raison and verdict.action == "verifier"


def test_pas_inconnu(reglages):
    assert v.regle_inconnu(ctx(reglages, fiche())) is None
    assert v.regle_inconnu(ctx(reglages, fiche(signature="app_store", editeur=None))) is None
    homebrew = fiche(label="homebrew.mxcl.redis", signature="adhoc", editeur=None)
    assert v.regle_inconnu(ctx(reglages, homebrew, connaissance=kb("homebrew.mxcl.redis"))) is None
    systeme_connu = fiche(label="com.if.Amphetamine", signature="apple", details={"programme_systeme": True})
    assert v.regle_inconnu(ctx(reglages, systeme_connu, connaissance=kb("com.if.Amphetamine"))) is None
    assert v.regle_inconnu(ctx(reglages, fiche(source="extension", programme=None, equipe="AB12CD34EF"))) is None
    assert (
        v.regle_inconnu(ctx(reglages, fiche(source="extension", programme=None, signature="inconnue"))).code
        == "inconnu"
    )


def test_un_inconnu_n_est_jamais_a_supprimer(reglages):
    for source in ("agent_utilisateur", "agent_global", "ouverture", "cron", "assistant_privilegie"):
        f = fiche(source=source, signature="non_signe", editeur=None, programme_existe=False)
        assert v.juger(ctx(reglages, f, impact=90.0, utilite="faible")).action == "verifier"


# --- inactif, mise à jour, lourd et inutile, utile ---------------------------------------------------------------


def test_inactif(reglages):
    assert v.regle_inactif(ctx(reglages, fiche(actif=False, desactive=True))).raison == "déjà désactivé"
    assert "pas activé" in v.regle_inactif(ctx(reglages, fiche(actif=False, desactive=False))).raison
    assert v.regle_inactif(ctx(reglages, fiche(actif=False))).action == "aucune"
    assert v.regle_inactif(ctx(reglages, fiche(actif=None))) is None


def test_mise_a_jour(reglages):
    assert v.regle_mise_a_jour(ctx(reglages, fiche(label="com.vendeur.Updater"))).code == "inutile"
    assert v.regle_mise_a_jour(ctx(reglages, fiche(programme="/opt/x/SoftwareUpdateAgent"))).code == "inutile"
    assert v.regle_mise_a_jour(ctx(reglages, fiche(label="com.google.keystone.agent"),
                                   connaissance=kb("com.google.keystone.agent"))).code == "inutile"  # fmt: skip
    # Négatifs : un « helper » n'est pas une mise à jour ; la base de connaissances l'emporte sur les motifs.
    assert v.regle_mise_a_jour(ctx(reglages, fiche(label="com.docker.helper"))) is None
    assert (
        v.regle_mise_a_jour(ctx(reglages, fiche(label="com.x.updater"), connaissance=kb("com.docker.socket"))) is None
    )


def test_lourd_inutile(reglages):
    seuil = reglages["verdicts"]["impact_significatif"]
    assert v.regle_lourd_inutile(ctx(reglages, impact=seuil, utilite="faible")).code == "inutile"
    assert v.regle_lourd_inutile(ctx(reglages, impact=seuil - 0.1, utilite="faible")) is None
    assert v.regle_lourd_inutile(ctx(reglages, impact=90, utilite="forte")) is None
    assert v.regle_lourd_inutile(ctx(reglages, impact=90, utilite="inconnue")) is None


def test_utile(reglages):
    assert v.regle_utile(ctx(reglages, impact=1.0)).raison == "impact négligeable"
    assert v.regle_utile(ctx(reglages, impact=50.0, utilite="forte")).raison.startswith("utile")
    assert "à toi de voir" in v.regle_utile(ctx(reglages, impact=50.0, utilite="inconnue")).raison
    assert v.regle_utile(ctx(reglages, fiche(source="agent_global"), impact=1.0)).action == "instructions"


# --- l'ordre, la configuration, les mentions ---------------------------------------------------------------------


def test_ordre_configurable_et_regle_inconnue(reglages):
    f = fiche(label="com.x.updater", signature="non_signe", editeur=None)
    assert v.juger(ctx(reglages, f)).code == "inconnu"  # inconnu passe avant mise à jour
    reglages["verdicts"]["ordre"] = ["absente", "mise_a_jour", "inconnu"]
    verdict = v.juger(ctx(reglages, f))
    assert verdict.code == "inutile" and verdict.regle == "mise_a_jour"
    reglages["verdicts"]["ordre"] = []
    assert v.juger(ctx(reglages, fiche())).regle == "défaut"


def test_mentions(reglages):
    f = fiche(declencheurs=Declencheurs(garder_en_vie=True), details={"relances": 50, "dernier_code": 3}, doublon=True,
              c_est_moi=True)  # fmt: skip
    m = Metriques(veille=0.5, releves=10)
    assert v.drapeaux(ctx(reglages, f, metriques=m)) == ["empêche la veille", "relancé en boucle (il plante)",
                                                          "label en double", "c'est moi"]  # fmt: skip
    assert v.drapeaux(ctx(reglages)) == []
    assert v.Verdict("orphelin", "r", "quarantaine").emoji == "👻" and "Orphelin" in v.Verdict("orphelin", "", "").titre
