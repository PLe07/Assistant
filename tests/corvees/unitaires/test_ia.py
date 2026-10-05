"""La couche IA, avec un Claude imité : schéma, relance, essais, quota, budget, une demande par jour."""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest import mock
from zoneinfo import ZoneInfo

import pytest

from core.cerveau import ClaudeIndisponible, PlafondAtteint
from modules.corvees import ia
from modules.corvees.normalize import mois_de

PARIS = ZoneInfo("Europe/Paris")
SOIR = datetime(2026, 10, 5, 21, 0, tzinfo=PARIS).timestamp()
LENDEMAIN = SOIR + 86400


def candidat(n, **en_plus):
    c = {
        "id": f"id{n:04d}",
        "signature": f"sig{n}",
        "type": "fichiers",
        "tokens": [f"fmove:Downloads→Documents/Factures{n} [pdf, Facture_*]"],
        "occurrences": 12,
        "jours_distincts": 10,
        "duree_moyenne_s": 60.0,
        "regularite": 0.0,
        "lift": 99.0,
        "frequence_mois": 12.9,
        "minutes_mois": 12.9,
        "score": 100.0 - n,
        "premiere": 1788814111.9,
        "derniere": 1790965831.0,
        "details": {"origine": "fcreate:Downloads [pdf, Facture_*]"},
        "exemples": ["lun. 28/09 16:34"],
    }
    c.update(en_plus)
    return c


def description(id_, **en_plus):
    d = {
        "id": id_,
        "titre_court": "Ranger les factures",
        "description_fr": "Tu ranges tes factures à la main chaque semaine.",
        "pourquoi_corvee": "Toujours les mêmes gestes.",
        "solution": {
            "type": "tache_launchd",
            "explication": "Une tâche range les factures.",
            "script": 'mv -n "$HOME"/Downloads/Facture_*.pdf "$HOME"/Documents/Factures/',
            "installation_pas_a_pas": ["Lis le script.", "Installe-le."],
            "risques": "Aucun.",
        },
        "gain_minutes_mois": 12.0,
        "difficulte": "facile",
        "confiance": 0.8,
    }
    d.update(en_plus)
    return d


def reponse(donnees, entree=3000, sortie=800):
    return SimpleNamespace(texte=json.dumps(donnees), donnees=donnees, tokens_entree=entree, tokens_sortie=sortie)


class FauxClaude:
    """Joue un scénario : chaque élément est une réponse (dict → JSON) ou une exception à lever."""

    def __init__(self, *scenario):
        self.scenario = list(scenario)
        self.appels = []

    def __call__(self, message, **options):
        self.appels.append((message, options))
        suite = self.scenario.pop(0)
        if isinstance(suite, Exception):
            raise suite
        if callable(suite):
            suite = suite(message)
        return reponse(suite)


def envoyees(message):
    return json.loads(message[len(ia.CONSIGNES) :].split("\n\nTa réponse")[0])


def tout_decrire(message):
    """Répond pour chaque corvée présente dans le message."""
    ids = [c["id"] for c in envoyees(message)]
    return {"corvees": [description(i) for i in ids]}


def lancer(base, reglages, candidats, faux, maintenant=SOIR, pause=0.0):
    attentes, journal = [], []
    resultat = ia.decrire(
        base,
        candidats,
        reglages,
        maintenant,
        demander=faux,
        dormir=attentes.append,
        pause_restante=lambda: pause,
        journal=journal.append,
    )
    return resultat, attentes, journal


def test_ce_qui_part_chez_claude_est_resume_et_caviarde():
    c = candidat(1, tokens=["cmd:mysql -u moi -p hunter2 --host db.exemple.fr", "url:site.fr/?jeton=abc"])
    c["details"]["creneau"] = "08:30"
    c["details"]["jour_semaine"] = "lundi"
    r = ia.resume(c)
    assert set(r) == {
        "id",
        "type",
        "etapes",
        "fois_par_mois",
        "jours_distincts",
        "duree_moyenne_s",
        "minutes_par_mois",
        "heure_habituelle",
        "jour",
        "fichier_apparu_avant",
    }
    assert "hunter2" not in json.dumps(r) and r["heure_habituelle"] == "08:30" and r["jour"] == "lundi"
    texte = ia.message([c])
    for absent in ("1788814111", "1790965831", "sig1", "28/09", "exemples", "signature", "lift"):
        assert absent not in texte
    assert texte.startswith(ia.CONSIGNES)


