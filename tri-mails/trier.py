"""Tri des mails : programme principal.

    python trier.py --test 20            classe les 20 derniers mails, SANS rien modifier
    python trier.py --creer-etiquettes   crée les 5 étiquettes dans Gmail (aucun mail touché)
    python trier.py --reel               trie les nouveaux mails (pose les étiquettes)
    python trier.py --arriere-plan       pareil, sans rien afficher (utilisé par launchd)
"""

import argparse
import contextlib
import fcntl
import logging
import sys
import time
from collections import Counter
from datetime import datetime
from logging.handlers import RotatingFileHandler

from googleapiclient.errors import HttpError

import config
from classificateur import classer
from gmail_client import (
    ConnexionImpossible,
    MauvaiseBoite,
    appliquer_bac,
    creer_etiquette,
    etiquettes_existantes,
    lire_mail,
    lister_boite,
    service_gmail,
    verifier_boite,
)
from memoire import Memoire


def _court(texte: str, n: int) -> str:
    return texte if len(texte) <= n else texte[: n - 1] + "…"


def afficher(mails, res) -> None:
    print()
    for i, mail in enumerate(mails, 1):
        print(f"{i:>2}. {mail.date:%d/%m %H:%M} · {_court(mail.expediteur_nom, 28)} · « {_court(mail.objet, 60)} »")
        print(f"    <{mail.expediteur_adresse}>")
        c = res.classements.get(mail.id)
        if c is None:
            print("    ❔ Non classé (erreur, voir plus bas)")
        else:
            temps = "oui" if c.vaut_mon_temps else "non"
            print(f"    {config.BACS[c.bac].etiquette} · {c.source} · vaut ton temps : {temps}")
            print(f"    → {c.raison}")
        print()

    compte = Counter(c.bac for c in res.classements.values())
    sources = Counter("IA" if c.source == "IA" else "règle" for c in res.classements.values())
    resume = " · ".join(f"{b.etiquette} {compte.get(code, 0)}" for code, b in config.BACS.items())
    print(f"Résumé : {resume}")
    print(f"Décidés par une règle gratuite : {sources.get('règle', 0)} · par Claude : {sources.get('IA', 0)}")
    if res.appels:
        lus, ecrits = (f"{n:,}".replace(",", " ") for n in (res.tokens_entree, res.tokens_sortie))
        print(f"Consommation Claude ({config.MODELE}) : {res.appels} appel(s), {lus} tokens lus, {ecrits} écrits")
    for e in res.erreurs:
        print(f"⚠️  {e}")


def mode_test(nombre: int) -> int:
    try:
        service = service_gmail(interactif=True)
        moi = verifier_boite(service, config.GMAIL_ATTENDU)
        ids = lister_boite(service, nombre)
        mails = []
        for i, mail_id in enumerate(ids, 1):
            print(f"\rLecture des mails… {i}/{len(ids)}", end="", flush=True)
            mails.append(lire_mail(service, mail_id, moi, config.LONGUEUR_EXTRAIT))
        print()
    except (ConnexionImpossible, MauvaiseBoite) as e:
        print(f"⛔ {e}")
        return 1
    except HttpError as e:
        print(f"⛔ Gmail a répondu une erreur ({e.status_code}) : {e.reason}")
        return 1
    except OSError as e:
        print(f"⛔ Problème réseau : {e}")
        return 1

    res = classer(mails, au_fil=print)
    afficher(mails, res)
    print("\n✅ MODE TEST : aucun mail n'a été modifié.")
    return 0 if not res.erreurs else 1


