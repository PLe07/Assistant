"""La commande « demarrage » :  python demarrage.py <commande>  (ou python assistant.py demarrage <commande>).

scan                       inventaire complet de ce qui se lance tout seul
mesurer [--minutes N]      mesure intensive maintenant (5 minutes par défaut)
rapport [--sans-ouvrir]    écrit et ouvre le rapport (classement, verdicts, commandes)
desactiver ID [--confirmer]  montre ce qui serait fait ; --confirmer le fait (réversible)
restaurer ID [--confirmer]   défait la dernière action sur cet élément ; --confirmer le fait
historique                 tes actions, et l'évolution de tes ouvertures de session
top [--nombre N]           le top N en texte (Markdown), sans aucun chemin personnel
surveiller on|off          la surveillance en fond (nouveaux éléments, mesure à chaque connexion)
doctor                     la machine, les commandes, les données, ce qui est dégradé et pourquoi
"""

from __future__ import annotations

import argparse
import os
import stat
import time
from collections.abc import Callable
from typing import Any

from modules.demarrage import config, daemon, environnement, rapport, travail
from modules.demarrage.actions.desactiver import desactiver as desactiver_element
from modules.demarrage.actions.journal import Journal
from modules.demarrage.actions.restaurer import restaurer as restaurer_element
from modules.demarrage.analyse import Bilan, Element
from modules.demarrage.db import Base
from modules.demarrage.mesure.echantillonneur import Echantillonneur
from modules.demarrage.systeme import Mac, Systeme


class Contexte:
    """Ce dont chaque commande a besoin : les réglages, le Mac (vrai ou faux), la base, et où écrire."""

    def __init__(
        self,
        reglages: dict[str, Any] | None = None,
        systeme: Systeme | None = None,
        ecrire: Callable[[str], None] = print,
        activer: Callable[[str, bool], None] | None = None,
    ):
        self.reglages = reglages or config.charger()[0]
        self.systeme: Systeme = systeme or Mac()
        self.ecrire = ecrire
        self._base: Base | None = None
        self.activer = activer or _activer_module

    @property
    def base(self) -> Base:
        if self._base is None:
            self._base = travail.ouvrir_base(self.reglages)
        return self._base

    def fermer(self) -> None:
        if self._base is not None:
            self._base.fermer()


def _activer_module(nom: str, actif: bool) -> None:
    from core import config as coeur

    coeur.activer_module(nom, actif)


def _ligne(ok: bool | None, texte: str) -> str:
    return f"   {'✅' if ok else '⚠️' if ok is None else '❌'} {texte}"


def trouver(bilan: Bilan, cle: str) -> tuple[Element | None, str]:
    """Par identifiant, début d'identifiant (4 caractères au moins) ou label exact."""
    exacts = [el for el in bilan.elements if el.fiche.id == cle or el.fiche.label == cle]
    if len(exacts) == 1:
        return exacts[0], ""
    debut = [el for el in bilan.elements if len(cle) >= 4 and el.fiche.id.startswith(cle)]
    candidats = exacts or debut
    if len(candidats) == 1:
        return candidats[0], ""
    if candidats:
        return None, "Plusieurs éléments correspondent : " + ", ".join(f"{el.fiche.id} ({el.nom})" for el in candidats)
    return None, f"Je ne connais pas « {cle} ». Les identifiants sont dans le rapport (demarrage rapport)."


def _top(ctx: Contexte, bilan: Bilan, n: int = 5) -> None:
    for i, el in enumerate(bilan.classement[:n], start=1):
        estime = " (estimé)" if el.impact_estime else ""
        ctx.ecrire(
            f"   {i}. {el.verdict.emoji} {el.nom} — impact {el.impact:.0f}/100{estime} · {el.verdict.raison}"
            f" [{el.fiche.id}]"
        )


# --- les commandes ---------------------------------------------------------------------------------------------


def scan(ctx: Contexte, _: argparse.Namespace) -> int:
    debut = time.perf_counter()
    inventaire, nouveaux, premier = travail.scanner(ctx.systeme, ctx.base, ctx.reglages)
    duree = time.perf_counter() - debut
    bilan = travail.bilan(ctx.systeme, ctx.base, ctx.reglages)
    ctx.ecrire(f"🔎 {len(inventaire.fiches)} éléments trouvés en {duree:.1f} s ({len(bilan.apple)} de macOS).")
    puces = {
        code: sum(1 for el in bilan.classement if el.verdict.code == code)
        for code in ("inutile", "orphelin", "inconnu", "utile")
    }
    ctx.ecrire(f"   💤 {puces['inutile']} · 👻 {puces['orphelin']} · ⚠️ {puces['inconnu']} · ✅ {puces['utile']}")
    for c in inventaire.collecteurs:
        if c.etat != "ok":
            ctx.ecrire(_ligne(None, f"{c.nom} {c.etat} : {c.detail}"))
    if nouveaux and not premier:
        ctx.ecrire(
            "   Nouveaux depuis le dernier scan : "
            + ", ".join(el.nom for el in bilan.elements if el.fiche.id in nouveaux)
        )
    _top(ctx, bilan)
    ctx.ecrire("Le détail : demarrage rapport")
    return 0


