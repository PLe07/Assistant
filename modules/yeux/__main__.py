"""Module « yeux » : regarde la fenêtre au premier plan pour repérer quand tu bloques.

Sous le superviseur (sans option) : observe en fond, rien n'est conservé.

À la main, dans ~/Assistant avec .venv activé :
    python -m modules.yeux --diagnostic             vérifie l'autorisation et la capture (rien n'est gardé ni affiché)
    python -m modules.yeux --une-fois [--delai 5]   lit UNE fois la fenêtre au premier plan et montre le texte
                                                    tel qu'il partirait à Claude (rien n'est gardé)
    python -m modules.yeux --test [--rapide] [--avec-claude]
                                                    en direct : ce qui est vu et ce qui déclencherait,
                                                    sans notification (--rapide : délais divisés par 10)
    python -m modules.yeux --texte "Erreur : …" [--avec-claude]   teste un texte, sans capture
    python -m modules.yeux --mode journal|reel      journal : note ce qui aurait déclenché, sans appeler Claude
    python -m modules.yeux --essai                  essai guidé, en vrai : bouton, erreur à l'écran, couper l'écran
"""

import argparse
import sys
import threading
import time

from core import config, etat
from core.journal import journal
from core.mac import sur_secteur
from core.module import executer
from core.notifications import notifier
from modules.yeux import parametres as p

ALERTE_ECRAN = ("Les yeux n'ont pas l'autorisation de voir l'écran : Réglages Système → Confidentialité et "
                "sécurité → Enregistrement de l'écran → active « Python », puis coupe et rallume l'écran (icône).")


def _ecran_interdit() -> bool:
    r = config.charger()
    return r["pause_globale"] or r["pause_ecran"]


def observer(arret, log, obs, interactif: bool = False) -> None:
    """La boucle d'observation, commune au mode normal et au mode test."""
    prochain, erreurs = 0.0, set()
    while not arret.is_set():
        maintenant = time.time()
        try:  # une erreur de macOS sur un coup d'œil ne doit jamais arrêter les yeux
            if maintenant >= prochain:
                prochain = maintenant + (min(p.intervalle(), 10) if interactif else p.intervalle())
                if p.reglage("uniquement_sur_secteur", False) and not sur_secteur():
                    obs.detecteur.oublier()
                elif obs.capteur.absent(p.ABSENT_APRES):
                    obs.detecteur.oublier()  # tu n'es pas là (ou écran verrouillé) : on ne regarde pas
                    if interactif:
                        obs.annoncer("💤 Tu sembles absent (ou l'écran est verrouillé) : rien n'est capturé")
                else:
                    obs.regarder()
            if not interactif:
                obs.servir_captures()
                obs.servir_demandes()
                obs.oublier()
        except Exception as e:
            if str(e) not in erreurs:  # chaque erreur différente est notée une fois (avec le détail)
                erreurs.add(str(e))
                log.exception("Coup d'œil en erreur (les yeux continuent)")
            if interactif:
                obs.annoncer(f"⚠️ Coup d'œil en erreur : {e}")
        if interactif:
            if _ecran_interdit():
                print("\n⏸  Écran coupé (pause ou bouton de l'icône) : test arrêté.")
                break
            etat.ecrire("ecran_test", time.time())  # 👁 sur l'icône pendant le test aussi
        arret.wait(1)
    if interactif:
        etat.effacer("ecran_test")


def boucle(ctx) -> None:
    from modules.yeux.observation import Observation

    # Si l'observation précédente a été coupée net, ses aides en attente ne peuvent plus être rédigées.
    etat.expirer_aides("yeux", "Cette aide a expiré : l'observation a redémarré entre-temps.")
    etat.effacer("yeux_regard")
    obs = Observation(ctx.log)
    try:
        if not obs.capteur.autorise():
            obs.capteur.demander_autorisation()
            etat.ecrire("yeux_alerte", "autorisation")
            ctx.log.error("Enregistrement de l'écran non autorisé pour Python (%s) : rien n'est capturé", python_utilise())
            notifier("Assistant", ALERTE_ECRAN, module="yeux", urgent=True)  # tu dois pouvoir agir, même la nuit
            while not obs.capteur.autorise():  # macOS ne le prend souvent en compte qu'au redémarrage
                for a in etat.aides_a_capturer("yeux"):
                    etat.finir_aide(a["id"], ALERTE_ECRAN, "echec")
                if ctx.arret.wait(30):
                    return
            etat.effacer("yeux_alerte")
        ctx.log.info("Observation active (mode %s)", p.mode())
        observer(ctx.arret, ctx.log, obs)
    finally:
        obs.arreter()  # efface tout ce qui restait en mémoire
        etat.effacer("yeux_regard")
        etat.effacer("yeux_alerte")
        ctx.log.info("Observation arrêtée")


