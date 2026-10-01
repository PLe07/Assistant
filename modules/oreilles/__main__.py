"""Module « oreilles » : écoute locale du micro.

Sous le superviseur (sans option) : écoute en fond, rien n'est enregistré.

À la main, dans ~/Assistant avec .venv activé :
    python -m modules.oreilles --telecharger            télécharge le modèle de transcription (une fois)
    python -m modules.oreilles --micros                 liste les micros disponibles
    python -m modules.oreilles --test                   MODE TEST : affiche ce qui est entendu et ce qui
                                                        déclencherait, sans notification ni appel à Claude
    python -m modules.oreilles --test --avec-claude     idem, avec la réponse qu'aurait Claude (quota)
    python -m modules.oreilles --phrase "il faut que je…" [--avec-claude]   teste une phrase écrite, sans micro
"""

import argparse
import sys
import time

import numpy as np

from core import config, etat
from core.journal import journal
from core.module import executer
from core.notifications import notifier
from modules.oreilles import parametres as p

ALERTE_MICRO = ("Le micro semble bloqué par macOS : autorise « Python » dans Réglages Système → "
                "Confidentialité et sécurité → Micro, puis coupe et rallume le micro.")


def ecouter(ctx_arret, log, ecoute, interactif: bool = False) -> None:
    """La boucle d'écoute, commune au mode normal et au mode test."""
    from modules.oreilles.decoupage import Decoupeur
    from modules.oreilles.micro import Micro, sur_secteur

    sur_batterie_signale = False
    while not ctx_arret.is_set():
        if p.reglage("uniquement_sur_secteur", False) and not sur_secteur():
            if not sur_batterie_signale:
                log.info("Sur batterie : écoute suspendue (réglage « uniquement_sur_secteur »)")
                sur_batterie_signale = True
            ecoute.servir_demandes()
            if ctx_arret.wait(30):
                break
            continue
        sur_batterie_signale = False
        decoupeur = Decoupeur(p.TAUX, p.BLOC)
        with Micro(p.reglage("micro")) as micro:
            log.info("Écoute active (micro ouvert)")
            muet_depuis, controle = None, time.time()
            while not ctx_arret.is_set():
                bloc = micro.lire()
                if bloc is not None:
                    if not np.any(bloc):  # zéros absolus : macOS refuse le micro
                        muet_depuis = muet_depuis or time.time()
                        if time.time() - muet_depuis > p.SILENCE_NUMERIQUE_ALERTE:
                            log.error("Micro muet (zéros absolus) : autorisation macOS probablement refusée")
                            print(f"⛔ {ALERTE_MICRO}") if interactif else notifier("Assistant", ALERTE_MICRO, module="oreilles")
                            muet_depuis = float("inf")
                    else:
                        muet_depuis = None
                    phrase = decoupeur.ajouter(bloc)
                    if phrase is not None:
                        ecoute.traiter_phrase(phrase)
                if time.time() - controle >= 1:
                    controle = time.time()
                    ecoute.servir_demandes()
                    ecoute.oublier()
                    if interactif:
                        if _micro_interdit():
                            print("\n⏸  Micro coupé (pause ou bouton de l'icône) : test arrêté.")
                            ctx_arret.set()
                            break
                        etat.ecrire("micro_test", time.time())  # 🎙 sur l'icône pendant le test aussi
                    if p.reglage("uniquement_sur_secteur", False) and not sur_secteur():
                        break
        decoupeur.vider()
        if interactif:
            etat.effacer("micro_test")
        log.info("Écoute arrêtée (micro fermé)")


def _micro_interdit() -> bool:
    r = config.charger()
    return r["pause_globale"] or r["pause_micro"]


def boucle(ctx) -> None:
    from modules.oreilles.ecoute import Ecoute

    # Si l'écoute précédente a été coupée net, ses aides en attente ne peuvent plus être rédigées.
    etat.expirer_aides("oreilles", "Cette aide a expiré : l'écoute a redémarré entre-temps.")
    ecoute = Ecoute(ctx.log)
    try:
        ecoute.transcripteur.charger()
        ecouter(ctx.arret, ctx.log, ecoute)
    finally:
        ecoute.arreter()  # efface tout ce qui restait en mémoire


def mode_test(avec_claude: bool) -> int:
    import threading

    from modules.oreilles.ecoute import Ecoute

    if _micro_interdit():
        print("⏸  Le micro est coupé (pause globale ou « micro off ») : rallume-le d'abord.")
        return 1
    print("MODE TEST : rien n'est enregistré, aucune notification." + (" Claude est consulté (quota)." if avec_claude else ""))
    print("Chargement du modèle de transcription…")
    ecoute = Ecoute(journal("oreilles"), test=True, avec_claude=avec_claude)
    ecoute.transcripteur.charger()
    print("🎙  Parle ! (Ctrl + C pour arrêter)\n")
    arret = threading.Event()
    try:
        ecouter(arret, journal("oreilles"), ecoute, interactif=True)
    except KeyboardInterrupt:
        print("\nArrêt du test.")
    finally:
        arret.set()
        ecoute.arreter()
    return 0


def tester_phrase(phrase: str, avec_claude: bool) -> int:
    from modules.oreilles.ecoute import Ecoute

    class Fixe:  # pas de micro : on « transcrit » directement la phrase donnée
        def transcrire(self, _):
            return phrase

    ecoute = Ecoute(journal("oreilles"), test=True, avec_claude=avec_claude, transcripteur=Fixe())
    ecoute.traiter_phrase(None)
    ecoute.arreter()
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        executer("oreilles", boucle)
        return 0
    parser = argparse.ArgumentParser(prog="python -m modules.oreilles", description="Écoute locale")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--test", action="store_true", help="affiche ce qui est entendu, sans rien déclencher")
    modes.add_argument("--phrase", help="teste une phrase écrite, sans micro")
    modes.add_argument("--telecharger", action="store_true", help="télécharge le modèle de transcription")
    modes.add_argument("--micros", action="store_true", help="liste les micros disponibles")
    parser.add_argument("--avec-claude", action="store_true", help="montre aussi la réponse de Claude (quota)")
    args = parser.parse_args(argv)
    if args.micros:
        from modules.oreilles.micro import lister_micros

        print("\n".join(lister_micros()) or "Aucun micro trouvé.")
        return 0
    if args.telecharger:
        from modules.oreilles.transcription import Transcripteur

        print("Téléchargement du modèle (une seule fois, quelques minutes)…")
        Transcripteur(p.reglage("modele_transcription", "small")).charger(telecharger=True)
        print(f"✅ Modèle prêt dans {p.MODELES}")
        return 0
    if args.phrase is not None:
        return tester_phrase(args.phrase, args.avec_claude)
    return mode_test(args.avec_claude)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
