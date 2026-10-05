"""La commande « corvees » :  python corvees.py <commande>  (ou « corvees <commande> » avec l'alias du README).

status                     le détecteur tourne-t-il ? combien d'événements, de corvées ?
rapport                    ouvre la page de tes corvées repérées
accept ID [--installer]    tu acceptes : les étapes et le script ; --installer l'installe pour toi (types sûrs)
reject ID                  tu refuses : elle ne reviendra plus (sauf si elle devient 3 fois plus fréquente)
snooze ID [jours]          à revoir plus tard (7 jours par défaut)
pause [heures]             coupe tous les capteurs tout de suite (sans durée : jusqu'à « resume »)
resume                     rallume les capteurs
analyser --maintenant      analyse tout de suite, sans attendre 21 h
purge                      efface toutes les données (avec confirmation)
doctor                     la santé de chaque capteur, les autorisations, la dernière analyse, le coût du mois
derniers [n]               les n derniers événements notés (20 par défaut) : pour voir ce qu'il voit
desinstaller ID            défait ce que « accept ID --installer » avait installé
"""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

from modules.corvees import config, daemon, propositions, rapport, suite
from modules.corvees.db import Base
from modules.corvees.detection.moteur import frequence_actuelle
from modules.corvees.normalize import instant_du_jour, local, mois_de

ATTENTE_DEMON_S = 10.0


class Contexte:
    """Ce dont chaque commande a besoin : les réglages, la base, l'heure, et de quoi attendre le démon."""

    def __init__(
        self,
        reglages: dict[str, Any] | None = None,
        maintenant: Callable[[], float] = time.time,
        dormir: Callable[[float], None] = time.sleep,
        entree: Callable[[str], str] = input,
        lancer: Callable[..., Any] = subprocess.run,
        demander: Callable[..., Any] | None = None,
    ):
        self.reglages = reglages or config.charger()[0]
        self.horloge = maintenant
        self.dormir = dormir
        self.entree = entree
        self.lancer = lancer
        self.demander = demander
        self.plateforme = sys.platform
        self.base: Base = daemon.ouvrir(self.reglages)

    @property
    def maintenant(self) -> float:
        return self.horloge()

    def rouvrir(self) -> None:
        self.base.fermer()
        self.base = daemon.ouvrir(self.reglages)

    def demon_vivant(self) -> bool:
        battement = self.base.lire("battement")
        return bool(battement and self.maintenant - float(battement) < 3 * daemon.BATTEMENT_S)

    def demander_au_demon(self, quoi: str, delai: float = ATTENTE_DEMON_S) -> bool:
        """Demande au démon de faire quelque chose (vider, purge) et attend qu'il l'ait fait."""
        quand = self.maintenant
        self.base.ecrire("demande", {"quoi": quoi, "quand": quand})
        fin = time.monotonic() + delai
        while time.monotonic() < fin:
            self.dormir(0.2)
            self.rouvrir()  # après une purge, la base est un nouveau fichier
            fait = self.base.lire("demande_faite")
            if fait and fait.get("quoi") == quoi and fait.get("quand") == quand:
                return True
        return False


def _candidat(ctx: Contexte, id_: str) -> dict[str, Any] | None:
    c = ctx.base.candidat(id_)
    if c is None:
        print(f"⛔ Je ne connais pas la corvée « {id_} ». Les identifiants sont dans le rapport : corvees rapport")
    return c


def _rafraichir_rapport(ctx: Contexte) -> None:
    if rapport.chemin(ctx.reglages).exists():
        rapport.ecrire(ctx.base, ctx.reglages, ctx.maintenant)


# --- les commandes ---------------------------------------------------------------------------------------------


def status(ctx: Contexte, _: argparse.Namespace) -> int:
    s = daemon.status(ctx.base, ctx.maintenant)
    print("🔁 Détecteur de corvées")
    print(
        "   Module : "
        + ("allumé" if s["actif"] else "éteint (pour l'allumer : python assistant.py activer corvees)")
        + " · démon : "
        + (f"vivant (battement il y a {int(ctx.maintenant - float(s['battement']))} s)" if s["vivant"] else "arrêté")
    )
    if s["pause"]:
        jusqua = s["pause"].get("jusqua")
        print(
            "   ⏸ En pause " + (f"jusqu'au {rapport.date_lisible(jusqua)}" if jusqua else "jusqu'à « corvees resume »")
        )
    print(f"   {s['evenements']} événements gardés · {s['corvees']} corvée(s) à la dernière analyse")
    print(f"   Dernière analyse : {rapport.date_lisible(s['derniere_analyse'])}")
    return 0


