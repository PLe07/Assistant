"""L'assemblage de l'analyse : impact estimé, élément inactif, noms lisibles, éditeur affiché, classement."""

from modules.demarrage.analyse import Bilan, analyser, nom_lisible
from modules.demarrage.analyse.connaissances import trouver
from modules.demarrage.db import Base
from modules.demarrage.modele import Fiche, Inventaire


def fiche(id_, label, **k):
    base = {"source": "agent_utilisateur", "programme": f"/opt/{id_}", "programme_existe": True,
            "signature": "developpeur", "editeur": "Éditeur", "actif": True}  # fmt: skip
    base.update(k)
    return Fiche(id=id_, label=label, **base)


def test_analyse_sans_mesure(tmp_path, reglages):
    b = Base(tmp_path / "d.db")
    fiches = [
        fiche("a", "com.tinyspeck.slackmacgap"),  # connu, pas mesuré : impact typique « estimé »
        fiche("b", "com.zebre.agent"),  # inconnu de la base : 0, mesuré ou pas
        fiche("c", "com.epicgames.launcher", actif=False, desactive=True),  # inactif : 0
        fiche("d", "com.apple.x", source="apple", est_apple=True, editeur=None, signature="apple"),
        fiche("e", "com.docker.vmnetd", editeur=None, details={"editeur_btm": "Docker Inc"}),
        fiche("f", "com.zebre.ext", source="extension", editeur=None, equipe="AB12CD34EF", programme=None),
    ]
    inventaire = Inventaire(ts=1.0, fiches=fiches)
    b.enregistrer_scan(inventaire)
    bilan = analyser(inventaire, b, reglages, 2.0)
    b.fermer()
    par_id = {e.fiche.id: e for e in bilan.elements}
    assert par_id["a"].impact == reglages["scores"]["impact_estime"]["moyen"] and par_id["a"].impact_estime
    assert par_id["a"].nom == "Slack" and par_id["a"].role.startswith("La messagerie")
    assert par_id["b"].impact == 0.0 and not par_id["b"].impact_estime and "on ne devine pas" in par_id["b"].role
    assert par_id["c"].impact == 0.0 and par_id["c"].verdict.action == "aucune"
    assert par_id["d"].editeur == "Apple" and bilan.apple == [par_id["d"]] and bilan.elements[-1] is par_id["d"]
    assert par_id["e"].editeur == "Docker Inc" and par_id["f"].editeur == "équipe AB12CD34EF"
    assert par_id["a"].premiere_vue == 1.0
    assert {e.fiche.id for e in bilan.classement[:2]} == {"a", "e"}  # impacts estimés égaux (12), en tête
    assert bilan.classement[0].nom < bilan.classement[1].nom  # à égalité : par nom
    assert par_id["c"] not in bilan.actifs() and par_id["a"] in bilan.actifs()
    assert bilan.couteux(reglages) == []  # un impact estimé ne compte pas comme « coûte vraiment »
    assert bilan.element("b") is par_id["b"] and bilan.element("zz") is None
    assert isinstance(bilan, Bilan)


def test_noms_lisibles():
    connue = trouver(Fiche(id="i", label="com.google.keystone.agent", source="agent_utilisateur"))
    assert nom_lisible(Fiche(id="i", label="com.google.keystone.agent", source="agent_utilisateur"), connue).startswith(
        "Google"
    )
    icloud = trouver(Fiche(id="i", label="com.apple.bird", source="apple"))
    assert nom_lisible(Fiche(id="i", label="com.apple.bird", source="apple"), icloud) == "com.apple.bird"
    assert nom_lisible(Fiche(id="i", label="x", source="ouverture", nom="Mon App"), None) == "Mon App"
    assert (
        nom_lisible(Fiche(id="i", label="x", source="ouverture", app_parente="/Applications/Café.app"), None) == "Café"
    )
    assert nom_lisible(Fiche(id="i", label="com.x", source="agent_utilisateur"), None) == "com.x"
