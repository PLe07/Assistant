"""Module « traduction » : quand il est allumé (icône → 🇬🇧), chaque phrase française que tu finis par un point
devient anglaise, là où tu écris. Traduction SUR TON MAC (aucun appel à Claude, rien ne quitte le Mac).

Sous le superviseur (sans option) : écoute le point en fond. Rien n'est gardé, ni touche ni phrase.

À la main, dans ~/Assistant avec .venv activé :
    python -m modules.traduction --telecharger      télécharge le grand modèle de traduction (une fois, ~1,3 Go)
    python -m modules.traduction --texte "…"        traduit une phrase ici (sans rien toucher ailleurs)
    python -m modules.traduction --comparer "…"     la même phrase par le grand et le petit modèle, côte à côte
    python -m modules.traduction --diagnostic       modèle, autorisations macOS, détection du français
    python -m modules.traduction --test             EN DIRECT, SANS RIEN REMPLACER : tape des phrases dans
                                                    Notes (par ex.) et vois ici ce qui serait traduit
"""

import argparse
import queue
import sys
import threading
import time
import traceback

from core import etat
from core.module import executer
from core.notifications import notifier
from modules.traduction import parametres as p
from modules.traduction.moteur import ModeleAbsent, Traducteur

ALERTE_MODELE = ("La traduction attend son modèle (une seule fois, ~1,3 Go) : dans le Terminal, "
                 "python -m modules.traduction --telecharger")
ALERTE_AUTORISATIONS = ("La traduction a besoin de deux autorisations : Réglages Système → Confidentialité et "
                        "sécurité → « Surveillance de l'entrée » ET « Accessibilité » → active « Python » dans les deux, "
                        "puis éteins et rallume la traduction (icône).")


def _alerter(ctx, cle: str, message: str) -> None:
    etat.ecrire("traduction_alerte", cle)
    ctx.log.error(message)
    notifier("Assistant", message, module="traduction", urgent=True)  # tu dois pouvoir agir tout de suite


def _charger(ctx) -> Traducteur | None:
    """Le modèle chargé ; s'il manque, on le dit une fois et on attend qu'il arrive."""
    alerte = False
    while not ctx.arret.is_set():
        try:
            return Traducteur()
        except ModeleAbsent:
            if not alerte:
                _alerter(ctx, "modele", ALERTE_MODELE)
                alerte = True
        if ctx.attendre(30):
            return None
    return None


def _autoriser(ctx, mac) -> bool:
    """Les deux autorisations de macOS ; demandées une fois, puis attendues (dit une fois)."""
    from modules.yeux.__main__ import python_utilise

    if mac.saisie_autorisee() and mac.accessibilite_autorisee():
        return True
    mac.demander_saisie()
    mac.accessibilite_autorisee(demander=True)
    _alerter(ctx, "autorisation", f"{ALERTE_AUTORISATIONS} (programme à autoriser : {python_utilise()})")
    while not ctx.attendre(30):
        if mac.saisie_autorisee() and mac.accessibilite_autorisee():
            return True
    return False


def _travailler(arret, log, mac, traducteur, points, rapporter=None) -> None:
    """Chaque point tapé : lire, traduire, remplacer. Une erreur sur une phrase n'arrête jamais le module.
    points : file de (heure, phrases finies au clavier à ce moment). rapporter(résultat, appli) : pour --test."""
    from modules.traduction.traitement import COPIEE, TRADUITE, traiter_point

    erreurs = set()
    while not arret.is_set():
        try:
            _, finies = points.get(timeout=0.5)
        except queue.Empty:
            continue
        time.sleep(p.ATTENTE)  # le temps que l'appli affiche le point
        while not points.empty():  # « ... » tapés d'affilée : un seul passage
            points.get_nowait()
        try:
            resultat, appli = traiter_point(mac, traducteur, finies)
        except Exception as e:
            resultat, appli = f"⛔ erreur : {type(e).__name__} : {e}", ""
            if str(e) not in erreurs:  # chaque erreur différente notée une fois, avec le détail (jamais le texte)
                erreurs.add(str(e))
                log.exception("Traduction : erreur sur une phrase (le module continue)")
        fini = time.time()
        restants = []
        while not points.empty():  # les points tapés pendant ce passage y ont été pris en compte
            point = points.get_nowait()
            if point[0] > fini:
                restants.append(point)
        for point in restants:
            points.put(point)
        if rapporter:
            rapporter(resultat, appli)
        if resultat in (TRADUITE, COPIEE):
            log.info("Phrase %s (%s)", resultat, appli)  # jamais la phrase elle-même