def mesurer(ctx: Contexte, args: argparse.Namespace) -> int:
    if ctx.base.dernier_scan() is None:
        travail.scanner(ctx.systeme, ctx.base, ctx.reglages)
    inventaire = ctx.base.dernier_scan()
    fiches = inventaire.fiches if inventaire else []
    ech = Echantillonneur(ctx.systeme, ctx.base, ctx.reglages, lambda: fiches)
    ctx.ecrire(f"⏱ Mesure pendant {args.minutes:g} min (un relevé toutes les 5 s). Utilise ton Mac normalement.")
    dernier = [ctx.systeme.maintenant()]

    def rappel(reste: float) -> None:
        if ctx.systeme.maintenant() - dernier[0] >= 60 and reste > 0:
            dernier[0] = ctx.systeme.maintenant()
            ctx.ecrire(f"   … encore {reste / 60:.0f} min")

    n = ech.mesurer(args.minutes, rappel=rappel)
    bilan = travail.bilan(ctx.systeme, ctx.base, ctx.reglages)
    ctx.ecrire(f"✅ {n} relevés. Les plus coûteux :")
    _top(ctx, bilan)
    return 0


def rapport_cmd(ctx: Contexte, args: argparse.Namespace) -> int:
    bilan = travail.bilan(ctx.systeme, ctx.base, ctx.reglages)
    travail.mesurer_zsh(ctx.systeme, ctx.base, ctx.reglages)
    from core import config as coeur

    contenu = rapport.construire(
        bilan,
        ctx.reglages,
        ctx.base.sessions(),
        ctx.base.zsh(),
        ctx.systeme.uid,
        str(coeur.RACINE).replace(ctx.systeme.maison, "~", 1),
    )
    chemin = rapport.ecrire(travail.dossier(ctx.reglages) / "rapport.html", contenu)
    phrase, gain = rapport.resume(bilan, ctx.reglages)
    ctx.ecrire(f"📄 {phrase}\n   {gain}\n   Rapport : {chemin}")
    if not args.sans_ouvrir and ctx.systeme.a_la_commande("open"):
        ctx.systeme.executer(["open", str(chemin)], delai=10)
    return 0


def desactiver(ctx: Contexte, args: argparse.Namespace) -> int:
    bilan = travail.bilan(ctx.systeme, ctx.base, ctx.reglages)
    el, erreur = trouver(bilan, args.id)
    if el is None:
        ctx.ecrire(f"⛔ {erreur}")
        return 1
    r = desactiver_element(el, ctx.systeme, Journal(ctx.base), travail.dossier(ctx.reglages), args.confirmer)
    p = r.plan
    ctx.ecrire(f"{el.verdict.emoji} {el.nom} [{el.fiche.id}] — {el.verdict.titre}")
    ctx.ecrire(f"   {p.message}")
    if p.texte and (p.genre in ("instructions", "verifier") or not r.fait):
        ctx.ecrire("\n".join("   " + ligne for ligne in p.texte.splitlines()))
    if p.agit and not args.confirmer:
        for c in p.commandes:
            ctx.ecrire("   → " + " ".join(c))
        ctx.ecrire(
            f"   Simulation : rien n'a été modifié. Pour le faire : demarrage desactiver {el.fiche.id} --confirmer"
        )
    elif p.annulation and p.genre == "instructions":
        ctx.ecrire("   Pour annuler :\n" + "\n".join("   " + ligne for ligne in p.annulation.splitlines()))
    if args.confirmer and p.agit:
        ctx.ecrire(f"   {'✅' if r.fait else '❌'} {r.message}")
        for err in r.erreurs:
            ctx.ecrire(f"   ⚠️ {err}")
    return 0 if (r.fait or not args.confirmer or not p.agit) else 1