def test_le_schema_envoye_n_a_pas_de_bornes_mais_les_memes_champs():
    envoye = ia.schema_pour_claude()
    texte = json.dumps(envoye)
    assert all(b not in texte for b in ("maxLength", "minLength", "minimum", "maximum", "maxItems"))
    assert (
        envoye["properties"]["corvees"]["items"]["required"] == ia.SCHEMA["properties"]["corvees"]["items"]["required"]
    )
    assert "maxLength" in json.dumps(ia.SCHEMA)  # vérifiées ici


def test_validation():
    ids = {"a", "b"}
    trouvees, erreurs = ia.valider({"corvees": [description("a"), description("b")]}, ids)
    assert set(trouvees) == ids and erreurs == []
    trouvees, erreurs = ia.valider({"corvees": [description("a"), description("zzz")]}, ids)
    assert set(trouvees) == {"a"} and erreurs == ["id inconnu : zzz", "corvées oubliées : b"]
    mauvaise = description("a", difficulte="difficile", confiance=3)
    trouvees, erreurs = ia.valider({"corvees": [mauvaise]}, ids)
    assert trouvees == {} and len(erreurs) == 2 and all("corvees/0" in e for e in erreurs)
    assert ia.valider(None, ids)[0] == {} and ia.valider({"autre": 1}, ids)[1]
    sans_script = description("a")
    del sans_script["solution"]["script"]
    assert "script" in ia.valider({"corvees": [sans_script]}, ids)[1][0]


def test_une_demande_reussie(base, reglages):
    faux = FauxClaude(tout_decrire)
    cands = [candidat(1), candidat(2)]
    resultat, attentes, journal = lancer(base, reglages, cands, faux)
    assert len(faux.appels) == 1 and attentes == []
    message, options = faux.appels[0]
    assert options["module"] == "corvees" and options["modele"] == "rapide" and options["essais"] == 1
    assert options["schema"] == ia.schema_pour_claude() and options["systeme"] == ia.SYSTEME
    assert {d["source"] for d in resultat.values()} == {"claude"} and set(resultat) == {"sig1", "sig2"}
    attendu = 3000 * 1.0 / 1e6 + 800 * 5.0 / 1e6
    assert base.cout_du_mois(mois_de(SOIR)) == pytest.approx(attendu)
    assert base.lire("ia_derniere_demande") == SOIR
    assert any("Claude a décrit 2 corvée(s)" in m for m in journal)
    assert base.descriptions()["sig1"]["titre_court"] == "Ranger les factures"


def test_une_seule_demande_par_jour_et_celles_deja_decrites_ne_repartent_pas(base, reglages):
    lancer(base, reglages, [candidat(1)], FauxClaude(tout_decrire))
    faux = FauxClaude(tout_decrire)
    resultat, _, journal = lancer(base, reglages, [candidat(1), candidat(2)], faux, SOIR + 3600)
    assert faux.appels == []  # même jour : pas de deuxième demande
    assert resultat["sig1"]["source"] == "claude" and resultat["sig2"]["source"] == "locale"
    assert any("déjà une demande" in m for m in journal)
    resultat, _, _ = lancer(base, reglages, [candidat(1), candidat(2)], faux := FauxClaude(tout_decrire), LENDEMAIN)
    assert len(faux.appels) == 1 and "id0001" not in faux.appels[0][0] and "id0002" in faux.appels[0][0]
    assert resultat["sig2"]["source"] == "claude"
    resultat, _, _ = lancer(base, reglages, [candidat(1)], faux := FauxClaude(), LENDEMAIN + 86400)
    assert faux.appels == [] and resultat["sig1"]["source"] == "claude"  # rien de nouveau : pas de demande


def test_au_plus_8_corvees_par_demande(base, reglages):
    faux = FauxClaude(tout_decrire)
    cands = [candidat(i) for i in range(11)]
    resultat, _, _ = lancer(base, reglages, cands, faux)
    parties = envoyees(faux.appels[0][0])
    assert len(parties) == 8 and [c["id"] for c in parties] == [f"id{i:04d}" for i in range(8)]
    sources = [resultat[f"sig{i}"]["source"] for i in range(11)]
    assert sources == ["claude"] * 8 + ["locale"] * 3