def voir_rapport(ctx: Contexte, args: argparse.Namespace) -> int:
    fichier = rapport.ecrire(ctx.base, ctx.reglages, ctx.maintenant)
    ouvert = not args.sans_ouvrir and rapport.ouvrir(fichier, ctx.lancer, ctx.plateforme)
    print(f"📄 Rapport : {fichier}" + (" (ouvert dans ton navigateur)" if ouvert else ""))
    return 0


def accepter(ctx: Contexte, args: argparse.Namespace) -> int:
    c = _candidat(ctx, args.id)
    if c is None:
        return 1
    ctx.base.decider(c["signature"], c["id"], "accept", None, float(c["frequence_mois"]), c["tokens"])
    prop = propositions.lire(ctx.reglages, c["id"])
    print(f"✅ Acceptée : {prop['description']['titre_court'] if prop else c['id']}. Je ne te la reproposerai plus.")
    if prop:
        s = prop["description"]["solution"]
        if s["installation_pas_a_pas"]:
            print("   Les étapes :")
            for i, etape in enumerate(s["installation_pas_a_pas"], 1):
                print(f"     {i}. {etape}")
        if s["script"].strip():
            nom = propositions.nom_script(s["type"])
            print(
                f"   Le script ({prop['verification']['statut']}) : {propositions.racine(ctx.reglages) / c['id'] / nom}"
            )
        print(f"   Tout est expliqué ici : {propositions.racine(ctx.reglages) / c['id'] / 'README.md'}")
    code = 0
    if args.installer:
        try:
            message = propositions.installer(ctx.reglages, c["id"], lancer=ctx.lancer)
            print("   " + message.replace("\n", "\n   "))
            print(f"   Pour tout défaire : corvees desinstaller {c['id']}")
        except propositions.Refus as e:
            print(f"   ⛔ Pas d'installation : {e}")
            code = 1
    _rafraichir_rapport(ctx)
    return code


def refuser(ctx: Contexte, args: argparse.Namespace) -> int:
    c = _candidat(ctx, args.id)
    if c is None:
        return 1
    maintenant = ctx.maintenant
    depuis = maintenant - int(ctx.reglages["detection"]["fenetre_jours"]) * 86400
    reference = frequence_actuelle(ctx.base.evenements(depuis, attrs_pour=()), ctx.reglages, c["tokens"], maintenant)
    ctx.base.decider(c["signature"], c["id"], "reject", None, reference, c["tokens"])
    print("🗑 Refusée. Je ne te la reproposerai pas, sauf si elle devient 3 fois plus fréquente.")
    _rafraichir_rapport(ctx)
    return 0


def reporter(ctx: Contexte, args: argparse.Namespace) -> int:
    c = _candidat(ctx, args.id)
    if c is None:
        return 1
    if args.jours <= 0:
        print("⛔ Un nombre de jours positif, par exemple : corvees snooze ID 7")
        return 2
    jusqua = ctx.maintenant + args.jours * 86400
    ctx.base.decider(c["signature"], c["id"], "snooze", jusqua, float(c["frequence_mois"]), c["tokens"])
    print(f"⏰ Reportée : elle pourra revenir après le {rapport.date_lisible(jusqua)}.")
    _rafraichir_rapport(ctx)
    return 0


def pause(ctx: Contexte, args: argparse.Namespace) -> int:
    if args.heures is not None and args.heures <= 0:
        print("⛔ Un nombre d'heures positif, par exemple : corvees pause 2")
        return 2
    jusqua = ctx.maintenant + args.heures * 3600 if args.heures else None
    ctx.base.ecrire("pause", {"jusqua": jusqua})
    duree = f"jusqu'au {rapport.date_lisible(jusqua)}" if jusqua else "jusqu'à « corvees resume »"
    if not ctx.demon_vivant():
        print(f"⏸ Pause notée ({duree}). Le démon ne tourne pas : aucun capteur n'est allumé de toute façon.")
        return 0
    fin = time.monotonic() + 3
    while time.monotonic() < fin and not ctx.base.lire("en_pause"):
        ctx.dormir(0.2)
    confirme = bool(ctx.base.lire("en_pause"))
    print(f"⏸ Pause {duree} : " + ("tous les capteurs sont coupés." if confirme else "les capteurs se coupent."))
    return 0


def reprendre(ctx: Contexte, _: argparse.Namespace) -> int:
    ctx.base.effacer("pause")
    print("▶️ Reprise : les capteurs se rallument.")
    return 0