def _signaler(points):
    """Ce que le clavier transmet à chaque point : l'heure et le nombre de phrases finies (jamais les touches)."""
    from modules.traduction.acces import ACTIVITE

    return lambda: points.put((time.time(), ACTIVITE.phrases_finies()))


def boucle(ctx) -> None:
    from modules.traduction.acces import Clavier, Mac

    mac = Mac()
    etat.effacer("traduction_alerte")
    try:
        traducteur = _charger(ctx)
        if traducteur is None or not _autoriser(ctx, mac):
            return
        etat.effacer("traduction_alerte")
        points = queue.Queue()
        threading.Thread(target=_travailler, args=(ctx.arret, ctx.log, mac, traducteur, points), daemon=True).start()
        ctx.log.info("Traduction active : chaque phrase française finie par un point devient anglaise")
        if not Clavier(_signaler(points)).tourner(ctx.arret):
            _alerter(ctx, "autorisation", ALERTE_AUTORISATIONS)
            ctx.arret.wait()  # rien à faire tant que macOS refuse : éteins et rallume après l'avoir autorisé
    finally:
        etat.effacer("traduction_alerte")
        ctx.log.info("Traduction arrêtée")


# --- commandes à la main ----------------------------------------------------------------------------


def texte(phrase: str) -> int:
    from modules.traduction.phrase import finir_comme, langue, raison_de_ne_pas_traduire

    phrase = " ".join(phrase.split())
    if not phrase.endswith("."):
        phrase += "."
    raison = raison_de_ne_pas_traduire(phrase, p.mots_min())
    print(f"📝 « {phrase} »  (langue repérée : {langue(phrase[:-1]) or 'inconnue'})")
    if raison:
        print(f"   · ne serait pas traduite : {raison}")
        return 0
    try:
        traducteur = Traducteur()
        debut = time.time()
        anglais = finir_comme(traducteur.traduire(phrase))
    except ModeleAbsent as e:
        print(f"⛔ {e}")
        return 1
    print(f"🇬🇧 « {anglais} »  ({time.time() - debut:.1f} s, {NOMS[traducteur.nom]}, sur ton Mac)")
    return 0


NOMS = {"nllb": "grand modèle", "argos": "petit modèle"}


def comparer(phrase: str) -> int:
    """La même phrase par les deux modèles (ceux qui sont téléchargés), pour juger sur pièce."""
    from modules.traduction.phrase import finir_comme

    phrase = " ".join(phrase.split())
    print(f"📝 « {phrase} »")
    vus = 0
    for nom in ("nllb", "argos"):
        try:
            traducteur = Traducteur(moteur=nom)
        except ModeleAbsent:
            continue
        if traducteur.nom != nom:  # ce modèle-là n'est pas téléchargé
            continue
        debut = time.time()
        anglais = finir_comme(traducteur.traduire(phrase))
        print(f"   {NOMS[nom]:<13} « {anglais} »  ({time.time() - debut:.1f} s)")
        vus += 1
    if vus < 2:
        print("   (un seul modèle est là ; le grand : python -m modules.traduction --telecharger)")
    return 0 if vus else 1


def diagnostic() -> int:
    from modules.traduction import moteur
    from modules.yeux.__main__ import python_utilise

    ok = moteur.present()
    grand, petit = moteur._dossier_nllb() is not None, moteur._dossier_modele() is not None
    print(("✅" if grand else "⚠️ ") + f" Grand modèle (NLLB) : {'prêt' if grand else 'absent'} ({p.NLLB})")
    print(("✅" if petit else "· ") + f" Petit modèle (Argos) : {'prêt' if petit else 'absent'} ({p.MODELE})")
    print(f"   utilisé : {NOMS[p.moteur()] if (grand if p.moteur() == 'nllb' else petit) else 'celui qui est là'}"
          f" (réglage modules.traduction.moteur = « {p.moteur()} »)")
    if not grand:
        print("   → le grand modèle : python -m modules.traduction --telecharger")
    if sys.platform != "darwin":
        print("⛔ La lecture des phrases ne marche que sur un Mac.")
        return 1
    from modules.traduction.acces import Mac

    mac = Mac()
    saisie, acces = mac.saisie_autorisee(), mac.accessibilite_autorisee()
    print(("✅" if saisie else "⛔") + " Surveillance de l'entrée (voir le point tapé) : " + ("accordée" if saisie else "PAS ENCORE"))
    print(("✅" if acces else "⛔") + " Accessibilité (lire et remplacer la phrase) : " + ("accordée" if acces else "PAS ENCORE"))
    print("   (pour le Terminal ; pour la traduction en fond, c'est ce programme qui doit être autorisé :"
          f"\n    {python_utilise()})")
    if not (saisie and acces):
        print("   Réglages Système → Confidentialité et sécurité → Surveillance de l'entrée, puis Accessibilité :")
        print("   active « Terminal » (et « Python »). macOS te le demande maintenant ; ensuite quitte (Cmd + Q) et")
        print("   rouvre le Terminal, puis relance cette commande.")
        mac.demander_saisie()
        mac.accessibilite_autorisee(demander=True)
    if ok:
        return texte("Bonjour, je suis étudiant en comptabilité et je cherche une alternance.")
    return 0 if saisie and acces else 1