def test_json_hors_schema_une_relance_de_correction(base, reglages):
    faux = FauxClaude({"corvees": [{"id": "id0001"}]}, tout_decrire)
    resultat, _, journal = lancer(base, reglages, [candidat(1)], faux)
    assert len(faux.appels) == 2 and "ne respectait pas le format" in faux.appels[1][0]
    assert "corvees/0" in faux.appels[1][0] and resultat["sig1"]["source"] == "claude"
    assert any("relance de correction" in m for m in journal)


def test_json_toujours_hors_schema_description_locale(base, reglages):
    faux = FauxClaude({"pas": "ça"}, {"toujours": "pas"})
    resultat, _, journal = lancer(base, reglages, [candidat(1)], faux)
    assert len(faux.appels) == 2 and resultat["sig1"]["source"] == "locale"
    assert any("toujours hors format" in m for m in journal)


def test_une_corvee_oubliee_par_claude_est_decrite_sur_place(base, reglages):
    faux = FauxClaude({"corvees": [description("id0001")]})
    resultat, _, _ = lancer(base, reglages, [candidat(1), candidat(2)], faux)
    assert len(faux.appels) == 1
    assert resultat["sig1"]["source"] == "claude" and resultat["sig2"]["source"] == "locale"


def test_delai_depasse_puis_surcharge_puis_reussite(base, reglages):
    faux = FauxClaude(
        ClaudeIndisponible("Claude n'a pas répondu en 180 s."),
        ClaudeIndisponible("Claude Code a renvoyé une erreur : API Error: 529 Overloaded"),
        tout_decrire,
    )
    resultat, attentes, journal = lancer(base, reglages, [candidat(1)], faux)
    assert len(faux.appels) == 3 and attentes == [20, 40] and resultat["sig1"]["source"] == "claude"
    assert sum("essai" in m for m in journal) == 2
    lignes = base.db.execute("SELECT ok FROM couts ORDER BY id").fetchall()
    assert [ok for (ok,) in lignes] == [0, 0, 1]


def test_trois_pannes_500_description_locale(base, reglages):
    erreur = ClaudeIndisponible("Claude Code a renvoyé une erreur : API Error: 500 Internal server error")
    faux = FauxClaude(erreur, erreur, erreur)
    resultat, attentes, journal = lancer(base, reglages, [candidat(1)], faux)
    assert len(faux.appels) == 3 and attentes == [20, 40] and resultat["sig1"]["source"] == "locale"
    assert any("Claude indisponible" in m for m in journal)
    assert base.lire("ia_derniere_demande") == SOIR  # la demande du jour a eu lieu (sans succès)


def test_quota_429_on_attend_la_fin_de_la_pause_de_l_assistant(base, reglages):
    quota = ClaudeIndisponible("Quota de l'abonnement atteint : nouvel essai dans 15 min.")
    quota.pause = True
    faux = FauxClaude(quota, tout_decrire)
    resultat, attentes, _ = lancer(base, reglages, [candidat(1)], faux, pause=900.0)
    assert attentes == [905.0] and resultat["sig1"]["source"] == "claude"
    faux = FauxClaude(quota, quota, quota)
    _, attentes, _ = lancer(base, reglages, [candidat(2)], faux, LENDEMAIN, pause=4000.0)
    assert attentes == [960.0, 960.0]  # jamais plus de 16 minutes


@pytest.mark.parametrize(
    "erreur",
    [
        ClaudeIndisponible("Jeton Claude absent du .env de l'assistant."),
        ClaudeIndisponible("Claude Code est introuvable (curl …)."),
        PlafondAtteint("Plafond de 50 appels à Claude atteint pour aujourd'hui."),
    ],
)
def test_une_erreur_de_reglage_n_est_pas_reessayee(base, reglages, erreur):
    faux = FauxClaude(erreur)
    resultat, attentes, _ = lancer(base, reglages, [candidat(1)], faux)
    assert len(faux.appels) == 1 and attentes == [] and resultat["sig1"]["source"] == "locale"


def test_une_panne_imprevue_n_est_pas_reessayee(base, reglages):
    faux = FauxClaude(ValueError("bogue"))
    resultat, _, journal = lancer(base, reglages, [candidat(1)], faux)
    assert len(faux.appels) == 1 and resultat["sig1"]["source"] == "locale"
    assert any("ValueError : bogue" in m for m in journal)


