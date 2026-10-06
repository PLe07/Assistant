"""La commande « trieur » (python trieur.py <commande>, ou python assistant.py trieur <commande>)."""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

AIDE = """🗂 Le Trieur : tes documents reconnus, renommés, rangés ; tes garanties suivies.

  trieur ajouter FICHIER…          donner un ou plusieurs documents (--note "garantie 3 ans")
  trieur statut                    l'état du système
  trieur journal                   les derniers traitements (-n 40 pour en voir plus)
  trieur coffre                    tes garanties
  trieur garantie ajouter|modifier|supprimer
  trieur annuler ID                remettre l'original à sa place
  trieur corriger ID --type X      corriger un classement (une règle est apprise ; --emetteur Y)
  trieur ranger-existant DOSSIER   un plan pour un dossier existant (--confirmer pour l'exécuter)
  trieur arborescence              s'aligner sur tes dossiers de ~/Documents (--appliquer)
  trieur pages                     refaire les pages « Mon coffre » et « Derniers classements »
  trieur doctor                    santé, autorisations, données
  trieur installer                 dossiers, action du Finder, raccourcis, surveillance
"""


def _date(texte: str) -> date:
    try:
        return date.fromisoformat(texte)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"date attendue au format AAAA-MM-JJ : {texte}") from e


def construire() -> argparse.ArgumentParser:
    from modules.trieur.api import SOURCES
    from modules.trieur.classement.regles import TYPES

    p = argparse.ArgumentParser(prog="trieur", description="Le Trieur de documents.")
    sp = p.add_subparsers(dest="commande")
    a = sp.add_parser("ajouter", help="donner des documents")
    a.add_argument("fichiers", nargs="+", type=Path)
    a.add_argument("--source", default="cli", choices=SOURCES)
    a.add_argument("--note")
    sp.add_parser("statut")
    j = sp.add_parser("journal")
    j.add_argument("-n", type=int, default=20)
    sp.add_parser("coffre")
    g = sp.add_parser("garantie")
    gs = g.add_subparsers(dest="action", required=True)
    ga = gs.add_parser("ajouter")
    ga.add_argument("produit")
    ga.add_argument("--achat", type=_date, required=True)
    ga.add_argument("--mois", type=int)
    ga.add_argument("--fin", type=_date)
    ga.add_argument("--emetteur")
    ga.add_argument("--prix")
    gm = gs.add_parser("modifier")
    gm.add_argument("id", type=int)
    for option in ("--produit", "--emetteur", "--prix"):
        gm.add_argument(option)
    gm.add_argument("--achat", type=_date)
    gm.add_argument("--fin", type=_date)
    gm.add_argument("--mois", type=int)
    gd = gs.add_parser("supprimer")
    gd.add_argument("id", type=int)
    an = sp.add_parser("annuler")
    an.add_argument("id", type=int)
    co = sp.add_parser("corriger")
    co.add_argument("id", type=int)
    co.add_argument("--type", required=True, choices=TYPES)
    co.add_argument("--emetteur")
    re_ = sp.add_parser("ranger-existant")
    re_.add_argument("dossier", type=Path)
    re_.add_argument("--confirmer", action="store_true")
    re_.add_argument("--recursif", action="store_true")
    ar = sp.add_parser("arborescence")
    ar.add_argument("--appliquer", action="store_true")
    sp.add_parser("pages")
    sp.add_parser("doctor")
    ins = sp.add_parser("installer")
    ins.add_argument("--sans-allumer", action="store_true", help="tout préparer, sans allumer la surveillance")
    return p


class Contexte:
    """Les réglages, les outils (créés à la demande) et la sortie : remplaçables dans les tests."""

    def __init__(self, reglages: dict[str, Any] | None = None, outils: Any = None,
                 ecrire: Callable[[str], None] = print):  # fmt: skip
        if reglages is None:
            from modules.trieur import config

            reglages, erreurs = config.charger()
            for e in erreurs:
                ecrire(f"⚠️ {e}")
        self.reglages, self._outils, self.ecrire = reglages, outils, ecrire

    @property
    def o(self) -> Any:
        if self._outils is None:
            from modules.trieur import traitement

            self._outils = traitement.outils(self.reglages)
        return self._outils

    def fermer(self) -> None:
        if self._outils is not None:
            self._outils.base.fermer()


