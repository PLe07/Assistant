"""Un tableau de bord prêt à servir, pour les tests de la page : quatre modules (🟢 🔴 🟡 ⚪), une semaine
d'historique, une erreur brute qui contient un e-mail et un chemin personnel, un code changé, des crédits."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tableau import config
from tableau.analyse.alertes import Alertes
from tableau.analyse.integrite import Gardien
from tableau.db import Base
from tableau.module import Attente, DefModule, EtatModule, Pastille, Probleme
from tableau.notifier import NotificateurMemoire
from tableau.vues import Source

MAINTENANT = 1791360000.0  # mercredi 7 octobre 2026, 10:00 à Paris
JETON = "jeton-de-test-" + "x" * 32
ERREUR_BRUTE = "Échec d'envoi à alice.martin@example.com depuis /Users/quelquun/Projets/trieur/main.py"


def definitions(maison: Path) -> dict[str, DefModule]:
    projet = maison / "Projets" / "trieur"
    projet.mkdir(parents=True, exist_ok=True)
    (projet / "main.py").write_text("print('trieur')\n")
    diagnostic = [sys.executable, "-c", "print('diagnostic ok pour alice.martin@example.com')"]
    brief = Attente("brief", "quotidienne", "brief chaque jour vers 7h15", heure="07:15", tolerance_min=20)
    return {
        "bouclier": DefModule(id="bouclier", nom="Bouclier", emoji="🛡️", plafond_usd=2.0, aide="bouclier doctor"),
        "trieur": DefModule(id="trieur", nom="Trieur", emoji="🗂️", dossier_projet=str(projet), perimetre_code=["."],
                            commande_diagnostic=diagnostic, aide="trieur doctor"),
        "quotidien": DefModule(id="quotidien", nom="Quotidien", emoji="🌅", attentes=[brief]),
        "corvees": DefModule(id="corvees", nom="Corvées", emoji="🧹"),
    }  # fmt: skip


def etats() -> list[EtatModule]:
    boucle = Probleme("trieur", "boucle", "grave", "🔴 Trieur s'est arrêté 5 fois en 10 min. Tape « trieur doctor ».",
                      "✅ Trieur tourne de nouveau.", phrase="Trieur s'est arrêté 5 fois aujourd'hui")  # fmt: skip
    attente = Probleme("quotidien", "attente", "attention", "🟡 Quotidien : le brief n'a pas eu lieu.", "✅",
                       sous_cle="brief", phrase="« brief » : pas fait (attendu vers 7h15)")  # fmt: skip
    return [
        EtatModule("bouclier", "Bouclier", "🛡️", Pastille.VERT, "Tourne depuis 3 j", "analyse il y a 5 min",
                   erreurs_24h=0, cpu_pct=0.4, rss_mo=42.0, credits_mois=0.8, plafond_usd=2.0, maj=MAINTENANT),
        EtatModule("trieur", "Trieur", "🗂️", Pastille.ROUGE, boucle.phrase, erreurs_24h=14, cpu_pct=31.0,
                   rss_mo=80.0, credits_mois=0.95, plafond_usd=1.0, problemes=[boucle], integrite="changé",
                   files=[{"nom": "BoiteMac", "n": 2, "plus_vieux_s": 2700, "pas_encore_telecharges": 0}],
                   maj=MAINTENANT),
        EtatModule("quotidien", "Quotidien", "🌅", Pastille.JAUNE, attente.phrase, problemes=[attente],
                   prochaine="brief demain à 7h15",
                   attentes=[{"id": "brief", "libelle": "brief chaque jour vers 7h15", "statut": "manquee",
                              "echeance": MAINTENANT - 9900, "prochaine": None, "derniere_preuve": None,
                              "detail": "pas fait (attendu vers 7h15)"}], maj=MAINTENANT),
        EtatModule("corvees", "Corvées", "🧹", Pastille.GRIS, "Éteint : en pause", maj=MAINTENANT),
    ]  # fmt: skip


def remplir(base: Base) -> None:
    lignes = []
    for heure in range(48):
        ts = MAINTENANT - heure * 3600
        lignes += [("bouclier", ts, "vert", 0.4, 42.0, 0, 0, 0), ("trieur", ts, "vert" if heure > 3 else "rouge",
                   2.0 + heure % 5, 70.0, 1, 0, 0)]  # fmt: skip
    base.plusieurs("INSERT INTO echantillons VALUES (?, ?, ?, ?, ?, ?, ?, ?)", lignes)
    agregats = [("h", MAINTENANT - 86400 * j - 3600 * h, "trieur", 60, 1.5, 3.0, 65.0, 70.0, 2, 0, 60, 0, 0, 0)
                for j in range(3, 6) for h in range(24)]  # fmt: skip
    base.plusieurs("INSERT INTO agregats VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", agregats)
    base.plusieurs("INSERT INTO compteurs_logs VALUES ('trieur', ?, ?, 0)",
                   [(MAINTENANT - 3600 * h, 3) for h in range(30)])  # fmt: skip
    base.executer("INSERT INTO dernieres_erreurs VALUES ('trieur', ?, ?)", (MAINTENANT - 600, ERREUR_BRUTE))
    base.executer("INSERT INTO attentes VALUES ('quotidien', 'brief', ?, 'manquee', ?, 'pas fait')",
                  (MAINTENANT - 9900, MAINTENANT))  # fmt: skip
    base.executer("INSERT INTO attentes VALUES ('quotidien', 'brief', ?, 'tenue', ?, 'fait')",
                  (MAINTENANT - 9900 - 86400, MAINTENANT))  # fmt: skip
    base.executer(
        "INSERT INTO integrite_etat (module, reference_le, controle_le, ecarts, head, head_reference) "
        "VALUES ('trieur', ?, ?, ?, 'b', 'a')",
        (MAINTENANT - 86400 * 3, MAINTENANT - 600, json.dumps([{"chemin": "main.py", "genre": "modifié", "quand": 1}])),
    )
    base.executer("INSERT INTO credits VALUES ('bouclier', '2026-09', 1.2, 2.0, 0)")
    base.noter_evenement(MAINTENANT - 300, "trieur", "boucle", "grave", "🔴 Trieur s'est arrêté 5 fois en 10 min.")
    base.noter_evenement(MAINTENANT - 7200, "bouclier", "resolution", "info", "✅ Bouclier tourne de nouveau.")
    base.ecrire_meta("mac", json.dumps({"cpu_pct": 120.0, "memoire_totale_mo": 16384}))


def construire(maison: Path, horloge: object = None) -> tuple[Source, NotificateurMemoire]:
    chemins = config.Chemins(maison)
    chemins.preparer()
    base = Base(chemins.base)
    reglages = config.charger(chemins.reglages)
    t = [MAINTENANT]
    lire = horloge if callable(horloge) else (lambda: t[0])
    notif = NotificateurMemoire()
    defs = definitions(maison)
    gardien = Gardien(base, maison, chemins.launch_agents, lire)
    source = Source(base, reglages, chemins, defs, gardien, Alertes(base, reglages, notif, lire), lire)
    remplir(base)
    source.publier(etats())
    return source, notif
