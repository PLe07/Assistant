"""Les détecteurs, un par un, sur de petits cas construits à la main."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from modules.corvees import config
from modules.corvees.db import Evenement
from modules.corvees.detection import fichiers, memoire, moteur, ponts, routines, scoring, sequences, shell
from modules.corvees.detection.flux import Candidat, preparer

PARIS = ZoneInfo("Europe/Paris")
R, _ = config.charger({})


def ts(jour, h, m=0, s=0):
    """Le jour j de septembre 2026 (le 7 est un lundi) à h:m:s, heure de Paris."""
    return datetime(2026, 9, jour, h, m, s, tzinfo=PARIS).timestamp()


def e(t, token, **attrs):
    kind = token.split(":", 1)[0]
    return Evenement(t, "test", kind, token, attrs)


def suite(debut, tokens, pas=20):
    return [e(debut + i * pas, t) for i, t in enumerate(tokens)]


# --- Le flux ---------------------------------------------------------------------------------------------


def test_sessions_coupees_par_une_pause_l_inactivite_et_minuit():
    evts = (
        suite(ts(7, 9), ["app:A", "app:B"])
        + suite(ts(7, 9, 30), ["app:C"])  # 30 min plus tard : nouvelle session
        + [e(ts(7, 9, 31), "inactif")]
        + suite(ts(7, 9, 32), ["app:D"])  # après une inactivité : nouvelle session
        + suite(ts(7, 23, 59, 50), ["app:E"])
        + suite(ts(8, 0, 0, 5), ["app:F"])  # minuit : nouvelle session
    )
    flux = preparer(evts, 10)
    assert [[flux.vocab[t] for t in s.ids] for s in flux.sessions] == [
        ["app:A", "app:B"],
        ["app:C"],
        ["app:D"],
        ["app:E"],
        ["app:F"],
    ]


def test_repetitions_immediates_et_titres_de_fenetres_ignores():
    flux = preparer(suite(ts(7, 9), ["app:A", "app:A", "fen:A:titre", "app:B"]), 10)
    assert [flux.vocab[t] for t in flux.sessions[0].ids] == ["app:A", "app:B"]
    assert flux.jours_observes == 1 and preparer([], 10).sessions == []


def test_identifiant_stable_et_export():
    c = Candidat("fichiers", ("fmove:a",), 4, 3, [1.0, 2.0], [0.0, 0.0])
    assert c.id == Candidat("fichiers", ("fmove:a",), 9, 9, [], []).id and len(c.id) == 6
    assert c.id != Candidat("pont", ("fmove:a",), 4, 3, [], []).id
    x = c.exporter()
    assert {
        "id",
        "signature",
        "type",
        "tokens",
        "occurrences",
        "jours_distincts",
        "duree_moyenne_s",
        "regularite",
        "score",
        "premiere",
        "derniere",
        "details",
    } <= set(x)
    assert x["premiere"] == 1.0 and x["derniere"] == 2.0


# --- D1 : séquences -------------------------------------------------------------------------------------


def jours_avec(sequence, jours=(7, 8, 9, 10), parasite=None):
    """La séquence chaque jour, entourée d'actions toujours différentes (le bruit)."""
    evts = []
    for i, j in enumerate(jours):
        seq = list(sequence)
        if parasite and i % 2 == 0:
            seq.insert(2, parasite)
        avant, apres = [f"app:Avant{j}{k}" for k in range(2)], [f"app:Apres{j}{k}" for k in range(2)]
        evts += suite(ts(j, 10), avant + seq + apres)
    return evts


def test_d1_trouve_une_sequence_repetee_meme_avec_un_parasite():
    corvee = ["url:a.fr", "url:b.fr", "url:c.fr", "url:d.fr"]
    flux = preparer(jours_avec(corvee, parasite="url:pub.fr"), 10)
    trouves = {c.tokens for c in sequences.detecter(flux, R)}
    assert tuple(corvee) in trouves
    assert not any(set(t) < set(corvee) for t in trouves)  # seulement la séquence maximale


def test_d1_deux_parasites_c_est_trop():
    flux = preparer(jours_avec(["url:a.fr", "url:b.fr", "url:p1.fr", "url:p2.fr", "url:c.fr"], jours=(7, 8, 9)), 10)
    motifs = sequences.motifs_frequents(flux, 3, 8, 3, 1)
    noms = {tuple(flux.vocab[t] for t in m) for m in motifs}
    assert ("url:a.fr", "url:b.fr", "url:c.fr") not in noms


