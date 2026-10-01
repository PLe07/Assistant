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
ALERTE_MICRO_MUET = ("Le micro « {nom} » ne transmet aucun son, alors que macOS l'autorise. Vérifie Réglages "
                     "Système → Son → Entrée (le niveau doit bouger quand tu parles), puis coupe et rallume le micro.")
CLES_ETAT = ("oreilles_son", "oreilles_muet", "oreilles_micro")  # pour « assistant.py etat » (jamais le son)


def _alerte(autorisation: str | None, nom: str) -> str:
    return ALERTE_MICRO_MUET.format(nom=nom) if autorisation == "accordee" else ALERTE_MICRO


def ecouter(ctx_arret, log, ecoute, interactif: bool = False) -> None:
    """La boucle d'écoute, commune au mode normal et au mode test."""
    from core.mac import TEXTES_AUTORISATION, autorisation_micro
    from modules.oreilles.decoupage import Decoupeur
    from modules.oreilles.micro import Micro, micro_du_mac, sur_secteur

    sur_batterie_signale = False
    alerte = rouvert = notifie = entendu = False  # pendant un silence : noté, rouvert, notifié · du vrai son reçu ?
    secours = None  # le micro du Mac, si celui choisi par macOS reste muet (iPhone, écouteurs rangés…)
    dernier_son = time.time()  # vrai dernier son reçu : ne repart pas à zéro quand on rouvre un micro muet
    if not interactif:
        for cle in CLES_ETAT:
            etat.effacer(cle)
    try:
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
            choisi = p.reglage("micro")  # un micro imposé dans reglages.json passe avant tout
            reouvrir = False
            with Micro(choisi if choisi is not None else secours) as micro:
                if not rouvert:  # pas de ligne à chaque nouvel essai pendant un silence
                    log.info("Écoute active (micro : %s · autorisation macOS : %s)", micro.nom,
                             TEXTES_AUTORISATION[autorisation_micro()])
                if not interactif:
                    etat.ecrire("oreilles_micro", micro.nom)
                controle = ouvert_le = time.time()
                if not alerte:
                    dernier_son = ouvert_le
                note_son = 0.0
                while not ctx_arret.is_set():
                    bloc = micro.lire()
                    if bloc is not None and np.any(bloc):
                        dernier_son, entendu = time.time(), True
                        if alerte:
                            log.info("Le micro transmet de nouveau du son (%s)", micro.nom)
                            if not interactif:
                                etat.effacer("oreilles_muet")
                            note_son = 0.0  # « etat » à jour tout de suite
                        alerte = rouvert = notifie = False
                    else:
                        silence = time.time() - dernier_son
                        if not alerte and silence > p.SILENCE_NUMERIQUE_ALERTE:
                            # Aucun son, ou des zéros absolus : macOS refuse le micro, ou il ne répond plus.
                            alerte, autorisation = True, autorisation_micro()
                            log.error("Micro muet : aucun son reçu depuis %d s (micro : %s · autorisation macOS : %s)",
                                      p.SILENCE_NUMERIQUE_ALERTE, micro.nom, TEXTES_AUTORISATION[autorisation])
                            if interactif:  # lancé depuis le Terminal : c'est le Terminal qui doit être autorisé
                                print("\n⛔ Micro bloqué par macOS : Réglages Système → Confidentialité et sécurité → Micro "
                                      "→ coche « Terminal », puis relance le test." if autorisation != "accordee" else
                                      f"\n⛔ Le micro « {micro.nom} » ne transmet aucun son : vérifie Réglages Système → "
                                      "Son → Entrée.")
                            else:
                                etat.ecrire("oreilles_muet", autorisation or "inconnue")
                                etat.ecrire("oreilles_son", dernier_son)
                        if alerte and not notifie and not interactif and silence > p.ALERTE_APRES:
                            # Après les essais (rouvrir, micro du Mac) : là, il faut ton aide.
                            notifie = True
                            notifier("Assistant", _alerte(autorisation_micro(), micro.nom), module="oreilles",
                                     urgent=True)  # même la nuit
                        if alerte and time.time() - ouvert_le > p.REOUVERTURE_APRES:
                            if choisi is None and secours is None:
                                mac = micro_du_mac()
                                if mac and mac != micro.nom:
                                    secours = mac
                                    log.info("Micro muet : je passe sur le micro du Mac (« %s »)", mac)
                            if not rouvert:
                                log.info("Micro muet : je le rouvre (après une veille ou un changement de micro, ça suffit)")
                                rouvert = True
                            reouvrir = True
                            break  # on referme et on rouvre le micro, avec la liste des micros à jour
                    if bloc is not None:
                        phrase = decoupeur.ajouter(bloc)
                        if phrase is not None:
                            ecoute.traiter_phrase(phrase)
                    if time.time() - controle >= 1:
                        controle = time.time()
                        ecoute.servir_demandes()
                        ecoute.oublier()
                        # Pour « assistant.py etat » : l'heure du dernier son, jamais le son. Rien avant le
                        # premier vrai son (« démarrage… ») : l'heure d'ouverture n'est pas du son.
                        if not interactif and (entendu or alerte) and controle - note_son >= 5:
                            etat.ecrire("oreilles_son", dernier_son)
                            note_son = controle
                        if interactif:
                            if _micro_interdit():
                                print("\n⏸  Micro coupé (pause ou bouton de l'icône) : test arrêté.")
                                ctx_arret.set()
                                break
                            etat.ecrire("micro_test", time.time())  # 🎙 sur l'icône pendant le test aussi
                        if p.reglage("uniquement_sur_secteur", False) and not sur_secteur():
                            break
            decoupeur.vider()
            if not reouvrir:
                log.info("Écoute arrêtée (micro fermé)")
    finally:
        for cle in CLES_ETAT if not interactif else ("micro_test",):
            etat.effacer(cle)


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
        if p.reglage("micro") is not None:
            print(f"Réglage « micro » imposé dans reglages.json : {p.reglage('micro')}")
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
