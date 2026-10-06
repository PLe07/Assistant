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
    quoi = list(args.quoi or [])
    messages: list[tuple[extraction.Message, str]] = []
    if args.presse_papiers:
        texte = env.systeme.presse_papiers()
        if not texte.strip():
            return _repondre(args, env, "Le presse-papiers est vide : copie d'abord le message (⌘C), puis relance.", 1)
        messages.append((extraction.depuis_texte(texte, "texte"), "presse-papiers"))
    elif args.stdin or (not quoi and not sys.stdin.isatty()):
        messages.append((extraction.depuis_texte(sys.stdin.read(), "texte"), "mac"))
    elif quoi and all(Path(q).expanduser().is_file() for q in quoi):
        for q in quoi:
            chemin = Path(q).expanduser()
            try:
                messages.append((extraction.depuis_fichier(chemin, outils.lire_image), "fichier"))
            except (OSError, ValueError) as e:
                return _repondre(args, env, f"Je ne peux pas lire {chemin.name} : {e}.", 1)
    elif quoi:
        messages.append((extraction.depuis_texte(" ".join(quoi), "texte"), "mac"))
    else:
        return _repondre(args, env, 'Donne-moi le message : bouclier verifier "le texte"  (ou un fichier, ou'
                                    " --presse-papiers)", 1)  # fmt: skip
    textes = []
    for message, source in messages:
        if not message.texte.strip() and not message.avertissements:
            textes.append("Le message est vide.")
            continue
        textes.append(analyse.verifier(message, outils, source, demande_ia=args.ia).reponse.texte())
    return _repondre(args, env, "\n\n".join(textes), 0)


def _repondre(args: argparse.Namespace, env: Environnement, texte: str, code: int) -> int:
    _ecrire(texte)
    if getattr(args, "fenetre", False):
        env.systeme.dialogue("Bouclier", texte)
    return code


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


# --- Fuites (n°19) -------------------------------------------------------------------------------------------------


def cmd_fuites(args: argparse.Namespace, env: Environnement) -> int:
    from bouclier import tableau_de_bord
    from bouclier.fuites import rapport, traductions
    from bouclier.notifier import Notifieur

    r = rapport.verifier(env.chemins, env.reglages, env.base, Notifieur(env.base, env.systeme, env.reglages),
                         forcer=args.mettre_a_jour)  # fmt: skip
    _ecrire(f"{r.liste.capitalize()}.")
    if not r.bilan.toutes:
        _ecrire("Aucune fuite connue ne touche les services de ton inventaire (lance aussi : bouclier inventaire).")
    for c in r.bilan.toutes:
        quand = c.fuite.date.strftime("%m/%Y") if c.fuite.date else "?"
        nouveau = "  🆕" if c in r.bilan.nouvelles and not r.bilan.premier_passage else ""
        _ecrire(f"⚠️ {c.compte.nom} ({quand}){nouveau} : {', '.join(traductions.traduire(list(c.fuite.donnees))[:5])}")
    if r.bilan.toutes:
        _ecrire(f"👉 {r.bilan.toutes[0].que_faire}")
    if not r.adresse_verifiee:
        _ecrire("Pour vérifier exactement ton adresse, gratuitement : Mozilla Monitor (voir le README).")
    tableau_de_bord.ecrire(env.base, env.chemins.tableau_de_bord)
    return 0


# --- Métadonnées (n°21) --------------------------------------------------------------------------------------------


def cmd_nettoyer(args: argparse.Namespace, env: Environnement) -> int:
    from bouclier.metadonnees import nettoyeur

    code, textes = 0, []
    for fichier in args.fichiers:
        r = nettoyeur.nettoyer(Path(fichier), remplacer=args.remplacer, garder_date=args.garder_date,
                               systeme=env.systeme)  # fmt: skip
        textes.append(r.texte())
        if r.erreur or r.restants:
            code = 1
    return _repondre(args, env, "\n".join(textes), code)


# --- Fiche urgence (n°22) ------------------------------------------------------------------------------------------


