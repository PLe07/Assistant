"""Le tri lui-même : mode test (lecture seule), création des étiquettes, passage réel."""

import contextlib
import fcntl
import logging
import time
from collections import Counter
from datetime import datetime

from googleapiclient.errors import HttpError

from core import config as config_coeur
from core import etat
from core.notifications import notifier
from modules.mails import parametres as config
from modules.mails.classificateur import classer
from modules.mails.gmail import (
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
from modules.mails.memoire import Memoire


def _court(texte: str, n: int) -> str:
    return texte if len(texte) <= n else texte[: n - 1] + "…"


def _nom_modele() -> str:
    modele = config.reglage("modele", "fort")
    reglages = config_coeur.charger()["claude"]
    return reglages.get(f"modele_{modele}", modele)


# --- Mode test (lecture seule) ---------------------------------------------------


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
    sources = Counter("IA" if c.source.startswith("IA") else "règle" for c in res.classements.values())
    resume = " · ".join(f"{b.etiquette} {compte.get(code, 0)}" for code, b in config.BACS.items())
    print(f"Résumé : {resume}")
    print(f"Décidés par une règle gratuite : {sources.get('règle', 0)} · par Claude : {sources.get('IA', 0)}")
    if res.appels:
        lus, ecrits = (f"{n:,}".replace(",", " ") for n in (res.tokens_entree, res.tokens_sortie))
        print(f"Consommation Claude ({_nom_modele()}) : {res.appels} appel(s), {lus} tokens lus, {ecrits} écrits")
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


def verifier_connexion() -> int:
    """Test de connexion à Gmail, en lecture seule (rouvre le navigateur si le jeton est mort)."""
    try:
        service = service_gmail(interactif=True)
        adresse = verifier_boite(service, config.GMAIL_ATTENDU)
        boite = service.users().labels().get(userId="me", id="INBOX").execute()
    except MauvaiseBoite as e:
        print(f"⛔ Mauvaise boîte : {e}")
        if config.TOKEN.exists():
            config.TOKEN.unlink()  # jeton du mauvais compte : on l'oublie
            print("   J'ai effacé le jeton Gmail. Relance la commande et choisis le bon compte.")
        return 1
    except ConnexionImpossible as e:
        print(f"⛔ {e}")
        return 1
    except HttpError as e:
        print(f"⛔ Gmail a répondu une erreur ({e.status_code}) : {e.reason}")
        return 1
    except OSError as e:
        print(f"⛔ Problème réseau : {e}")
        return 1
    print(f"✅ Connecté à {adresse} : c'est bien la boîte attendue.")
    print(f"   Boîte de réception : {boite['messagesTotal']} mails, dont {boite['messagesUnread']} non lus.")
    print("   Aucun mail n'a été modifié.")
    return 0


# --- Mode réel -------------------------------------------------------------------


@contextlib.contextmanager
def _verrou():
    """Un seul passage à la fois (évite qu'un passage manuel croise celui du superviseur)."""
    config.preparer_dossier()
    f = open(config.VERROU, "w")
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


def _alerter(message: str) -> None:
    """Le tri est bloqué : une notification (le garde anti-spam en limite le nombre)."""
    notifier("Assistant · mails", message, module="mails")


def passage_reel(memoire: Memoire, log: logging.Logger, interactif: bool, rattrapage_heures: float) -> Counter:
    bilan = Counter()
    service = service_gmail(interactif=interactif)
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
        if "Jeton Claude refusé" in erreur:
            _alerter("Le tri des mails est bloqué : jeton Claude refusé. Lance : python assistant.py renouveler-jeton")

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


def _echec(memoire: Memoire, log: logging.Logger, niveau: int, message: str) -> int:
    log.log(niveau, "%s", message)
    memoire.ecrire("derniere_erreur", f"{time.time()}|{message}")
    return 1


def un_passage(log: logging.Logger, interactif: bool, rattrapage_heures: float | None = None) -> int:
    """Un passage complet. Ne lève jamais d'exception : tout est noté dans le journal."""
    if rattrapage_heures is None:
        rattrapage_heures = float(config.reglage("rattrapage_premier_passage_heures", 24))
    with _verrou() as libre:
        if not libre:
            if interactif:
                print("Un passage est déjà en cours : réessaie dans une minute.")
            return 0
        memoire = Memoire()
        try:
            bilan = passage_reel(memoire, log, interactif, rattrapage_heures)
            memoire.ecrire("dernier_passage_ok", time.time())
        except ConnexionImpossible as e:
            _alerter(f"Le tri des mails est bloqué : {e}")
            return _echec(memoire, log, logging.ERROR, str(e))
        except MauvaiseBoite as e:
            _alerter(f"Le tri des mails est arrêté (mauvaise boîte) : {e}")
            return _echec(memoire, log, logging.ERROR, str(e))
        except HttpError as e:
            return _echec(memoire, log, logging.ERROR, f"Gmail a répondu une erreur ({e.status_code}) : {e.reason}")
        except OSError as e:
            return _echec(memoire, log, logging.WARNING, f"Problème réseau, nouvel essai au prochain passage : {e}")
        finally:
            memoire.fermer()

    tries = sum(n for k, n in bilan.items() if k in config.BACS)
    if tries or bilan:
        detail = " · ".join(f"{config.BACS[k].etiquette} {n}" for k, n in bilan.items() if k in config.BACS)
        log.info("Passage terminé : %d mail(s) trié(s)%s%s%s", tries, f" ({detail})" if detail else "",
                 f", {bilan['en_attente']} en attente" if bilan["en_attente"] else "",
                 f", {bilan['abandonne']} laissé(s) tel(s) quel(s)" if bilan["abandonne"] else "")
    elif interactif:
        print("Aucun nouveau mail à trier.")
    return 0


def claude_en_pause() -> bool:
    """Claude se repose après une panne (géré par le cœur) : inutile de relire Gmail."""
    pause = etat.lire("claude_pause_jusqua")
    return bool(pause) and time.time() < float(pause)


# --- État (python -m modules.mails --etat) ---------------------------------------------


def _il_y_a(horodatage: float) -> str:
    minutes = int((time.time() - horodatage) // 60)
    if minutes < 1:
        return "à l'instant"
    if minutes < 60:
        return f"il y a {minutes} min"
    if minutes < 48 * 60:
        return f"il y a {minutes // 60} h {minutes % 60:02d}"
    return f"le {datetime.fromtimestamp(horodatage):%d/%m à %H:%M}"


def afficher_etat() -> int:
    actif = config.reglage("actif", False)
    print(f"Module mails : {'✅ activé' if actif else '⚫ désactivé'} dans reglages.json"
          + (" · ⏸ PAUSE GLOBALE" if config_coeur.charger()["pause_globale"] else ""))
    memoire = Memoire()
    try:
        ok, erreur, depart = (memoire.lire(c) for c in ("dernier_passage_ok", "derniere_erreur", "date_depart"))
        lignes = memoire.db.execute("SELECT bac, traite_le FROM mails WHERE statut = 'etiquete'").fetchall()
    finally:
        memoire.fermer()
    print(f"Dernier passage réussi : {_il_y_a(float(ok)) if ok else 'aucun pour l’instant'}")
    if erreur:
        quand, _, message = erreur.partition("|")
        if not ok or float(quand) > float(ok):
            print(f"⚠️  Dernière erreur ({_il_y_a(float(quand))}) : {message}")
    if claude_en_pause():
        print("⏳ Claude indisponible pour l'instant : nouvel essai automatique dans quelques minutes.")
    if depart:
        print(f"Triés depuis la mise en service ({datetime.fromtimestamp(float(depart)):%d/%m/%Y %H:%M}) : {len(lignes)}")
    aujourdhui = datetime.now().strftime("%Y-%m-%d")
    du_jour = Counter(bac for bac, quand in lignes if (quand or "").startswith(aujourdhui))
    detail = " · ".join(f"{config.BACS[b].etiquette} {n}" for b, n in du_jour.items() if b in config.BACS)
    print(f"Aujourd'hui : {sum(du_jour.values())}" + (f"  ({detail})" if detail else ""))
    return 0
