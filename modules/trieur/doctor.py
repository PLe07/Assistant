"""« trieur doctor » : la santé du Trieur, ce qui marche en mode dégradé et pourquoi.

Chaque ligne : ✅ (ça marche), ⚠️ (dégradé : le Trieur continue sans), ❌ (à corriger). Rien n'est modifié.
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from modules.trieur import config


def _ligne(etat: str, texte: str) -> tuple[str, str]:
    return etat, texte


def _ecrivable(dossier: Path) -> bool:
    d = dossier
    while not d.exists() and d != d.parent:
        d = d.parent
    return os.access(d, os.W_OK)


def _a_trier_pas_a_nous(reglages: dict[str, Any], base: Any) -> bool:
    from modules.trieur.entrees import surveillance

    dossier = config.chemin(reglages, "a_trier")
    if not dossier.exists() or surveillance.a_trier_du_trieur(reglages, base) is not None:
        return False
    return surveillance.contient_des_fichiers(dossier)


def _erreurs_par_dossier(base: Any) -> list[tuple[str, str]]:
    """D'où viennent les erreurs : les 3 dossiers qui en ont le plus, avec le message le plus fréquent."""
    par_dossier: dict[str, list[str]] = {}
    for el in base.erreurs():
        par_dossier.setdefault(str(Path(el.chemin).parent), []).append(el.erreur or "?")
    sortie = []
    for dossier, messages in sorted(par_dossier.items(), key=lambda x: -len(x[1]))[:3]:
        message, _ = Counter(messages).most_common(1)[0]
        sortie.append(_ligne("⚠️", f"   {len(messages)} dans {dossier} · {message}"))
    return sortie


def _superviseur() -> tuple[bool | None, dict[str, Any] | None]:
    """(le superviseur de l'Assistant tourne-t-il ?, ce qu'il dit du Trieur) : lu dans donnees/etat.db.
    None : impossible à savoir."""
    try:
        from core import etat

        vu = etat.lire("superviseur_vivant")
        vivant = vu is not None and time.time() - float(vu) < etat.SUPERVISEUR_SILENCIEUX_APRES
        return vivant, next((m for m in etat.modules() if m["nom"] == "trieur"), None) if vivant else None
    except Exception:
        return None, None


def _pourquoi_muette() -> tuple[str, str]:
    """Allumée mais sans battement : juste lancée (le cas d'après l'installation), superviseur arrêté, ou plantage."""
    vivant, ligne = _superviseur()
    if vivant is None:
        return _ligne("❌", "surveillance allumée mais muette : python assistant.py etat")
    if not vivant:
        return _ligne("❌", "surveillance allumée mais le superviseur de l'Assistant est arrêté : "
                            "python service.py installer")  # fmt: skip
    if ligne is None or ligne["statut"] == "démarrage" or (ligne["statut"] == "actif" and not ligne["relances"]):
        return _ligne("⏳", "surveillance en train de démarrer : relance doctor dans une minute "
                            "(si ça dure, python assistant.py journal)")  # fmt: skip
    if ligne["statut"] == "en pause":
        return _ligne("⚠️", "surveillance en pause (pause globale de l'Assistant)")
    detail = f" ({ligne['detail']})" if ligne.get("detail") else ""
    return _ligne("❌", f"surveillance allumée mais elle plante : {ligne['statut']}{detail}, "
                        f"{ligne['relances']} relance(s) : python assistant.py journal")  # fmt: skip


