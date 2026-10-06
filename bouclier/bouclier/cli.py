"""La commande `bouclier` : tout ce que Bouclier sait faire, en français.

bouclier verifier "texte du SMS"        bouclier verifier message.eml       bouclier verifier --presse-papiers
bouclier historique
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bouclier import config, db, journal, reseau
from bouclier.systeme import Systeme


@dataclass
class Environnement:
    chemins: config.Chemins
    reglages: dict[str, Any]
    base: db.Base
    systeme: Systeme
    alerte_config: str | None = None


def preparer(systeme: Systeme | None = None) -> Environnement:
    reseau.installer_garde()
    chemins = config.chemins()
    reglages, alerte = config.charger_ou_defauts(chemins)
    chemins.support.mkdir(parents=True, exist_ok=True)
    journal.configurer(chemins.logs, reglages.get("moi", {}))
    return Environnement(chemins, reglages, db.ouvrir(chemins.base), systeme or Systeme(), alerte)


def _ecrire(texte: str) -> None:
    print(texte)


# --- verifier ------------------------------------------------------------------------------------------------------


def cmd_verifier(args: argparse.Namespace, env: Environnement) -> int:
    from bouclier.arnaque import analyse, extraction

    outils = analyse.outils_reels(env.chemins, env.reglages, env.base, env.systeme)
    if args.presse_papiers:
        texte = env.systeme.presse_papiers()
        if not texte.strip():
            _ecrire("Le presse-papiers est vide : copie d'abord le message (⌘C), puis relance.")
            return 1
        message, source = extraction.depuis_texte(texte, "texte"), "presse-papiers"
    elif args.quoi and Path(args.quoi).expanduser().is_file():
        chemin = Path(args.quoi).expanduser()
        try:
            message = extraction.depuis_fichier(chemin, outils.lire_image)
        except (OSError, ValueError) as e:
            _ecrire(f"Je ne peux pas lire {chemin.name} : {e}.")
            return 1
        source = "fichier"
    elif args.quoi:
        message, source = extraction.depuis_texte(args.quoi, "texte"), "mac"
    elif not sys.stdin.isatty():
        message, source = extraction.depuis_texte(sys.stdin.read(), "texte"), "mac"
    else:
        _ecrire('Donne-moi le message : bouclier verifier "le texte"  (ou un fichier, ou --presse-papiers)')
        return 1
    if not message.texte.strip() and not message.avertissements:
        _ecrire("Le message est vide.")
        return 1
    resultat = analyse.verifier(message, outils, source, demande_ia=args.ia)
    _ecrire(resultat.reponse.texte())
    return 0


def cmd_historique(args: argparse.Namespace, env: Environnement) -> int:
    from bouclier.arnaque import historique

    _ecrire(historique.formater(historique.lister(env.base, args.nombre)))
    return 0


# --- Inventaire des comptes (n°18) ---------------------------------------------------------------------------------


def cmd_inventaire(args: argparse.Namespace, env: Environnement) -> int:
    from bouclier import tableau_de_bord
    from bouclier.arnaque.ia import choisir_client
    from bouclier.comptes import lancer

    client = None
    if env.reglages["comptes"].get("ia_domaines_inconnus"):
        client = choisir_client(env.reglages, lambda service: env.systeme.trousseau_lire(service))
    r = lancer.lancer(env.chemins, env.reglages, env.base, env.systeme, client=client,
                      avec_gmail=not args.sans_gmail, avec_navigateurs=not args.sans_navigateurs)  # fmt: skip
    chemin = tableau_de_bord.ecrire(env.base, env.chemins.tableau_de_bord)
    _ecrire(f"{r.gmail}\nNavigateurs lus : {', '.join(r.navigateurs) or 'aucun'}")
    _ecrire(f"🗂 {r.comptes} comptes probables, {r.abonnements} simples abonnements.")
    if r.nouveaux:
        _ecrire(f"Nouveaux depuis la dernière fois : {', '.join(r.nouveaux[:15])}")
    _ecrire(f"Le détail (liens de suppression, double authentification) : {chemin}")
    if args.ouvrir:
        env.systeme.ouvrir(chemin)
    return 0


def cmd_comptes(args: argparse.Namespace, env: Environnement) -> int:
    from bouclier.comptes import inventaire, rapport

    lignes = inventaire.lignes(env.base, ("compte",) if not args.tous else ("compte", "abonnement"))
    if not lignes:
        _ecrire("Pas encore d'inventaire : lance  bouclier inventaire")
        return 0
    categorie = None
    for ligne in lignes:
        if ligne.categorie != categorie:
            categorie = ligne.categorie
            _ecrire(f"\n{categorie.upper()}")
        statut = rapport.STATUTS.get(ligne.statut, ligne.statut)
        _ecrire(f"  {ligne.nom:<34} {rapport.NATURES[ligne.nature]:<18} {statut:<12} ({ligne.id})")
    _ecrire("\nPour noter ton choix : bouclier compte <identifiant> garder|supprimer|supprime")
    return 0


def cmd_compte(args: argparse.Namespace, env: Environnement) -> int:
    from bouclier import tableau_de_bord
    from bouclier.comptes import inventaire

    if not inventaire.poser_statut(env.base, args.service, args.statut):
        _ecrire(f"Je ne trouve pas « {args.service} » dans ton inventaire (bouclier comptes pour la liste).")
        return 1
    tableau_de_bord.ecrire(env.base, env.chemins.tableau_de_bord)
    _ecrire(f"✅ {args.service} : {args.statut}. (Bouclier ne touche jamais lui-même à tes comptes.)")
    return 0


def cmd_gmail_relier(args: argparse.Namespace, env: Environnement) -> int:
    from bouclier import gmail

    adresse = args.adresse.strip().lower()
    if "@" not in adresse:
        _ecrire("Donne ton adresse : bouclier gmail-relier <ton adresse Gmail>")
        return 1
    config.ecrire_modele_si_absent(env.chemins)
    texte = env.chemins.config.read_text(encoding="utf-8")
    if 'adresse = ""' in texte:
        env.chemins.config.write_text(texte.replace('adresse = ""', f'adresse = "{adresse}"', 1), encoding="utf-8")
    _ecrire("Colle le mot de passe d'application (16 lettres) quand le Mac te le demande, puis Entrée :")
    if not env.systeme.trousseau_ecrire_interactif(gmail.ELEMENT_TROUSSEAU, adresse):
        _ecrire("❌ Le mot de passe n'a pas été rangé dans le trousseau (sur le Mac seulement).")
        return 1
    reglages = config.charger_ou_defauts(env.chemins)[0]
    ok, message = gmail.etat(reglages, env.systeme)
    _ecrire(("✅ " if ok else "❌ ") + message)
    return 0 if ok else 1


# --- Analyse des arguments -----------------------------------------------------------------------------------------

Commande = Callable[[argparse.Namespace, Environnement], int]


def analyseur() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bouclier", description="Bouclier : arnaques, comptes, fuites, métadonnées, urgence."
    )
    sous = p.add_subparsers(dest="commande", metavar="commande")

    v = sous.add_parser("verifier", help="est-ce une arnaque ? (texte, fichier .eml / .txt / capture, presse-papiers)")
    v.add_argument("quoi", nargs="?", help="le texte du message, ou le chemin d'un fichier")
    v.add_argument("--presse-papiers", action="store_true", help="vérifier le texte copié")
    v.add_argument("--ia", action="store_true", help="demander aussi l'avis de Claude, même si les règles sont sûres")
    v.set_defaults(fonction=cmd_verifier)

    h = sous.add_parser("historique", help="les dernières vérifications (texte caviardé, 90 jours)")
    h.add_argument("-n", "--nombre", type=int, default=20)
    h.set_defaults(fonction=cmd_historique)

    i = sous.add_parser("inventaire", help="retrouver tes comptes en ligne (en-têtes Gmail et navigateurs)")
    i.add_argument("--sans-gmail", action="store_true")
    i.add_argument("--sans-navigateurs", action="store_true")
    i.add_argument("--ouvrir", action="store_true", help="ouvrir le tableau de bord ensuite")
    i.set_defaults(fonction=cmd_inventaire)

    c = sous.add_parser("comptes", help="la liste de tes comptes trouvés")
    c.add_argument("--tous", action="store_true", help="avec les simples abonnements")
    c.set_defaults(fonction=cmd_comptes)

    s = sous.add_parser("compte", help="noter ton choix pour un compte (Bouclier n'agit jamais lui-même)")
    s.add_argument("service")
    s.add_argument("statut", choices=["garder", "supprimer", "supprime", "a_trier"])
    s.set_defaults(fonction=cmd_compte)

    g = sous.add_parser("gmail-relier", help="ranger le mot de passe d'application Gmail dans le trousseau")
    g.add_argument("adresse")
    g.set_defaults(fonction=cmd_gmail_relier)
    return p


def main(argv: Sequence[str] | None = None, systeme: Systeme | None = None) -> int:
    p = analyseur()
    args = p.parse_args(argv)
    fonction: Commande | None = getattr(args, "fonction", None)
    if fonction is None:
        p.print_help()
        return 0
    env = preparer(systeme)
    try:
        if env.alerte_config:
            _ecrire(f"⚠️ {env.alerte_config} (réglages par défaut utilisés)")
        return fonction(args, env)
    finally:
        env.base.fermer()