def python_utilise() -> str:
    """Le programme que macOS doit autoriser (pour le bouton « + » des Réglages si besoin)."""
    import os

    reel = os.path.realpath(sys.executable)
    if "Python.framework/Versions/" in reel:
        base = reel.split("Python.framework/Versions/")[0] + "Python.framework/Versions/"
        version = reel.split("Python.framework/Versions/")[1].split("/")[0]
        return f"{base}{version}/Resources/Python.app"
    return reel


# --- commandes à la main ----------------------------------------------------------------


def diagnostic() -> int:
    if sys.platform != "darwin":
        print("⛔ Ce module ne fonctionne que sur un Mac.")
        return 1
    from modules.yeux import capture
    from modules.yeux.filtres import exclue, ignoree

    ok = capture.autorise()
    print(("✅" if ok else "⛔") + " Autorisation « Enregistrement de l'écran » : " + ("accordée" if ok else "PAS ENCORE")
          + " (pour le Terminal)")
    print(f"   Pour l'observation en fond, c'est ce programme qui doit être autorisé : {python_utilise()}")
    if not ok:
        print("   macOS va te la demander. Accorde-la au Terminal, puis QUITTE le Terminal (Cmd + Q),")
        print("   rouvre-le et relance cette commande.")
        capture.demander_autorisation()
        return 1
    f = capture.fenetre_au_premier_plan()
    if f is None:
        print("⛔ Aucune fenêtre trouvée au premier plan.")
        return 1
    print(f"✅ Fenêtre au premier plan : {f['appli']}")
    raison = exclue(f, p.applis_exclues(), p.titres_exclus()) or ignoree(f, p.APPLIS_IGNOREES)
    print(f"   {'🙈 pas regardée (' + raison + ') : en vrai, elle ne serait pas capturée' if raison else 'pas exclue'}")
    print(f"   Absent ? {'oui' if capture.inactif_depuis() > p.ABSENT_APRES else 'non'} · écran verrouillé ? "
          f"{'oui' if capture.ecran_verrouille() else 'non'}")
    for methode in ("ScreenCaptureKit", "CoreGraphics"):
        debut = time.time()
        image, info = capture.capturer(f["id"], methode)
        if image is None:
            print(f"⚠️  Capture {methode} : échec ({info})")
            continue
        lignes = capture.lire_texte(image)
        del image
        print(f"✅ Capture {methode} + lecture : {len(lignes)} lignes lues en {time.time() - debut:.1f} s (rien n'est gardé)")
    return 0


def une_fois(delai: int) -> int:
    if sys.platform != "darwin":
        print("⛔ Ce module ne fonctionne que sur un Mac.")
        return 1
    from modules.yeux import capture
    from modules.yeux.declencheurs import signaux
    from modules.yeux.filtres import exclue, extrait, ignoree

    for reste in range(delai, 0, -1):
        print(f"\rPasse sur la fenêtre à lire… {reste} ", end="", flush=True)
        time.sleep(1)
    print()
    f = capture.fenetre_au_premier_plan()
    if f is None:
        print("⛔ Aucune fenêtre trouvée au premier plan.")
        return 1
    raison = exclue(f, p.applis_exclues(), p.titres_exclus()) or ignoree(f, p.APPLIS_IGNOREES)
    if raison:
        print(f"🙈 {f['appli']} : {raison}. Rien n'a été capturé.")
        return 0
    lignes = capture.Capteur().lire(f)
    if lignes is None:
        print("⛔ Capture impossible : lance  python -m modules.yeux --diagnostic")
        return 1
    print(f"Texte lu dans « {f['appli']} » ({len(lignes)} lignes), tel qu'il partirait à Claude :\n")
    print(extrait(f, lignes, None, p.EXTRAIT_MAX))
    trouves = sorted({t for t, _ in signaux(lignes)})
    print(f"\nSignaux repérés : {', '.join(trouves) if trouves else 'aucun'}")
    print("Rien n'a été gardé : ni l'image, ni le texte.")
    return 0