def mode_creer_etiquettes() -> int:
    """Crée les étiquettes manquantes. Ne touche à aucun mail. Peut être relancé sans risque."""
    try:
        service = service_gmail(interactif=True)
        verifier_boite(service, config.GMAIL_ATTENDU)
        existantes = etiquettes_existantes(service)
        for bac in config.BACS.values():
            if bac.etiquette in existantes:
                print(f"  = {bac.etiquette} : existe déjà")
            else:
                creer_etiquette(service, bac.etiquette, bac.fond, bac.texte)
                print(f"  + {bac.etiquette} : créée")
    except (ConnexionImpossible, MauvaiseBoite) as e:
        print(f"⛔ {e}")
        return 1
    except HttpError as e:
        print(f"⛔ Gmail a refusé ({e.status_code}) : {e.reason}")
        return 1
    except OSError as e:
        print(f"⛔ Problème réseau : {e}")
        return 1
    print("\n✅ Étiquettes prêtes. Aucun mail n'a été modifié.")
    return 0


# --- Mode réel -------------------------------------------------------------------


def _journal(console: bool) -> logging.Logger:
    """Journal dans logs/tri.log (1 Mo max × 4 fichiers) et, à la main, à l'écran."""
    config.DOSSIER_LOGS.mkdir(exist_ok=True)
    log = logging.getLogger("tri")
    log.setLevel(logging.INFO)
    if not log.handlers:
        fichier = RotatingFileHandler(
            config.DOSSIER_LOGS / "tri.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        fichier.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"))
        log.addHandler(fichier)
        if console:
            ecran = logging.StreamHandler(sys.stdout)
            ecran.setFormatter(logging.Formatter("%(message)s"))
            log.addHandler(ecran)
    return log


@contextlib.contextmanager
def _verrou():
    """Un seul passage à la fois (évite qu'un passage manuel croise celui de launchd)."""
    f = open(config.DOSSIER / ".verrou", "w")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        yield False
        return
    try:
        yield True
    finally:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def _ids_etiquettes(service, log) -> dict:
    """Code du bac → identifiant de l'étiquette Gmail (recrée une étiquette supprimée)."""
    existantes = etiquettes_existantes(service)
    ids = {}
    for code, bac in config.BACS.items():
        if bac.etiquette not in existantes:
            existantes[bac.etiquette] = creer_etiquette(service, bac.etiquette, bac.fond, bac.texte)
            log.info("Étiquette recréée : %s", bac.etiquette)
        ids[code] = existantes[bac.etiquette]
    return ids


def passage_reel(memoire: Memoire, log: logging.Logger, arriere_plan: bool, rattrapage_heures: float) -> Counter:
    bilan = Counter()
    service = service_gmail(interactif=not arriere_plan)
    moi = verifier_boite(service, config.GMAIL_ATTENDU)

    depart = memoire.lire("date_depart")
    if depart is None:
        depart = time.time() - rattrapage_heures * 3600
        memoire.ecrire("date_depart", depart)
        log.info("Mise en service : seuls les mails reçus après le %s seront triés.",
                 f"{datetime.fromtimestamp(depart):%d/%m/%Y %H:%M}")
    depart = float(depart)

    etiquettes = _ids_etiquettes(service, log)
    nos_etiquettes = set(etiquettes.values())

    ids = lister_boite(service, 500, requete=f"after:{int(depart)}")
    connus = memoire.connus(ids)
    nouveaux = [i for i in ids if i not in connus][: config.MAX_PAR_PASSAGE]

    mails = []
    for mail_id in nouveaux:
        mail = lire_mail(service, mail_id, moi, config.LONGUEUR_EXTRAIT)
        if mail.date.timestamp() < depart:
            memoire.noter(mail_id, "avant_mise_en_service", mail)
        elif nos_etiquettes & set(mail.libelles):
            memoire.noter(mail_id, "deja_etiquete", mail)  # déjà trié (par toi ou par un passage interrompu)
        else:
            mails.append(mail)
    if not mails:
        return bilan

    res = classer(mails)
    for erreur in res.erreurs:
        log.warning(erreur)
    if res.indisponible:
        memoire.ecrire("pause_jusqua", time.time() + config.PAUSE_APRES_PANNE_MINUTES * 60)

    for mail in mails:
        c = res.classements.get(mail.id)
        if c is None:
            if mail.id in res.non_tentes:
                bilan["en_attente"] += 1  # Claude en panne : retenté plus tard, sans pénalité
            elif memoire.noter_echec(mail.id) >= config.TENTATIVES_MAX:
                memoire.noter(mail.id, "abandonne", mail)
                log.warning("Laissé tel quel après %d essais : %s · « %s »",
                            config.TENTATIVES_MAX, mail.expediteur_nom, mail.objet)
                bilan["abandonne"] += 1
            else:
                bilan["en_attente"] += 1
            continue
        bac = config.BACS[c.bac]
        try:
            appliquer_bac(service, mail.id, etiquettes[c.bac], bac.archiver)
        except HttpError as e:
            if e.status_code == 404:  # supprimé entre-temps par toi
                memoire.noter(mail.id, "introuvable", mail)
                continue
            raise
        memoire.noter(mail.id, "etiquete", mail, c)
        bilan[c.bac] += 1
        log.info("%s%s · %s · %s · « %s »", bac.etiquette, " (archivé)" if bac.archiver else "",
                 c.source, _court(mail.expediteur_nom, 30), _court(mail.objet, 70))
    return bilan