def verifier(reglages: dict[str, Any], base: Any = None, maintenant: float | None = None,
             mac: bool | None = None) -> list[tuple[str, str]]:  # fmt: skip
    maintenant = maintenant or time.time()
    mac = sys.platform == "darwin" if mac is None else mac
    lignes: list[tuple[str, str]] = []

    # Les bibliothèques.
    for module, role in (("pymupdf", "lire les PDF"), ("PIL", "les photos"), ("jsonschema", "vérifier Claude"),
                         ("watchdog", "suivre tes déplacements")):  # fmt: skip
        try:
            importlib.import_module(module)
            lignes.append(_ligne("✅", f"{module} ({role})"))
        except ImportError:
            lignes.append(_ligne("❌", f"{module} manque ({role}) : pip install -r requirements.txt"))

    # La lecture des images.
    from modules.trieur.extraction import ocr

    moteur = ocr.choisir()
    if moteur is None:
        lignes.append(_ligne("⚠️", "aucun OCR : photos et scans iront dans « À vérifier »"))
    elif moteur.nom == "vision":
        lignes.append(_ligne("✅", "OCR : Apple Vision (français et anglais)"))
    else:
        lignes.append(_ligne("⚠️", f"OCR : {moteur.nom} (Vision indisponible : pyobjc-framework-Vision ?)"))

    # Les dossiers.
    for cle, nom in (("classes", "Classés"), ("a_trier", "À trier"), ("photos", "Photos de l'iPhone")):
        chemin = config.chemin(reglages, cle)
        if cle == "a_trier" and base is not None and _a_trier_pas_a_nous(reglages, base):
            lignes.append(_ligne("❌", f"À trier : {chemin} contient tes fichiers, le Trieur ne le surveille pas "
                                       "(pour choisir un autre dossier : ACTIONS_HUMAINES.md)"))  # fmt: skip
        elif chemin.is_dir():
            lignes.append(_ligne("✅" if _ecrivable(chemin) else "❌", f"{nom} : {chemin}"))
        else:
            lignes.append(_ligne("⚠️", f"{nom} absent ({chemin}) : python trieur.py installer le crée"))
    if base is not None:
        from modules.trieur.entrees import surveillance

        for ancien in surveillance.anciens_du_trieur(reglages, base):
            lignes.append(_ligne("⚠️", f"l'ancien « À trier » {ancien} est encore là : "
                                       "python trieur.py installer le retire s'il est vide"))  # fmt: skip
    icloud = Path(reglages["chemins"]["icloud"]).expanduser()
    boite = config.chemin(reglages, "boite")
    if not icloud.is_dir():
        lignes.append(
            _ligne("❌", "iCloud Drive introuvable : Réglages Système → identifiant Apple → iCloud → iCloud Drive")
        )
    elif not boite.is_dir():
        lignes.append(_ligne("⚠️", "la boîte iCloud BoiteMac n'existe pas encore : python trieur.py installer"))
    else:
        lignes.append(_ligne("✅", f"boîte iCloud : {boite}"))

    # Les commandes du Mac.
    if mac:
        for commande, role in (("sips", "HEIC"), ("brctl", "fichiers iCloud pas encore téléchargés"),
                               ("osascript", "Rappels"), ("shortcuts", "signer les raccourcis"),
                               ("xattr", "repérer AirDrop")):  # fmt: skip
            present = shutil.which(commande) is not None
            lignes.append(_ligne("✅" if present else "⚠️", f"{commande} ({role})" + ("" if present else " : absent")))
        services = config.chemin(reglages, "services")
        from modules.trieur.entrees import finder

        action = (services / f"{finder.NOM}.workflow").exists()
        lignes.append(_ligne("✅" if action else "⚠️", "action rapide du Finder « Trier avec l'assistant »"
                             + ("" if action else " : pas installée (python trieur.py installer)")))  # fmt: skip
    else:
        lignes.append(_ligne("⚠️", "pas sur un Mac : tags, alias, Rappels et iCloud sont imités"))

    # Les règles.
    from modules.trieur.classement import emetteurs, perso_emetteurs, regles

    try:
        r = regles.lire()
        lignes.append(_ligne("✅", f"regles.toml : {sum(len(v) for v in r.indices.values())} indices"))
    except regles.ReglesInvalides as e:
        lignes.append(_ligne("❌", f"regles.toml : {e}"))
    perso = perso_emetteurs(reglages)
    lignes.append(_ligne("✅", f"émetteurs connus : {len(emetteurs.charger(perso))}"
                         + (" (dont les tiens)" if perso and perso.exists() else "")))  # fmt: skip

    # La base et le démon.
    if base is not None:
        from modules.trieur import daemon

        s = daemon.status(reglages, base, maintenant)
        if not reglages["actif"]:
            lignes.append(
                _ligne("⚠️", "surveillance éteinte (python trieur.py installer, ou assistant.py activer trieur)")
            )
        elif s["vivant"]:
            lignes.append(_ligne("✅", f"surveillance active (battement il y a {int(s['battement_age'])} s)"))
        else:
            lignes.append(_pourquoi_muette())
        comptes = base.compter()
        from modules.trieur.pages import LIBELLES

        libelles = {**LIBELLES, "ignore": "laissé à sa place"}
        lignes.append(_ligne("✅", "documents : " + (", ".join(f"{n} {libelles.get(e, e)}"
                                                              for e, n in sorted(comptes.items()))
                                                    or "aucun pour l'instant")))  # fmt: skip
        if comptes.get("ignore"):
            lignes.append(_ligne("✅", "les fichiers laissés et pourquoi : python trieur.py statut"))
        attendus = base.attendus_d_icloud()
        if attendus:
            lignes.append(_ligne("⏳", f"{attendus} attendu(s) d'iCloud : téléchargement demandé, nouvel essai toutes "
                                      "les 2 minutes"))  # fmt: skip
        if comptes.get("erreur"):
            lignes.append(_ligne("⚠️", f"{comptes['erreur']} en erreur : python trieur.py journal"))
            lignes += _erreurs_par_dossier(base)
        if comptes.get("a_verifier"):
            lignes.append(_ligne("⚠️", f"{comptes['a_verifier']} à vérifier dans Classés/À vérifier"))
        from modules.trieur.ia import CoucheIA

        depense = CoucheIA(reglages, base, demander=lambda *a, **k: None).depense_du_mois()
        budget = float(reglages["ia"]["budget_mensuel_usd"])
        etat = "✅" if depense < budget else "⚠️"
        lignes.append(_ligne(etat, f"Claude ce mois-ci : {depense:.3f} $ sur {budget:.2f} $"
                             + ("" if reglages["ia"].get("actif", True) else " (désactivé)")))  # fmt: skip
    return lignes


def afficher(lignes: list[tuple[str, str]]) -> int:
    for etat, texte in lignes:
        print(f"{etat} {texte}")
    return 1 if any(e == "❌" for e, _ in lignes) else 0