def restaurer(ctx: Contexte, args: argparse.Namespace) -> int:
    journal = Journal(ctx.base)
    cle = args.id
    ids = {a.fiche_id for a in journal.toutes()}
    if cle not in ids:
        bilan = travail.bilan(ctx.systeme, ctx.base, ctx.reglages)
        el, _ = trouver(bilan, cle)
        cle = el.fiche.id if el else next((i for i in ids if len(cle) >= 4 and i.startswith(cle)), cle)
    r = restaurer_element(cle, ctx.systeme, journal, args.confirmer)
    ctx.ecrire(("✅ " if r.fait else "") + r.message)
    for err in r.erreurs:
        ctx.ecrire(f"   ⚠️ {err}")
    if not args.confirmer and r.commandes:
        ctx.ecrire(f"   Pour le faire : demarrage restaurer {cle} --confirmer")
    return 0 if not r.erreurs else 1


def top(ctx: Contexte, args: argparse.Namespace) -> int:
    """Le top N en Markdown, sans aucun chemin personnel : pour le coller ailleurs (RAPPORT_FINAL)."""
    bilan = travail.bilan(ctx.systeme, ctx.base, ctx.reglages)
    phrase, gain = rapport.resume(bilan, ctx.reglages)
    ctx.ecrire(f"{phrase}\n\n{gain}\n")
    ctx.ecrire("| # | Élément | Éditeur | Impact | Coût mesuré | Verdict | Désactiver | Restaurer |")
    ctx.ecrire("|---|---|---|---|---|---|---|---|")
    for i, el in enumerate(bilan.classement[: args.nombre], start=1):
        m = el.metriques
        morceaux = [
            f"{rapport.secondes(m.cpu_session_s)} à l'ouverture" if m.cpu_session_s else "",
            f"{rapport.nombre(m.cpu_croisiere_pct, 1)} % d'un cœur" if m.cpu_croisiere_pct else "",
            rapport.memoire(m.memoire_mo) if m.memoire_mo else "",
            "empêche la veille" if "empêche la veille" in el.drapeaux else "",
        ]
        cout = " · ".join(x for x in morceaux if x) or "—"
        if el.verdict.action in ("desactiver", "quarantaine", "reglages") or (
            el.verdict.action == "verifier" and el.fiche.actif is not False
        ):
            agir, annuler = (
                f"`demarrage desactiver {el.fiche.id} --confirmer`",
                f"`demarrage restaurer {el.fiche.id} --confirmer`",
            )
        elif el.verdict.action == "instructions":
            agir, annuler = f"à taper soi-même : `demarrage desactiver {el.fiche.id}` les affiche", "idem"
        else:
            agir = annuler = "—"
        impact = f"{el.impact:.0f}" + (" (estimé)" if el.impact_estime else "")
        editeur = (el.editeur or "inconnu").replace("|", "/")
        verdict = f"{el.verdict.emoji} {el.verdict.titre}"
        ctx.ecrire(f"| {i} | {el.nom} | {editeur} | {impact} | {cout} | {verdict} | {agir} | {annuler} |")
    return 0


def historique(ctx: Contexte, _: argparse.Namespace) -> int:
    actions = Journal(ctx.base).toutes()
    ctx.ecrire("🗂 Tes actions")
    if not actions:
        ctx.ecrire("   Aucune pour l'instant.")
    for a in actions:
        etat = f"annulée le {rapport.date_longue(a.annulee)}" if a.annulee else "en place"
        quoi = {"launchd": "désactivé", "quarantaine": "mis en quarantaine", "system_events": "retiré de l'ouverture"}
        ctx.ecrire(f"   {rapport.date_longue(a.ts)} · {a.label} [{a.fiche_id}] {quoi.get(a.genre, a.genre)} · {etat}")
    ctx.ecrire("⏱ Tes ouvertures de session")
    sessions = ctx.base.sessions(20)
    if not sessions:
        ctx.ecrire(
            "   Aucune observée pour l'instant (la surveillance mesure chaque ouverture : demarrage surveiller on)."
        )
    for s in sessions:
        quand = rapport.date_longue(s["connexion"]) if s.get("connexion") else rapport.date_longue(s["boot"])
        calme = (
            rapport.secondes(s.get("calme_s"))
            if s.get("calme_s") is not None
            else (s.get("note") or "pas calme en 5 min")
        )
        ctx.ecrire(
            f"   {quand} · démarrage → connexion {rapport.secondes(s.get('demarrage_s'))} · connexion → calme {calme}"
        )
    return 0


def surveiller(ctx: Contexte, args: argparse.Namespace) -> int:
    allume = args.etat == "on"
    ctx.activer("demarrage", allume)
    if allume:
        ctx.ecrire(
            "✅ Surveillance allumée. Le superviseur de l'Assistant la lance dans la minute "
            "(si « python service.py installer » a été fait)."
        )
    else:
        ctx.ecrire("✅ Surveillance éteinte. Tes données et tes actions restent (rien n'est réactivé ni effacé).")
    return 0