def _relatif(chemin: str | None, ctx: Contexte) -> str:
    if not chemin:
        return "—"
    from modules.trieur import config

    p = Path(chemin)
    for racine, prefixe in ((config.chemin(ctx.reglages, "classes").parent, ""), (Path.home(), "~/")):
        try:
            return prefixe + str(p.relative_to(racine))
        except ValueError:
            continue
    return str(p)


def _resultat(el: Any, ctx: Contexte) -> str:
    symbole = {"classe": "✅", "a_verifier": "🔎", "photos": "📷", "doublon": "♻️", "ignore": "·", "erreur": "⚠️",
               "annule": "↩️"}.get(el.etat, "…")  # fmt: skip
    texte = f"{symbole} n°{el.id} {el.nom} → {_relatif(el.destination, ctx)}"
    if el.etat == "classe":
        texte += f"  ({el.type}, {el.confiance:.0%}{', ' + el.par if el.par and el.par != 'règles' else ''})"
    elif el.etat in ("erreur", "ignore", "doublon") and (el.erreur or el.details.get("rangé")):
        texte += f"  ({el.erreur or 'déjà rangé : ' + _relatif(el.details.get('rangé'), ctx)})"
    return texte


def ajouter(ctx: Contexte, fichiers: list[Path], source: str, note: str | None) -> int:
    from modules.trieur import traitement
    from modules.trieur.notifications import Notifieur

    o = ctx.o
    notifieur = Notifieur(ctx.reglages) if source == "finder" else None  # depuis le Finder, pas de terminal
    if notifieur:
        o.avertir = notifieur.element
    code = 0
    for f in fichiers:
        chemin = f.expanduser().resolve()
        if not chemin.is_file():
            ctx.ecrire(f"⚠️ pas un fichier : {f}")
            code = 1
            continue
        el = traitement.traiter(o, o.base.ajouter(chemin, source, note))
        enfants = list(o.ajoutes)
        o.ajoutes.clear()
        for enfant in enfants:
            fait = traitement.traiter(o, enfant)
            if fait is not None:
                ctx.ecrire("   " + _resultat(fait, ctx))
        if el is not None:
            ctx.ecrire(_resultat(el, ctx))
            code = code or (1 if el.etat == "erreur" else 0)
    if notifieur:
        notifieur.vider(forcer=True)
    _pages(ctx)
    return code


def _pages(ctx: Contexte) -> None:
    from modules.trieur import pages

    try:
        pages.mettre_a_jour(ctx.reglages, ctx.o.base, ctx.o.coffre)
    except OSError:
        pass


def statut(ctx: Contexte) -> int:
    from modules.trieur import daemon

    s = daemon.status(ctx.reglages, ctx.o.base, time.time())
    vie = ("active" if s["vivant"] else "allumée mais muette (python assistant.py etat)") if s["actif"] else "éteinte"
    ctx.ecrire(f"🗂 Trieur : surveillance {vie}")
    ctx.ecrire(f"   {s['ranges']} rangé(s), {s['a_verifier']} à vérifier, {s['en_attente']} en attente, "
               f"{s['erreurs']} en erreur")  # fmt: skip
    fiches = ctx.o.coffre.fiches()
    bientot = [f for f in fiches if 0 <= f.jours_restants() <= 30]
    ctx.ecrire(f"   🛡 {len([f for f in fiches if f.jours_restants() >= 0])} garantie(s) en cours"
               + (f", {len(bientot)} finissent dans 30 jours" if bientot else ""))  # fmt: skip
    if ctx.o.ia is not None:
        ctx.ecrire(f"   Claude ce mois-ci : {ctx.o.ia.depense_du_mois():.3f} $ sur "
                   f"{float(ctx.reglages['ia']['budget_mensuel_usd']):.2f} $")  # fmt: skip
    for el in ctx.o.base.derniers(3):
        ctx.ecrire("   " + _resultat(el, ctx))
    return 0