def mode_reel(arriere_plan: bool, rattrapage_heures: float) -> int:
    log = _journal(console=not arriere_plan)
    if config.FICHIER_PAUSE.exists():
        if not arriere_plan:
            print("⏸  En pause (fichier PAUSE présent). Pour reprendre : rm PAUSE")
        return 0
    with _verrou() as libre:
        if not libre:
            if not arriere_plan:
                print("Un passage est déjà en cours : réessaie dans une minute.")
            return 0
        memoire = Memoire()
        try:
            pause = memoire.lire("pause_jusqua")
            if arriere_plan and pause and time.time() < float(pause):
                return 0  # Claude était en panne il y a peu : on le laisse souffler
            bilan = passage_reel(memoire, log, arriere_plan, rattrapage_heures)
        except (ConnexionImpossible, MauvaiseBoite) as e:
            log.error("%s", e)
            return 1
        except HttpError as e:
            log.error("Gmail a répondu une erreur (%s) : %s", e.status_code, e.reason)
            return 1
        except OSError as e:
            log.warning("Problème réseau, nouvel essai au prochain passage : %s", e)
            return 1
        finally:
            memoire.fermer()

    tries = sum(n for k, n in bilan.items() if k in config.BACS)
    if tries or bilan:
        detail = " · ".join(f"{config.BACS[k].etiquette} {n}" for k, n in bilan.items() if k in config.BACS)
        log.info("Passage terminé : %d mail(s) trié(s)%s%s%s", tries, f" ({detail})" if detail else "",
                 f", {bilan['en_attente']} en attente" if bilan["en_attente"] else "",
                 f", {bilan['abandonne']} laissé(s) tel(s) quel(s)" if bilan["abandonne"] else "")
    elif not arriere_plan:
        print("Aucun nouveau mail à trier.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Tri automatique des mails")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--test", type=int, metavar="N", help="classe les N derniers mails, sans rien modifier")
    modes.add_argument("--creer-etiquettes", action="store_true", help="crée les 5 étiquettes dans Gmail")
    modes.add_argument("--reel", action="store_true", help="trie les nouveaux mails (pose les étiquettes)")
    modes.add_argument("--arriere-plan", action="store_true", help="comme --reel, sans affichage (launchd)")
    parser.add_argument(
        "--rattrapage-heures", type=float, default=config.RATTRAPAGE_PREMIER_PASSAGE_HEURES,
        help="1er passage uniquement : trier aussi les mails des N dernières heures",
    )
    args = parser.parse_args()
    if args.creer_etiquettes:
        return mode_creer_etiquettes()
    if args.reel or args.arriere_plan:
        return mode_reel(args.arriere_plan, max(0.0, args.rattrapage_heures))
    return mode_test(max(1, min(args.test, 50)))


if __name__ == "__main__":
    sys.exit(main())