def test_trop_d_etapes_n_est_pas_reessaye(base, reglages):
    erreur = ClaudeIndisponible("max turns")
    erreur.definitif = True
    faux = FauxClaude(erreur)
    lancer(base, reglages, [candidat(1)], faux)
    assert len(faux.appels) == 1


def test_budget_du_mois_atteint(base, reglages):
    base.noter_cout(mois_de(SOIR), "haiku", 0, 0, 1.995, True, SOIR - 86400)
    faux = FauxClaude()
    resultat, _, journal = lancer(base, reglages, [candidat(1)], faux)
    assert faux.appels == [] and resultat["sig1"]["source"] == "locale"
    assert any("budget du mois atteint" in m and "sur 2.00 $" in m for m in journal)
    debut_novembre = datetime(2026, 11, 1, 21, 0, tzinfo=PARIS).timestamp()
    faux = FauxClaude(tout_decrire)
    resultat, _, _ = lancer(base, reglages, [candidat(1)], faux, debut_novembre)
    assert len(faux.appels) == 1 and resultat["sig1"]["source"] == "claude"  # nouveau mois, nouveau budget


def test_modele_fort_et_son_tarif(base, reglages):
    reglages["ia"]["modele"] = "fort"
    faux = FauxClaude(tout_decrire)
    lancer(base, reglages, [candidat(1)], faux)
    assert faux.appels[0][1]["modele"] == "fort"
    assert base.cout_du_mois(mois_de(SOIR)) == pytest.approx(3000 * 2.0 / 1e6 + 800 * 10.0 / 1e6)


def test_claude_coupe_dans_les_reglages(base, reglages):
    reglages["ia"]["actif"] = False
    faux = FauxClaude()
    resultat, _, journal = lancer(base, reglages, [candidat(1)], faux)
    assert faux.appels == [] and resultat["sig1"]["source"] == "locale" and any("coupé" in m for m in journal)


def test_le_texte_de_claude_est_caviarde_avant_d_etre_ecrit(base, reglages):
    d = description(
        "id0001", description_fr="Écris à jean.dupont@exemple.fr avec le jeton sk-ant-api03-abcdefghijklmnop"
    )
    faux = FauxClaude({"corvees": [d]})
    resultat, _, _ = lancer(base, reglages, [candidat(1)], faux)
    texte = resultat["sig1"]["description_fr"]
    assert "jean.dupont" not in texte and "sk-ant" not in texte
    brut = base.db.execute("SELECT donnees FROM descriptions").fetchone()[0]
    assert "jean.dupont" not in brut


def test_sans_imitation_c_est_le_cerveau_de_l_assistant_qui_est_appele(base, reglages):
    with mock.patch("core.cerveau.demander", side_effect=FauxClaude(tout_decrire)) as vrai:
        resultat = ia.decrire(base, [candidat(1)], reglages, SOIR)
    assert vrai.call_count == 1 and resultat["sig1"]["source"] == "claude"


def test_la_pause_de_l_assistant_est_lue_dans_son_etat():
    with mock.patch("core.etat.lire", return_value=10**12):
        assert ia._pause_restante() > 0
    with mock.patch("core.etat.lire", return_value=None):
        assert ia._pause_restante() == 0.0
    with mock.patch("core.etat.lire", side_effect=OSError("illisible")):
        assert ia._pause_restante() == 0.0


def test_estimation_prudente():
    assert ia.estimation("x" * 3000, 8, {"entree": 1.0, "sortie": 5.0}) > ia.cout(
        5000, 7000, {"entree": 1.0, "sortie": 5.0}
    )


@pytest.mark.live
def test_vrai_claude_deux_corvees(base, reglages):
    """Un vrai appel (moins d'un centime) : python -m pytest -m live tests/corvees/unitaires/test_ia.py"""
    from core.cerveau import demander

    cands = [candidat(1), candidat(2, tokens=["cmd:cd ~/Projets/x && git pull && make"], type="shell")]
    resultat = ia.decrire(base, cands, reglages, SOIR, demander=demander)
    assert {d["source"] for d in resultat.values()} == {"claude"}, resultat
    assert base.cout_du_mois(mois_de(SOIR)) < 0.01
    texte = " ".join(d["description_fr"] for d in resultat.values()).lower()
    assert any(mot in texte.split() for mot in ("tu", "les", "des", "dans", "le", "la")), texte