# Ce qui empêche de lire la phrase (et pas une phrase qu'on choisit de ne pas traduire) : le test explique.
BLOCAGES = ("aucune appli", "pas de champ", "texte illisible", "⛔")


class _JournalMuet:
    """En test, tout s'affiche ici (avec le détail d'une erreur) : rien n'est écrit dans le journal."""

    def info(self, *_):
        pass

    def exception(self, *_):
        traceback.print_exc()


class _Essai:
    """Le Mac pour de vrai en lecture, mais rien n'est remplacé ni copié : tout s'affiche ici."""

    def __init__(self, mac):
        self.mac = mac

    def __getattr__(self, nom):
        return getattr(self.mac, nom)

    def remplacer(self, champ, debut, longueur, nouveau, curseur_apres) -> bool:
        print(f"   🇬🇧 serait remplacée par : « {nouveau} »")
        return True

    def copier(self, texte_: str) -> None:
        print(f"   📋 serait copiée : « {texte_} »")

    def remplacer_au_clavier(self, combien, nouveau, depuis) -> bool:
        print(f"   🇬🇧 serait remplacée (mode clavier, {combien} caractères) par : « {nouveau} »")
        return True


def test() -> int:
    if sys.platform != "darwin":
        print("⛔ Ce module ne fonctionne que sur un Mac.")
        return 1
    from modules.traduction.acces import Clavier, Mac

    try:
        traducteur = Traducteur()
    except ModeleAbsent as e:
        print(f"⛔ {e}")
        return 1
    mac = _Essai(Mac())
    if not (mac.saisie_autorisee() and mac.accessibilite_autorisee()):
        print("⛔ Autorisations manquantes pour le Terminal : python -m modules.traduction --diagnostic")
        return 1
    print("MODE TEST : rien n'est remplacé ni gardé. Ouvre Notes (par ex.), tape une phrase en français finie par")
    print("un point, et regarde ici. Dans Pages et Keynote, ta phrase est sélectionnée un instant pour être lue")
    print("(⌥⇧↑ puis ⌘C, presse-papiers remis) : c'est normal, rien n'est modifié. Ctrl + C pour arrêter.\n")
    arret, points, deja = threading.Event(), queue.Queue(), set()

    def rapporter(resultat, appli):
        print(f"· {appli or '?'} : {resultat}")
        if resultat.startswith(BLOCAGES) and resultat not in deja:  # où ça bloque, étape par étape (une fois)
            deja.add(resultat)
            for ligne in mac.sonder():
                print(f"     {ligne}")

    try:
        threading.Thread(target=_travailler, args=(arret, _JournalMuet(), mac, traducteur, points, rapporter),
                         daemon=True).start()
        Clavier(_signaler(points)).tourner(arret)
    except KeyboardInterrupt:
        print("\nArrêt du test.")
    finally:
        arret.set()
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        executer("traduction", boucle)
        return 0
    parser = argparse.ArgumentParser(prog="python -m modules.traduction", description="Traduction des phrases")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--telecharger", action="store_true", help="télécharge le grand modèle (une fois, ~1,3 Go)")
    modes.add_argument("--telecharger-petit", action="store_true", help="télécharge le petit modèle (~100 Mo)")
    modes.add_argument("--texte", help="traduit une phrase ici")
    modes.add_argument("--comparer", help="la même phrase par les deux modèles")
    modes.add_argument("--diagnostic", action="store_true", help="modèle, autorisations, détection")
    modes.add_argument("--test", action="store_true", help="en direct, sans rien remplacer")
    args = parser.parse_args(argv)
    if args.telecharger or args.telecharger_petit:
        from modules.traduction.moteur import telecharger, telecharger_nllb

        try:
            (telecharger_nllb if args.telecharger else telecharger)()
        except Exception as e:  # réseau coupé, site indisponible… : rien n'est installé à moitié
            print(f"⛔ Téléchargement impossible : {e}")
            return 1
        if args.telecharger:
            print("   Si la traduction est allumée : éteins-la et rallume-la (icône 🇬🇧) pour passer au grand modèle.")
        return 0
    if args.texte is not None:
        return texte(args.texte)
    if args.comparer is not None:
        return comparer(args.comparer)
    if args.diagnostic:
        return diagnostic()
    return test()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
