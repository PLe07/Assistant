"""`bouclier doctor` : l'état de chaque brique (✅ OK, ⚠️ dégradé, ❌ absent), avec la solution en une ligne, le
budget de l'IA déjà dépensé ce mois et la date des listes téléchargées."""

from __future__ import annotations

import time
from typing import Any

from bouclier import config, daemon, gmail, installation
from bouclier.arnaque import ia, ocr
from bouclier.arnaque.flux import Flux
from bouclier.db import Base
from bouclier.fuites import hibp
from bouclier.notifier import Notifieur
from bouclier.raccourcis import actions_rapides, generer
from bouclier.systeme import Systeme
from bouclier.urgence import service as urgence

Ligne = tuple[str, str, str]  # (état, brique, explication ou solution)


def _date(t: float | None) -> str:
    return time.strftime("%d/%m/%Y %H:%M", time.localtime(t)) if t else "jamais"


def _age_jours(t: float | None, maintenant: float) -> float:
    return (maintenant - t) / 86400 if t else float("inf")


def verifier(chemins: config.Chemins, reglages: dict[str, Any], base: Base, systeme: Systeme,
             alerte_config: str | None = None, maintenant: float | None = None) -> list[Ligne]:  # fmt: skip
    m = maintenant or time.time()
    lignes: list[Ligne] = []
    if alerte_config:
        lignes.append(("⚠️", "réglages", alerte_config))

    # Démon
    lab = installation.label(reglages)
    agent = installation.etat_agent(systeme, lab)
    pouls = daemon.battement(base)
    if agent.charge and agent.pid and pouls and m - pouls < 120:
        lignes.append(("✅", "démon", f"{lab} tourne (pid {agent.pid}), dernier tour il y a {int(m - pouls)} s"))
    elif agent.charge:
        lignes.append(("⚠️", "démon", f"{lab} est chargé mais ne tourne pas : ./install.sh le relance (journal :"
                                      f" {chemins.logs}/demon.erreurs.log)"))  # fmt: skip
    else:
        lignes.append(("❌", "démon", "pas installé : lance ./install.sh"))

    # Gmail
    ok, message = gmail.etat(reglages, systeme)
    erreur = base.lire_meta("gmail_erreur") or ""
    releve = base.lire_meta("gmail_releve_le")
    if ok and not erreur:
        lignes.append(("✅", "Gmail", f"{message}, dernier relevé : {_date(float(releve) if releve else None)}"))
    elif ok:
        lignes.append(("⚠️", "Gmail", f"{erreur} (nouvel essai automatique)"))
    else:
        lignes.append(("⚠️", "Gmail", message))

    # IA
    client = ia.choisir_client(reglages, lambda service: systeme.trousseau_lire(service))
    budget = ia.Budget(base, reglages)
    depense = f"{budget.depense_du_mois():.3f} $ dépensés ce mois sur {budget.plafond:.2f} $"
    if not reglages["ia"].get("active", True):
        lignes.append(("⚠️", "avis de l'IA", "coupé dans config.toml : analyse locale seule"))
    elif client is None:
        lignes.append(("⚠️", "avis de l'IA", "aucun accès à Claude (clé API ou Claude Code) : analyse locale seule,"
                                             " voir ACTIONS_HUMAINES.md"))  # fmt: skip
    elif not budget.permet(0.005):
        lignes.append(("⚠️", "avis de l'IA", f"en pause jusqu'au mois prochain ({depense})"))
    else:
        lignes.append(("✅", "avis de l'IA", f"par {client.nom}, modèle {reglages['ia']['modele']} ; {depense}"))

    # Listes téléchargées
    for e in Flux(chemins.caches).etats():
        etat = "✅" if _age_jours(e.date, m) <= 2 else "⚠️"
        texte = f"{e.entrees} liens piégés, copie du {_date(e.date)}"
        if e.erreur and e.erreur != "jamais téléchargé":
            texte += f" ; dernier essai raté ({e.erreur[:160]}), nouvel essai toutes les heures"
        lignes.append((etat, f"liste {e.nom}", texte))
    date_fuites = hibp.ListeFuites(chemins.caches).date()
    etat_f = "✅" if _age_jours(date_fuites, m) <= 2 else "⚠️"
    lignes.append((etat_f, "liste des fuites", f"Have I Been Pwned, copie du {_date(date_fuites)}"))

    # Inventaire, fiche urgence
    inv = base.lire_meta("inventaire_le")
    nb = base.cx.execute("SELECT COUNT(*) FROM comptes WHERE nature = 'compte'").fetchone()[0]
    texte_inv = f"{nb} comptes, dernier inventaire : {_date(float(inv) if inv else None)}"
    if inv and nb == 0:
        lus = base.lire_meta("inventaire_navigateurs") or ""
        texte_inv += f" ; navigateurs lus : {lus or 'aucun'} (Safari n'est jamais lu : ses mots de passe sont au"
        texte_inv += " trousseau)"
        if not ok:
            texte_inv += " ; relie Gmail pour retrouver tes comptes : bouclier gmail-relier"
    lignes.append(("✅" if inv else "⚠️", "inventaire", texte_inv))
    generee = base.lire_meta("fiche_generee_le")
    sur_icloud = (chemins.icloud / urgence.NOM_PDF).exists()
    if generee:
        lignes.append(("✅" if sur_icloud else "⚠️", "fiche urgence",
                       f"générée le {_date(float(generee))}" + (", copiée sur iCloud" if sur_icloud else
                                                                 ", pas sur iCloud")))  # fmt: skip
    else:
        lignes.append(("⚠️", "fiche urgence", "pas encore générée : bouclier urgence"))

    # iCloud, raccourcis, actions rapides, lecture des captures, outils
    if chemins.icloud.is_dir():
        lignes.append(("✅", "iCloud", f"dossier {chemins.icloud}"))
    else:
        lignes.append(("❌", "iCloud", "iCloud Drive/Bouclier absent : active iCloud Drive puis relance ./install.sh"))
    if systeme.mac:
        r = systeme.executer(["shortcuts", "list"], None, 30)
        if r.code == 0:
            manquants = [n for n, present in generer.installes(r.sortie).items() if not present]
            lignes.append(("✅" if not manquants else "⚠️", "raccourcis",
                           "Arnaque ? et Envoyer sans traces présents" if not manquants else
                           f"à ajouter sur l'iPhone : {', '.join(manquants)} (ACTIONS_HUMAINES.md)"))  # fmt: skip
        else:
            lignes.append(("⚠️", "raccourcis", "liste des raccourcis illisible (commande shortcuts, macOS 12 ou plus)"))
    actions = actions_rapides.etat(chemins.services)
    absentes = [n for n, p in actions.items() if not p]
    lignes.append(("✅" if not absentes else "⚠️", "actions rapides",
                   "Finder et texte sélectionné installés" if not absentes else
                   f"absentes : {', '.join(absentes)} (./install.sh)"))  # fmt: skip
    etat_ocr, texte_ocr = ocr.etat(systeme.mac)
    lignes.append(("✅" if etat_ocr == "ok" else "⚠️", "captures d'écran", texte_ocr))
    outils = [o for o in ("ffmpeg", "exiftool") if systeme.commande_existe(o)]
    complement = f" ; avec {', '.join(outils)}" if outils else " ; vidéos : installe ffmpeg pour les nettoyer"
    lignes.append(("✅", "métadonnées", "photos, PDF, Office" + complement))
    n = Notifieur(base, systeme, reglages, lambda: m).envoyees_aujourdhui()
    lignes.append(("✅", "notifications", f"{n} envoyée(s) aujourd'hui sur {reglages['notifications']['max_par_jour']}"
                                         " au plus, jamais entre 23 h et 8 h"))  # fmt: skip
    return lignes


def afficher(lignes: list[Ligne]) -> str:
    return "\n".join(f"{etat} {brique} : {texte}" for etat, brique, texte in lignes)