def test_d1_pas_assez_de_jours_distincts():
    flux = preparer(jours_avec(["url:a.fr", "url:b.fr", "url:c.fr"], jours=(7, 8)), 10)
    assert sequences.detecter(flux, R) == []


def test_d1_laisse_les_ponts_au_detecteur_de_ponts():
    flux = preparer(jours_avec(["app:Safari", "clip:Safari→Numbers", "app:Numbers"]), 10)
    assert all("clip:" not in " ".join(c.tokens) for c in sequences.detecter(flux, R))


def test_d1_ecarte_ce_qui_n_est_pas_plus_frequent_qu_au_hasard():
    r, _ = config.charger({"detection": {"sequences": {"lift_min": 10**12}}})
    flux = preparer(jours_avec(["url:a.fr", "url:b.fr", "url:c.fr"]), 10)
    assert sequences.detecter(flux, r) == []


# --- D2 : routines --------------------------------------------------------------------------------------


def test_creneau_et_concentration():
    regulier = [ts(j, 8, 30 + j) for j in range(7, 14)]
    assert routines.creneau(regulier, 45, 3, 0.6)["jours"] == 7
    eparpille = [ts(j, h) for j, h in zip(range(7, 14), (8, 11, 14, 17, 20, 9, 22), strict=True)]
    assert routines.creneau(eparpille, 45, 3, 0.6) is None
    assert routines.creneau([], 45, 3, 0.6) is None


def test_hebdomadaire_semaines_de_suite_et_meme_heure():
    lundis = [ts(7, 9), ts(14, 9, 10), ts(21, 9, 5)]
    assert routines.hebdomadaire(lundis, 3, 0.75)["jour_semaine"] == 0
    assert routines.hebdomadaire([ts(7, 9), ts(21, 9)], 3, 0.75) is None
    assert routines.hebdomadaire(lundis + [ts(8, 9), ts(9, 9)], 3, 0.75) is None  # pas assez concentré
    heures_variees = [ts(7, 8), ts(14, 13), ts(21, 19)]
    assert routines.hebdomadaire(heures_variees, 3, 0.75) is not None
    assert routines.hebdomadaire(heures_variees, 3, 0.75, tolerance_min=45) is None
    assert routines.hebdomadaire([], 3, 0.75) is None


def test_d2_routine_d_une_action_et_groupe_hebdomadaire():
    evts = [e(ts(j, 8, 55), "app:Spotify") for j in range(7, 21)]
    for lundi in (7, 14, 21):
        evts += [e(ts(lundi, 9, 20), "url:ent.fr"), e(ts(lundi, 9, 21), "url:moodle.fr")]
    flux = preparer(evts, 10)
    trouvees = {c.tokens: c for c in routines.detecter(flux, R, [])}
    assert trouvees[("app:Spotify",)].details["creneau"] == "08:55"
    assert trouvees[("url:ent.fr", "url:moodle.fr")].details["jour_semaine"] == "lundi"


def test_horaire_d_une_sequence():
    c = Candidat("sequence", ("a", "b"), 5, 5, [ts(j, 14, 10) for j in range(7, 12)], [5.0] * 5)
    routines.horaire(c, preparer([e(ts(j, 14), "app:A") for j in range(7, 12)], 10), R)
    assert c.details["creneau"] == "14:10" and c.regularite > 0


# --- D3 : fichiers --------------------------------------------------------------------------------------


def parcours(jour, nom="Facture_x.pdf"):
    debut = ts(jour, 15)
    return [
        e(debut, "fcreate:Downloads [pdf, Facture_*]", fichier=f"f{jour}"),
        e(debut + 60, "fren:Downloads [pdf, Facture_*→Fact_*]", avant=f"f{jour}", fichier=f"g{jour}"),
        e(debut + 90, "fmove:Downloads→Documents/Factures [pdf, Fact_*]", avant=f"g{jour}", fichier=f"h{jour}"),
    ]


def test_d3_relie_les_etapes_d_un_meme_fichier():
    flux = preparer([x for j in (7, 8, 9, 10) for x in parcours(j)], 10)
    (c,) = fichiers.detecter(flux, R)
    assert c.tokens == ("fren:Downloads [pdf, Facture_*→Fact_*]", "fmove:Downloads→Documents/Factures [pdf, Fact_*]")
    assert c.occurrences == 4 and c.details["origine"] == "fcreate:Downloads [pdf, Facture_*]"
    assert len(fichiers.chaines(flux)) == 4


def test_d3_un_telechargement_seul_n_est_pas_une_corvee_et_il_faut_4_fois():
    flux = preparer([e(ts(j, 15), "fcreate:Downloads [pdf, Facture_*]", fichier=f"f{j}") for j in range(7, 14)], 10)
    assert fichiers.detecter(flux, R) == []
    flux = preparer([x for j in (7, 8, 9) for x in parcours(j)], 10)
    assert fichiers.detecter(flux, R) == []