def analyser(ctx: Contexte, args: argparse.Namespace) -> int:
    if not args.maintenant:
        heure = ctx.reglages["analyse"]["heure"]
        print(f"L'analyse a lieu chaque soir à {heure}. Pour la lancer tout de suite : corvees analyser --maintenant")
        return 0
    if ctx.demon_vivant():
        ctx.demander_au_demon("vider", 3.0)  # les événements des 30 dernières secondes aussi
    maintenant = ctx.maintenant
    print("🔎 Analyse des 30 derniers jours…")
    debut = time.monotonic()
    candidats = daemon.analyser_base(ctx.base, ctx.reglages, maintenant)
    duree = time.monotonic() - debut
    if not candidats:
        print(f"   Rien de solide pour l'instant ({duree:.1f} s). Je continue d'observer.")
        rapport.ecrire(ctx.base, ctx.reglages, maintenant)
        return 0
    descriptions = suite.traiter(
        ctx.reglages, candidats, maintenant, lambda m: print(f"   · {m}"), demander=ctx.demander, prevenir=False
    )
    print(f"   {len(candidats)} corvée(s) repérée(s) en {duree:.1f} s :")
    for c in candidats:
        d = descriptions.get(c["signature"], {})
        print(f"   [{c['id']}] {d.get('titre_court', c['tokens'][0])} · ≈ {round(c['minutes_mois'])} min/mois")
    print("   Le détail : corvees rapport")
    return 0


def purge(ctx: Contexte, args: argparse.Namespace) -> int:
    if not args.oui:
        reponse = ctx.entree(
            "⚠️ Tout effacer (événements, corvées, décisions, propositions, rapport) ? Ce que tu as installé avec "
            "--installer sera désinstallé. Tape OUI pour confirmer : "
        )
        if reponse.strip() != "OUI":
            print("Rien n'a été effacé.")
            return 1
    if ctx.demon_vivant():
        if not ctx.demander_au_demon("purge"):
            print("⛔ Le démon n'a pas répondu : rien n'a été effacé. Réessaie, ou arrête le module d'abord.")
            return 1
    else:
        ctx.base.fermer()
        daemon.effacer_donnees(ctx.reglages, print, ctx.lancer)
        ctx.base = daemon.ouvrir(ctx.reglages)
    print("🧹 Tout est effacé. Le détecteur repart de zéro.")
    return 0


def _ligne(ok: bool | None, texte: str) -> str:
    return f"   {'✅' if ok else '⚠️' if ok is None else '❌'} {texte}"


def doctor(ctx: Contexte, _: argparse.Namespace) -> int:
    h = daemon.health(ctx.base, ctx.maintenant)
    bloquant = False
    print("🩺 Détecteur de corvées")
    print(
        _ligne(
            True if h["actif"] else None,
            "Module " + ("allumé" if h["actif"] else "éteint : python assistant.py activer corvees"),
        )
    )
    if h["vivant"]:
        print(_ligne(True, f"Démon vivant (battement il y a {int(ctx.maintenant - float(h['battement']))} s)"))
    elif h["actif"]:
        bloquant = True
        print(
            _ligne(
                False, "Démon arrêté alors que le module est allumé : python service.py installer, puis attends 1 min"
            )
        )
    else:
        print(_ligne(None, "Démon arrêté (le module est éteint)"))
    if h["pause"]:
        print(_ligne(None, "En pause : corvees resume pour rallumer les capteurs"))
    if not h["capteurs"]:
        print(_ligne(None, "Pas encore de nouvelles des capteurs (le démon n'a pas encore tourné)"))
    for c in h["capteurs"]:
        ok = {"ok": True, "dégradé": None, "désactivé": None}.get(c["statut"], False)
        detail = f" : {c['detail']}" if c.get("detail") else ""
        print(_ligne(ok, f"Capteur {c['capteur']} {c['statut']}{detail}"))
    chemin_base = ctx.base.chemin
    privee = not (stat.S_IMODE(os.stat(chemin_base).st_mode) & 0o077)
    taille = h["taille_octets"] / 1e6
    print(
        _ligne(
            privee and taille < 200,
            f"Base : {h['evenements']} événements · {taille:.1f} Mo (plafond 200 Mo) · "
            + ("lisible par toi seul" if privee else "LISIBLE PAR D'AUTRES (chmod 600 conseillé)"),
        )
    )
    derniere = h["derniere_analyse"]
    heure = ctx.reglages["analyse"]["heure"]
    prochaine = instant_du_jour(ctx.maintenant, heure)
    if prochaine <= ctx.maintenant:
        prochaine += 86400
    print(
        _ligne(
            bool(derniere) or None,
            f"Dernière analyse : {rapport.date_lisible(derniere)} · prochaine : {rapport.date_lisible(prochaine)}",
        )
    )
    budget = float(ctx.reglages["ia"]["budget_mensuel_usd"])
    cout = ctx.base.cout_du_mois(mois_de(ctx.maintenant))
    print(_ligne(cout < budget or None, f"Claude ce mois-ci : {cout:.2f} $ sur {budget:.2f} $"))
    print(_ligne(*_claude()))
    return 1 if bloquant else 0


