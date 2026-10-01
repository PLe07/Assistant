"""Tri des mails : programme principal.

Pour l'instant : MODE TEST uniquement, en lecture seule.
    python trier.py --test 20

Le mode réel (pose des étiquettes) sera ajouté à l'étape 7, après ta validation.
"""

import argparse
import sys
from collections import Counter

from googleapiclient.errors import HttpError

import config
from classificateur import classer
from gmail_client import (
    ConnexionImpossible,
    MauvaiseBoite,
    lire_mail,
    lister_boite,
    service_gmail,
    verifier_boite,
)


def _court(texte: str, n: int) -> str:
    return texte if len(texte) <= n else texte[: n - 1] + "…"


def afficher(mails, res) -> None:
    print()
    for i, mail in enumerate(mails, 1):
        print(f"{i:>2}. {mail.date:%d/%m %H:%M} · {_court(mail.expediteur_nom, 28)} · « {_court(mail.objet, 60)} »")
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Tri automatique des mails")
    parser.add_argument("--test", type=int, metavar="N", help="classe les N derniers mails, sans rien modifier")
    args = parser.parse_args()
    if args.test is None:
        print("Pour l'instant, seul le mode test existe : python trier.py --test 20")
        return 2
    return mode_test(max(1, min(args.test, 50)))


if __name__ == "__main__":
    sys.exit(main())