def test_d3_variantes_reunies_sous_leur_prefixe_commun():
    evts = [
        e(ts(7 + i, 15), f"fconv:Documents/Lettres [docx→pdf, Lettre_motivation_{b}]", fichier=f"x{i}")
        for i, b in enumerate(["BNP", "SG", "CIC", "LCL", "SG"])
    ]
    (c,) = fichiers.detecter(preparer(evts, 10), R)
    assert c.tokens == ("fconv:Documents/Lettres [docx→pdf, Lettre_motivation_*]",) and c.occurrences == 5


def test_d3_pas_de_regle_sans_debut_de_nom_commun():
    evts = [
        e(ts(7 + i, 15), f"fmove:Downloads→Documents [pdf, {n}]", fichier=f"x{i}")
        for i, n in enumerate(["budget", "cours", "photo", "scan", "td"])
    ]
    assert fichiers.detecter(preparer(evts, 10), R) == []


@pytest.mark.parametrize(
    ("token", "racine"),
    [
        ("fmove:A→B [pdf, Devoir_Eco_*]", "fmove:A→B [pdf, Devoir_*]"),
        ("fren:A [pdf, Scan_*→Cours_fiscalite_*]", "fren:A [pdf, Scan_*→Cours_*]"),
        ("fmove:A→B [pdf, Facture_*]", "fmove:A→B [pdf, Facture_*]"),
        ("fmove:A→B [pdf, README]", "fmove:A→B [pdf, README]"),
        ("app:Safari", "app:Safari"),
    ],
)
def test_racine(token, racine):
    assert fichiers.racine(token) == racine


def test_squelette_et_prefixe_commun():
    assert fichiers.squelette("fren:A [pdf, x_*→y_*]") == "fren:A [pdf, *→*]"
    assert fichiers.squelette("app:Safari") == "app:Safari"
    assert fichiers.prefixe_commun(["Lettre_motivation_BNP", "Lettre_motivation_SG"]) == "Lettre_motivation_*"
    assert fichiers.prefixe_commun(["abc", "xyz"]) == "*"


# --- D4 : ponts -----------------------------------------------------------------------------------------


def test_queue_de_poisson():
    assert ponts.queue_poisson(0, 3.0) == 1.0
    assert ponts.queue_poisson(1, 3.0) == pytest.approx(1 - 2.718281828**-3)
    assert ponts.queue_poisson(30, 3.0) < 1e-15


def test_d4_un_vrai_pont_contre_le_hasard():
    import random

    h = random.Random(1)
    evts = [e(ts(7 + i % 10, 10, i), "clip:Safari→Numbers") for i in range(12)]
    applis = [f"App{k}" for k in range(8)]
    evts += [e(ts(7 + i % 10, 11, i % 60), f"clip:{h.choice(applis)}→{h.choice(applis)}") for i in range(80)]
    trouves = {c.tokens for c in ponts.detecter(preparer(evts, 10), R)}
    assert trouves == {("clip:Safari→Numbers",)}


# --- D5 : commandes -------------------------------------------------------------------------------------


def test_d5_ligne_enchainee_et_suite_de_commandes():
    evts = []
    for j in range(7, 12):
        evts.append(e(ts(j, 21), "cmd:cd ~/x && git pull && python main.py"))
        evts += suite(ts(j, 15), ["cmd:git add .", 'cmd:git commit -m "*"', "cmd:git push"])
        evts.append(e(ts(j, 16), f"cmd:ls {j}"))
    trouves = {c.tokens for c in shell.detecter(preparer(evts, 10), R)}
    assert ("cmd:cd ~/x && git pull && python main.py",) in trouves
    assert ("cmd:git add .", 'cmd:git commit -m "*"', "cmd:git push") in trouves


# --- Le score -------------------------------------------------------------------------------------------


def cand(type_, tokens, occ=10, jours=10, durees=None, **details):
    return Candidat(type_, tuple(tokens), occ, jours, [0.0] * occ, durees or [0.0] * occ, details=details)


def test_duree_par_etape_et_mesure_bornee():
    assert scoring.duree(cand("fichiers", ["fmove:x"]), R) == 20
    assert scoring.duree(cand("shell", ["cmd:a && b && c"]), R) == 24
    assert scoring.duree(cand("sequence", ["url:a", "url:b"], durees=[600.0] * 10), R) == 36  # 3 × 12 s
    assert scoring.duree(cand("sequence", ["url:a", "url:b"], durees=[15.0] * 10), R) == 15