def cmd_urgence(args: argparse.Namespace, env: Environnement) -> int:
    from bouclier.notifier import Notifieur
    from bouclier.urgence import infos, service

    if args.action == "editer":
        cree = infos.ecrire_modele_si_absent(env.chemins.infos_urgence)
        env.systeme.ouvrir_editeur(env.chemins.infos_urgence)
        _ecrire(("Fichier créé et ouvert : " if cree else "Fichier ouvert : ") + str(env.chemins.infos_urgence))
        _ecrire("Remplis ce que tu veux (tout est facultatif), enregistre, puis : bouclier urgence generer")
        return 0
    if args.action == "verifier":
        r = service.verifier(env.chemins, env.base, Notifieur(env.base, env.systeme, env.reglages))
        v = r.reverif
        if not v.pages_lues:
            _ecrire("Les sites officiels ne répondent pas : dernière vérification gardée, nouvel essai plus tard.")
            return 1
        _ecrire(f"✅ {len(v.confirmes)} numéros et sites confirmés sur leurs pages officielles ({v.pages_lues} pages).")
        if v.absents:
            _ecrire(f"⚠️ Plus trouvés sur leur page officielle (retirés de la fiche) : {', '.join(v.absents)}")
        if v.injoignables:
            _ecrire(f"Pages injoignables (dernière vérification gardée) : {', '.join(v.injoignables)}")
        return 0
    s = service.generer(env.chemins, env.base)
    _ecrire(f"🆘 Fiche urgence prête :\n   {s.html}\n   {s.pdf}\n   {s.carte}  (carte A6 à imprimer)")
    if s.ecran:
        _ecrire(f"   {s.ecran}  (image pour l'écran verrouillé de l'iPhone)")
    if s.icloud:
        _ecrire(f"Copiée sur iCloud : {s.icloud} (garde-la téléchargée dans l'app Fichiers, voir ACTIONS_HUMAINES.md)")
    for a in s.avertissements:
        _ecrire(f"⚠️ {a}")
    if args.action == "ouvrir":
        env.systeme.ouvrir(s.html)
    return 0


# --- Analyse des arguments -----------------------------------------------------------------------------------------

Commande = Callable[[argparse.Namespace, Environnement], int]


def analyseur() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bouclier", description="Bouclier : arnaques, comptes, fuites, métadonnées, urgence."
    )
    sous = p.add_subparsers(dest="commande", metavar="commande")

    v = sous.add_parser("verifier", help="est-ce une arnaque ? (texte, fichier .eml / .txt / capture, presse-papiers)")
    v.add_argument("quoi", nargs="*", help="le texte du message, ou le chemin d'un ou plusieurs fichiers")
    v.add_argument("--presse-papiers", action="store_true", help="vérifier le texte copié")
    v.add_argument("--stdin", action="store_true", help="lire le message sur l'entrée standard (service macOS)")
    v.add_argument("--fenetre", action="store_true", help="montrer aussi la réponse dans une fenêtre")
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

    f = sous.add_parser("fuites", help="les fuites de données connues qui touchent tes comptes")
    f.add_argument("--mettre-a-jour", action="store_true", help="retélécharger la liste publique maintenant")
    f.set_defaults(fonction=cmd_fuites)

    n = sous.add_parser("nettoyer", help="enlever position GPS, appareil, auteur… (copie « (propre) »)")
    n.add_argument("fichiers", nargs="+")
    n.add_argument("--remplacer", action="store_true", help="mettre l'original à la Corbeille (récupérable)")
    n.add_argument("--garder-date", action="store_true", help="garder la date de prise de vue")
    n.add_argument("--fenetre", action="store_true", help="montrer aussi le résultat dans une fenêtre")
    n.set_defaults(fonction=cmd_nettoyer)

    u = sous.add_parser("urgence", help="la fiche urgence hors-ligne (numéros vérifiés, réflexes, tes contacts)")
    u.add_argument("action", nargs="?", default="generer", choices=["generer", "editer", "verifier", "ouvrir"])
    u.set_defaults(fonction=cmd_urgence)

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