def journal(ctx: Contexte, n: int) -> int:
    elements = ctx.o.base.derniers(n)
    if not elements:
        ctx.ecrire("Rien encore. Envoie un document au Mac, ou : python trieur.py ajouter FICHIER")
    for el in elements:
        quand = datetime.fromtimestamp(el.traite or el.ajoute).strftime("%d/%m %H:%M")
        ctx.ecrire(f"{quand}  " + _resultat(el, ctx))
    return 0


def coffre(ctx: Contexte) -> int:
    fiches = ctx.o.coffre.fiches()
    if not fiches:
        ctx.ecrire("🛡 Aucune garantie pour l'instant.")
        return 0
    for f in fiches:
        j = f.jours_restants()
        reste = f"{j} j" if j >= 0 else "expirée"
        ctx.ecrire(f"🛡 n°{f.id} {f.produit} ({f.emetteur or '?'}) : fin le {f.fin.strftime('%d/%m/%Y')} — {reste}"
                   f"  [{f.source}]")  # fmt: skip
    return 0


def garantie(ctx: Contexte, args: argparse.Namespace) -> int:
    c = ctx.o.coffre
    try:
        if args.action == "ajouter":
            n = c.ajouter_a_la_main(args.produit, args.achat, args.mois, args.fin, args.emetteur, args.prix)
            f = c.fiche(n)
            ctx.ecrire(f"🛡 n°{n} {f.produit} : fin le {f.fin.strftime('%d/%m/%Y')} ({len(f.rappels)} rappel(s))")
        elif args.action == "modifier":
            n = c.modifier(args.id, produit=args.produit, emetteur=args.emetteur, prix=args.prix, achat=args.achat,
                           fin=args.fin, mois=args.mois)  # fmt: skip
            ctx.ecrire(f"🛡 garantie modifiée : n°{n} (l'ancienne n°{args.id} est retirée)")
        else:
            for fait in c.supprimer(args.id) or ["fiche retirée"]:
                ctx.ecrire(f"🛡 {fait}")
    except (KeyError, ValueError) as e:
        ctx.ecrire(f"⚠️ {e.args[0] if e.args else e}")
        return 1
    _pages(ctx)
    return 0


def annuler(ctx: Contexte, element: int) -> int:
    from modules.trieur import traitement

    try:
        faits = traitement.annuler(ctx.o, element)
    except traitement.Refus as e:
        ctx.ecrire(f"⚠️ {e}")
        return 1
    for fait in faits:
        ctx.ecrire(f"↩️ {fait}")
    _pages(ctx)
    return 0


def corriger(ctx: Contexte, element: int, type_: str, emetteur: str | None) -> int:
    from modules.trieur import traitement

    try:
        el = traitement.corriger(ctx.o, element, type_, emetteur)
    except traitement.Refus as e:
        ctx.ecrire(f"⚠️ {e}")
        return 1
    ctx.ecrire(_resultat(el, ctx))
    ctx.ecrire(f"📚 retenu : les documents de « {el.emetteur} » seront plutôt des « {type_} »")
    _pages(ctx)
    return 0