def mode_test(rapide: bool, avec_claude: bool) -> int:
    from modules.yeux.observation import Observation

    if sys.platform != "darwin":
        print("⛔ Ce module ne fonctionne que sur un Mac.")
        return 1
    if _ecran_interdit():
        print("⏸  L'écran est coupé (pause globale ou « ecran off ») : rallume-le d'abord.")
        return 1
    if rapide:
        for cle in p.DELAIS:
            p.DELAIS[cle] //= 10
    print("MODE TEST : rien n'est gardé, aucune notification." + (" Claude est consulté (quota)." if avec_claude else ""))
    print(f"Délais : {', '.join(f'{t} {s} s' for t, s in p.DELAIS.items())}. Un coup d'œil toutes les 10 s.")
    print("👁  Passe sur d'autres fenêtres (Ctrl + C ici pour arrêter)\n")
    obs = Observation(journal("yeux"), test=True, avec_claude=avec_claude)
    arret = threading.Event()
    try:
        observer(arret, journal("yeux"), obs, interactif=True)
    except KeyboardInterrupt:
        print("\nArrêt du test.")
    finally:
        arret.set()
        etat.effacer("ecran_test")
        obs.arreter()
    return 0


def tester_texte(texte: str, avec_claude: bool) -> int:
    from modules.yeux.declencheurs import signaux
    from modules.yeux.filtres import extrait
    from modules.yeux.observation import Observation

    lignes = texte.replace("\\n", "\n").splitlines()
    trouves = signaux(lignes)
    if not trouves:
        print("· rien de détecté")
        return 0
    obs = Observation(journal("yeux"), test=True, avec_claude=avec_claude)
    f = {"appli": "Test", "titre": ""}
    par_type: dict[str, list[int]] = {}  # une erreur sur plusieurs lignes = UN signal, comme en vrai
    for (type_, _), idx in trouves.items():
        par_type.setdefault(type_, []).extend(idx)
    for type_, idx in sorted(par_type.items()):
        idx = sorted(set(idx))
        print(f"⚡ signal « {type_} » : déclencherait après {p.DELAIS[type_] // 60} min à l'écran"
              if p.DELAIS[type_] else f"⚡ signal « {type_} » : déclencherait aussitôt")
        if avec_claude:
            print("   … Claude réfléchit")
            obs._decider(f"Signal repéré : {type_}\n{extrait(f, lignes, idx, p.EXTRAIT_MAX)}", type_, False, "")
    obs.arreter()
    return 0


def changer_mode(mode: str) -> int:
    config._modifier(lambda r: r.setdefault("modules", {}).setdefault("yeux", {}).__setitem__("mode", mode))
    print("📒 Mode journal : ce qui aurait déclenché est noté dans le journal, Claude n'est pas appelé."
          if mode == "journal" else "👁  Mode réel : les vraies aides 💡 sont proposées.")
    print("   Pris en compte dès le prochain coup d'œil.")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        executer("yeux", boucle)
        return 0
    parser = argparse.ArgumentParser(prog="python -m modules.yeux", description="Conscience de l'écran")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--diagnostic", action="store_true", help="vérifie l'autorisation et la capture")
    modes.add_argument("--une-fois", action="store_true", help="lit une fois la fenêtre au premier plan")
    modes.add_argument("--test", action="store_true", help="en direct, sans rien déclencher")
    modes.add_argument("--texte", help="teste un texte, sans capture")
    modes.add_argument("--mode", choices=["journal", "reel"], help="journal (sans Claude) ou reel")
    modes.add_argument("--essai", action="store_true", help="essai guidé, en vrai, de bout en bout")
    parser.add_argument("--delai", type=int, default=5, help="--une-fois : secondes pour changer de fenêtre")
    parser.add_argument("--rapide", action="store_true", help="--test : délais divisés par 10")
    parser.add_argument("--avec-claude", action="store_true", help="montre aussi l'avis de Claude (quota)")
    parser.add_argument("--etape", type=int, choices=[1, 2, 3], help="--essai : une seule étape")
    args = parser.parse_args(argv)
    if args.diagnostic:
        return diagnostic()
    if args.une_fois:
        return une_fois(max(0, args.delai))
    if args.texte is not None:
        return tester_texte(args.texte, args.avec_claude)
    if args.mode:
        return changer_mode(args.mode)
    if args.essai:
        from modules.yeux.essai import essai

        return essai(args.etape)
    return mode_test(args.rapide, args.avec_claude)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