def test_facteurs():
    fichier = scoring.scorer(cand("fichiers", ["fmove:x"]), R, 30)
    instantane = scoring.scorer(cand("routine", ["app:Spotify"]), R, 30)
    navigation = scoring.scorer(cand("sequence", ["app:A", "url:b", "clip:A→B"]), R, 30)
    routine = scoring.scorer(cand("routine", ["app:A", "url:b", "clip:A→B"], creneau="08:00"), R, 30)
    pont = scoring.scorer(cand("pont", ["clip:A→B"]), R, 30)
    assert fichier.score > 0 and instantane.score < fichier.score / 10
    assert navigation.score < routine.score / 5 and pont.score > 0
    assert fichier.frequence_mois == 10 and fichier.minutes_mois == pytest.approx(10 * 20 / 60)


# --- La mémoire des décisions ---------------------------------------------------------------------------


def test_cles_et_correspondance():
    assert memoire.cles(["app:Mail", "clip:Mail→Excel", "app:Excel"]) == {"clip:Mail→Excel"}
    assert memoire.cles(["app:A", "app:B"]) == {"app:A", "app:B"}
    decision = {"tokens": ["app:Safari", "clip:Mail→Excel", "app:Excel"]}
    assert memoire.correspond({"signature": "x", "tokens": ["clip:Mail→Excel"]}, decision, "y")
    assert memoire.correspond({"signature": "y", "tokens": ["autre"]}, decision, "y")
    assert not memoire.correspond({"signature": "x", "tokens": ["fmove:z"]}, decision, "y")
    assert not memoire.correspond({"signature": "x", "tokens": []}, decision, "y")


def test_frequence_des_etapes_cles():
    assert memoire.frequence({"clip:A→B": 10}, 30, ["app:A", "clip:A→B"]) == 10
    assert memoire.frequence({}, 30, []) == 0


def test_filtrer_refus_report_acceptation():
    c = {"signature": "s", "tokens": ["clip:A→B"], "frequence_mois": 10}
    assert memoire.filtrer([c], {}, 0) == [c]
    refus = {"s": {"statut": "reject", "frequence_ref": 8, "tokens": ["clip:A→B"]}}
    assert memoire.filtrer([c], refus, 0) == []
    assert memoire.filtrer([c], refus, 0, lambda tokens: 30)[0]["revenue"].startswith("Tu l'avais refusée")
    report = {"s": {"statut": "snooze", "jusqua": 100, "tokens": []}}
    assert memoire.filtrer([c], report, 50) == [] and memoire.filtrer([c], report, 150) == [c]
    assert memoire.filtrer([c], {"s": {"statut": "accept", "tokens": []}}, 0) == []


# --- Le moteur ------------------------------------------------------------------------------------------


def test_meme_corvee_et_fusion():
    a = Candidat("pont", ("clip:A→B",), 20, 20, [ts(7 + i % 20, 10) for i in range(20)], [0.0] * 20)
    b = Candidat("sequence", ("app:A", "clip:A→B", "app:B"), 8, 8, [ts(7 + i, 10) for i in range(8)], [30.0] * 8)
    autre = Candidat("sequence", ("app:A", "clip:A→B", "app:B"), 8, 8, [ts(7 + i, 18) for i in range(8)], [30.0] * 8)
    assert moteur.meme_corvee(a, b) and not moteur.meme_corvee(a, autre)
    assert not moteur.meme_corvee(a, Candidat("fichiers", ("fmove:x",), 4, 4, [], []))
    for c in (a, b):
        scoring.scorer(c, R, 30)
    flux = preparer([e(ts(7, 10), "app:A")], 10)
    (seul,) = moteur.fusionner([a, b], R, flux)
    assert seul.type == "pont" and "pont" in seul.details["vu_par"] and len(seul.details["vu_par"]) == 2


def test_analyser_de_bout_en_bout_avec_un_refus():
    evts = [x for j in range(7, 19) for x in parcours(j)]
    resultat = moteur.analyser(evts, R, maintenant=ts(19, 0))
    assert len(resultat) == 1 and resultat[0]["type"] == "fichiers" and len(resultat[0]["exemples"]) == 3
    c = resultat[0]
    refus = {c["signature"]: {"statut": "reject", "frequence_ref": c["frequence_mois"], "tokens": c["tokens"]}}
    assert moteur.analyser(evts, R, refus, maintenant=ts(19, 0)) == []
    assert moteur.frequence_actuelle(evts, R, c["tokens"], ts(19, 0)) > 0