def ranger_existant(ctx: Contexte, dossier: Path, confirmer: bool, recursif: bool) -> int:
    """Sans --confirmer : le plan seul (rien ne bouge). Avec : chaque fichier passe par la chaîne normale."""
    from modules.trieur import traitement
    from modules.trieur.classement import classer, issue, nommage
    from modules.trieur.extraction import extraire

    dossier = dossier.expanduser().resolve()
    if not dossier.is_dir():
        ctx.ecrire(f"⚠️ pas un dossier : {dossier}")
        return 1
    motif = "**/*" if recursif else "*"
    fichiers = sorted(p for p in dossier.glob(motif) if p.is_file() and not p.name.startswith("."))
    if not fichiers:
        ctx.ecrire("Rien à ranger.")
        return 0
    o = ctx.o
    if confirmer:
        for f in fichiers:
            el = traitement.traiter(o, o.base.ajouter(f, "existant"))
            if el is not None:
                ctx.ecrire(_resultat(el, ctx))
        _pages(ctx)
        return 0
    ctx.ecrire(f"Plan pour {len(fichiers)} fichier(s) — rien ne bouge sans --confirmer :")
    travail = o.travail(0) / "plan"
    for f in fichiers:
        e = extraire(f, o.moteur, travail)
        c = (
            classer(e.texte, ctx.reglages, appris=o.base.appris(), base_emetteurs=o.emetteurs)
            if e.texte.strip()
            else None
        )
        sortie = issue(c, e.nature, e.mots, e.erreur, ctx.reglages)
        if sortie == "classe" and c is not None:
            ext = ".pdf" if e.nature == "image" else f.suffix
            ctx.ecrire(f"  {f.name} → {nommage.dossier(c, ctx.reglages)}/{nommage.nom(c, ext, ctx.reglages)}"
                       f"  ({c.confiance:.0%})")  # fmt: skip
        else:
            ctx.ecrire(f"  {f.name} → {sortie.replace('_', ' ')}")
    import shutil

    shutil.rmtree(travail.parent, ignore_errors=True)
    return 0


def arborescence(ctx: Contexte, appliquer_: bool) -> int:
    from modules.trieur import arborescence as arbo

    documents = Path.home() / "Documents"
    propositions = arbo.proposer(documents, ctx.reglages)
    if not propositions:
        ctx.ecrire("Aucun de tes dossiers de ~/Documents ne correspond : tout ira dans ~/Documents/Classés.")
        return 0
    for cle, (avant, apres) in sorted(propositions.items()):
        ctx.ecrire(f"  {cle:16} Classés/{avant}  →  {apres}")
    if appliquer_:
        arbo.appliquer(propositions, ctx.reglages)
        ctx.ecrire("✅ réglages mis à jour (rien n'a été déplacé ; les prochains documents iront là)")
    else:
        ctx.ecrire("Rien n'est changé. Pour l'adopter : python trieur.py arborescence --appliquer")
    return 0


def main(argv: list[str] | None = None, ctx: Contexte | None = None) -> int:
    args = construire().parse_args(argv or [])
    if args.commande is None:
        print(AIDE)
        return 0
    ctx = ctx or Contexte()
    try:
        if args.commande == "ajouter":
            return ajouter(ctx, args.fichiers, args.source, args.note)
        if args.commande == "statut":
            return statut(ctx)
        if args.commande == "journal":
            return journal(ctx, args.n)
        if args.commande == "coffre":
            return coffre(ctx)
        if args.commande == "garantie":
            return garantie(ctx, args)
        if args.commande == "annuler":
            return annuler(ctx, args.id)
        if args.commande == "corriger":
            return corriger(ctx, args.id, args.type, args.emetteur)
        if args.commande == "ranger-existant":
            return ranger_existant(ctx, args.dossier, args.confirmer, args.recursif)
        if args.commande == "arborescence":
            return arborescence(ctx, args.appliquer)
        if args.commande == "pages":
            _pages(ctx)
            ctx.ecrire("✅ pages refaites dans la boîte iCloud")
            return 0
        if args.commande == "doctor":
            from modules.trieur import doctor

            lignes = doctor.verifier(ctx.reglages, ctx.o.base)
            for etat, texte in lignes:
                ctx.ecrire(f"{etat} {texte}")
            return 1 if any(e == "❌" for e, _ in lignes) else 0
        from modules.trieur import installer

        faits = installer.installer(ctx.reglages, ctx.o.base, ctx.o.systeme, allumer=not args.sans_allumer)
        for etat, texte in faits:
            ctx.ecrire(f"{etat} {texte}")
        ctx.ecrire("\nÉtapes suivantes (sur l'iPhone et dans Réglages) : modules/trieur/ACTIONS_HUMAINES.md")
        return 0
    finally:
        ctx.fermer()