def _claude() -> tuple[bool | None, str]:
    """Claude Code est-il là, avec son jeton ? (sans l'appeler)"""
    try:
        from core.cerveau import ClaudeIndisponible, binaire_claude

        binaire_claude()
    except ClaudeIndisponible as e:
        return None, f"Claude : {e} (descriptions faites sur place en attendant)"
    except Exception as e:  # pragma: no cover - l'Assistant manque : on le dit
        return None, f"Claude : {e}"
    if not os.getenv("CLAUDE_CODE_OAUTH_TOKEN", "").strip():
        return None, "Claude : jeton absent du .env (python assistant.py renouveler-jeton)"
    return True, "Claude : Claude Code trouvé, jeton présent"


def derniers(ctx: Contexte, args: argparse.Namespace) -> int:
    if args.n <= 0:
        print("⛔ Un nombre positif, par exemple : corvees derniers 20")
        return 2
    if ctx.demon_vivant():
        ctx.demander_au_demon("vider", 3.0)  # les 30 dernières secondes aussi
    evenements = ctx.base.derniers(args.n)
    if not evenements:
        print("Rien de noté pour l'instant.")
        return 0
    print(f"🔎 Les {len(evenements)} derniers événements notés (déjà caviardés, rien d'autre n'est gardé) :")
    for e in evenements:
        print(f"   {rapport.date_lisible(e.ts)}:{local(e.ts):%S} · {e.source:13s} · {e.token}")
    return 0


def desinstaller(ctx: Contexte, args: argparse.Namespace) -> int:
    try:
        print("↩️ " + propositions.desinstaller(ctx.reglages, args.id, lancer=ctx.lancer))
    except propositions.Refus as e:
        print(f"⛔ {e}")
        return 1
    return 0


# --- l'analyse de la ligne de commande ---------------------------------------------------------------------------


class _Analyseur(argparse.ArgumentParser):
    def error(self, message: str) -> Any:  # en français, avec l'aide
        print(f"⛔ {message}\n")
        print(__doc__)
        raise SystemExit(2)


def analyseur() -> argparse.ArgumentParser:
    p = _Analyseur(prog="corvees", description="Le détecteur de corvées répétées", add_help=False)
    sous = p.add_subparsers(dest="commande", parser_class=_Analyseur)
    sous.add_parser("status").set_defaults(faire=status)
    r = sous.add_parser("rapport")
    r.add_argument("--sans-ouvrir", action="store_true")
    r.set_defaults(faire=voir_rapport)
    a = sous.add_parser("accept")
    a.add_argument("id")
    a.add_argument("--installer", action="store_true")
    a.set_defaults(faire=accepter)
    sous.add_parser("reject").add_argument("id")
    sous.choices["reject"].set_defaults(faire=refuser)
    s = sous.add_parser("snooze")
    s.add_argument("id")
    s.add_argument("jours", nargs="?", type=int, default=7)
    s.set_defaults(faire=reporter)
    pa = sous.add_parser("pause")
    pa.add_argument("heures", nargs="?", type=float)
    pa.set_defaults(faire=pause)
    sous.add_parser("resume").set_defaults(faire=reprendre)
    an = sous.add_parser("analyser")
    an.add_argument("--maintenant", action="store_true")
    an.set_defaults(faire=analyser)
    pu = sous.add_parser("purge")
    pu.add_argument("--oui", action="store_true", help="sans demander de confirmation")
    pu.set_defaults(faire=purge)
    sous.add_parser("doctor").set_defaults(faire=doctor)
    de = sous.add_parser("derniers")
    de.add_argument("n", nargs="?", type=int, default=20)
    de.set_defaults(faire=derniers)
    sous.add_parser("desinstaller").add_argument("id")
    sous.choices["desinstaller"].set_defaults(faire=desinstaller)
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
        ctx.base.fermer()
