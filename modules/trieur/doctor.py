"""« trieur doctor » : la santé du Trieur, ce qui marche en mode dégradé et pourquoi.

Chaque ligne : ✅ (ça marche), ⚠️ (dégradé : le Trieur continue sans), ❌ (à corriger). Rien n'est modifié.
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
import time
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
        if chemin.is_dir():
            lignes.append(_ligne("✅" if _ecrivable(chemin) else "❌", f"{nom} : {chemin}"))
        else:
            lignes.append(_ligne("⚠️", f"{nom} absent ({chemin}) : python trieur.py installer le crée"))
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
            lignes.append(_ligne("❌", "surveillance allumée mais muette : python assistant.py etat"))
        comptes = base.compter()
        lignes.append(_ligne("✅", "documents : " + (", ".join(f"{n} {e}" for e, n in sorted(comptes.items()))
                                                    or "aucun pour l'instant")))  # fmt: skip
        if comptes.get("erreur"):
            lignes.append(_ligne("⚠️", f"{comptes['erreur']} en erreur : python trieur.py journal"))
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