def doctor(ctx: Contexte, _: argparse.Namespace) -> int:
    env = environnement.reconnaitre(ctx.systeme)
    ctx.ecrire("🩺 Nettoyeur de démarrage")
    ctx.ecrire(_ligne(env.macos[:1].isdigit(), f"macOS {env.macos} · {env.architecture} · Python {env.python}"))
    for nom, role in environnement.COMMANDES.items():
        ctx.ecrire(_ligne(env.commandes[nom] or None, f"{nom} : {role}" + ("" if env.commandes[nom] else " — absente")))
    if env.manquantes:
        ctx.ecrire(f"   {len(env.manquantes)} commande(s) absente(s) : ce qui en dépend sera marqué « dégradé ».")
    chemin = ctx.base.chemin
    prive = not (stat.S_IMODE(os.stat(chemin).st_mode) & 0o077)
    taille = chemin.stat().st_size / 1e6
    ctx.ecrire(
        _ligne(prive, f"Base : {taille:.1f} Mo · " + ("lisible par toi seul" if prive else "LISIBLE PAR D'AUTRES"))
    )
    corrompues = list(chemin.parent.glob(f"{chemin.name}.corrompue-*"))
    if corrompues:
        ctx.ecrire(
            _ligne(None, f"{len(corrompues)} ancienne(s) base(s) corrompue(s) mise(s) de côté dans {chemin.parent}")
        )
    inventaire = ctx.base.dernier_scan()
    if inventaire is None:
        ctx.ecrire(_ligne(None, "Pas encore de scan : demarrage scan"))
    else:
        ctx.ecrire(
            _ligne(True, f"Dernier scan : {rapport.date_longue(inventaire.ts)} · {len(inventaire.fiches)} éléments")
        )
        for c in inventaire.collecteurs:
            ok = True if c.etat == "ok" else None if c.etat == "dégradé" else False
            ctx.ecrire(_ligne(ok, f"{c.nom} {c.etat}" + (f" : {c.detail}" if c.detail else "")))
            if "Automatisation" in c.detail:
                ctx.ecrire(
                    "      → Réglages Système → Confidentialité et sécurité → Automatisation → coche « System Events »"
                )
    s = daemon.status(ctx.base, ctx.systeme.maintenant())
    if ctx.reglages["actif"]:
        ctx.ecrire(
            _ligne(
                s["vivant"],
                "Surveillance allumée · "
                + (
                    "elle tourne"
                    if s["vivant"]
                    else "elle ne tourne pas : python service.py installer, puis attends une minute"
                ),
            )
        )
    else:
        ctx.ecrire(_ligne(None, "Surveillance éteinte (demarrage surveiller on pour l'allumer)"))
    ctx.ecrire(
        _ligne(
            None if not s["releves"] else True,
            f"{s['releves']} relevés · {s['sessions']} ouverture(s) de session observée(s)",
        )
    )
    return 0


def analyseur() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="demarrage", description="Le Nettoyeur de démarrage")
    sous = p.add_subparsers(dest="commande", required=True)
    sous.add_parser("scan", help="inventaire complet").set_defaults(faire=scan)
    m = sous.add_parser("mesurer", help="mesure intensive maintenant")
    m.add_argument("--minutes", type=float, default=5.0)
    m.set_defaults(faire=mesurer)
    r = sous.add_parser("rapport", help="écrit et ouvre le rapport")
    r.add_argument("--sans-ouvrir", action="store_true")
    r.set_defaults(faire=rapport_cmd)
    for nom, fonction in (("desactiver", desactiver), ("restaurer", restaurer)):
        a = sous.add_parser(nom)
        a.add_argument("id")
        a.add_argument("--confirmer", action="store_true", help="agir pour de vrai (sinon : simulation)")
        a.set_defaults(faire=fonction)
    sous.add_parser("historique").set_defaults(faire=historique)
    t = sous.add_parser("top", help="le top N en Markdown, sans chemin personnel")
    t.add_argument("--nombre", type=int, default=10)
    t.set_defaults(faire=top)
    s = sous.add_parser("surveiller")
    s.add_argument("etat", choices=["on", "off"])
    s.set_defaults(faire=surveiller)
    sous.add_parser("doctor", help="ce qui marche, ce qui est dégradé").set_defaults(faire=doctor)
    return p


def main(argv: list[str], ctx: Contexte | None = None) -> int:
    if not argv or argv[0] in ("aide", "help", "-h", "--help"):
        print(__doc__)
        return 0
    args = analyseur().parse_args(argv)
    ctx = ctx or Contexte()
    try:
        code: int = args.faire(ctx, args)
        return code
    finally:
        ctx.fermer()
