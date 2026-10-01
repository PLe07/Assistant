"""Ton brief du jour, quand TU le demandes (icône → ☀️ Mon brief, ou python assistant.py brief).

Tout est lu SUR TON MAC, aucun appel à Claude, rien n'est modifié :
- 📅 l'agenda du jour : l'app Calendrier, via EventKit (la bibliothèque de macOS, qui voit aussi les
  événements qui se répètent, comme tes cours de chaque semaine) ;
- 📬 les mails à traiter : ceux que le tri a mis en 🔴 Important-Répondre ou ⏰ Action-Deadline et qui sont
  encore dans ta boîte de réception (Gmail, lecture seule) ;
- ⏰ les rappels du jour : l'app Rappels (ceux d'aujourd'hui, et ceux en retard).
Un bloc qui ne répond pas (autorisation, Gmail…) est signalé, les autres s'affichent quand même.
"""

import subprocess
import threading
import time
from datetime import datetime, timedelta

from core.journal import journal
from core.rappels import JOURS, MOIS

log = journal("brief")

ETIQUETTES = ["🔴 Important-Répondre", "⏰ Action-Deadline"]
MAILS_MAX = 5  # par étiquette
RAPPELS_MAX = 12
AUTORISATION_CALENDRIER = ("macOS n'autorise pas encore l'accès au Calendrier : Réglages Système → Confidentialité "
                           "et sécurité → Calendriers → autorise « Python » (et « Terminal »)")


class BlocIndisponible(Exception):
    """Le message dit pourquoi ce bloc manque, simplement."""


def _jour(maintenant: datetime | None = None) -> tuple[datetime, datetime]:
    debut = (maintenant or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    return debut, debut + timedelta(days=1)


# --- 📅 L'agenda : EventKit, sinon AppleScript --------------------------------------------------------


def _acces_calendrier(EventKit, store) -> tuple[bool, str]:
    """(accès accordé ?, détail pour comprendre un refus). Demande l'accès la première fois."""
    statut = EventKit.EKEventStore.authorizationStatusForEntityType_(EventKit.EKEntityTypeEvent)
    if statut == 3:  # accès complet
        return True, ""
    if statut != 0:  # 1 restreint, 2 refusé, 4 écriture seule
        return False, f"statut macOS {statut}"
    details = []
    # macOS 14 et plus : « accès complet » ; sinon (ou si le programme ne le déclare pas) : la demande d'avant.
    for methode in ("requestFullAccessToEventsWithCompletion_", "requestAccessToEntityType_completion_"):
        if not hasattr(store, methode):
            continue
        reponse, fini = [False, ""], threading.Event()

        def recu(accorde, erreur, reponse=reponse, fini=fini):
            reponse[0], reponse[1] = bool(accorde), str(erreur or "")
            fini.set()

        if methode.startswith("requestFull"):
            store.requestFullAccessToEventsWithCompletion_(recu)
        else:
            store.requestAccessToEntityType_completion_(EventKit.EKEntityTypeEvent, recu)
        fini.wait(120)  # le temps que tu cliques « Autoriser »
        if reponse[0]:
            return True, ""
        details.append(reponse[1][:100] or "refusé")
    return False, " / ".join(details)


def _agenda_eventkit(maintenant: datetime | None) -> list[dict]:
    """Par EventKit : voit aussi les événements qui se répètent. Lève BlocIndisponible sans accès."""
    try:
        import EventKit
        from Foundation import NSDate
    except ImportError:
        raise BlocIndisponible("lecture du Calendrier impossible ici (pip install -r requirements.txt, sur ton Mac)")
    store = EventKit.EKEventStore.alloc().init()
    accorde, detail = _acces_calendrier(EventKit, store)
    if not accorde:
        raise BlocIndisponible(f"{AUTORISATION_CALENDRIER} [{detail}]")
    debut, fin = _jour(maintenant)
    predicat = store.predicateForEventsWithStartDate_endDate_calendars_(
        NSDate.dateWithTimeIntervalSince1970_(debut.timestamp()), NSDate.dateWithTimeIntervalSince1970_(fin.timestamp()),
        None)
    return [{"debut": datetime.fromtimestamp(e.startDate().timeIntervalSince1970()),
             "fin": datetime.fromtimestamp(e.endDate().timeIntervalSince1970()),
             "titre": str(e.title() or "(sans titre)"), "lieu": str(e.location() or ""), "journee": bool(e.isAllDay())}
            for e in store.eventsMatchingPredicate_(predicat) or []]


# Lit seulement : aucun événement n'est créé ni modifié. (Limite d'AppleScript : un événement qui se répète
# n'apparaît que le jour de sa première occurrence.)
SCRIPT_AGENDA = """on iso(d)
set texteDate to (year of d as string) & "-" & text -2 thru -1 of ("0" & ((month of d) as integer))
set texteDate to texteDate & "-" & text -2 thru -1 of ("0" & (day of d))
return texteDate & "T" & text -2 thru -1 of ("0" & (hours of d)) & ":" & text -2 thru -1 of ("0" & (minutes of d)) & ":00"
end iso
on run
set debut to current date
set hours of debut to 0
set minutes of debut to 0
set seconds of debut to 0
set fin to debut + 86400
set sortie to ""
tell application "Calendar"
repeat with c in calendars
repeat with e in (every event of c whose start date is greater than or equal to debut and start date is less than fin)
set lieu to location of e
if lieu is missing value then set lieu to ""
set sortie to sortie & (summary of e) & tab & (my iso(start date of e)) & tab & (my iso(end date of e)) & tab & ((allday event of e) as string) & tab & lieu & linefeed
end repeat
end repeat
end tell
return sortie
end run"""


def _agenda_applescript() -> list[dict]:
    evenements = []
    for ligne in _osascript(SCRIPT_AGENDA, "Calendrier").splitlines():
        morceaux = ligne.split("\t")
        if len(morceaux) != 5:
            continue
        try:
            debut, fin = datetime.fromisoformat(morceaux[1]), datetime.fromisoformat(morceaux[2])
        except ValueError:
            continue
        evenements.append({"debut": debut, "fin": fin, "titre": morceaux[0].strip() or "(sans titre)",
                           "lieu": morceaux[4].strip(), "journee": morceaux[3].strip() == "true"})
    return evenements


def agenda(maintenant: datetime | None = None) -> tuple[list[dict], str]:
    """(événements du jour triés, remarque). EventKit d'abord ; sans son accès, AppleScript (comme Rappels)."""
    try:
        evenements, remarque = _agenda_eventkit(maintenant), ""
    except BlocIndisponible as e:
        log.info("Brief : agenda par EventKit impossible, lecture par AppleScript")
        try:
            evenements = _agenda_applescript()
        except BlocIndisponible as e2:
            raise BlocIndisponible(f"{e} · AppleScript : {e2}")
        remarque = ("lu par AppleScript : un cours qui se répète peut manquer. Pour tout voir : " + str(e))
    return sorted(evenements, key=lambda x: (not x["journee"], x["debut"])), remarque


# --- 📬 Les mails à traiter (Gmail, lecture seule) -------------------------------------------------


def mails_a_traiter() -> dict[str, list[dict]]:
    """Étiquette → [{de, objet, date}] des mails encore dans ta boîte de réception."""
    from email.utils import parseaddr

    from modules.mails import parametres as mp
    from modules.mails.gmail import _decoder_entete, etiquettes_existantes, service_gmail, verifier_boite

    try:
        service = service_gmail(interactif=False)
        verifier_boite(service, mp.GMAIL_ATTENDU)
        ids_etiquettes = etiquettes_existantes(service)
    except Exception as e:
        raise BlocIndisponible(f"Gmail injoignable ({type(e).__name__} : python -m modules.mails --verifier-connexion)")
    resultat = {}
    for nom in ETIQUETTES:
        if nom not in ids_etiquettes:
            resultat[nom] = []
            continue
        rep = service.users().messages().list(userId="me", labelIds=["INBOX", ids_etiquettes[nom]],
                                              maxResults=MAILS_MAX).execute()
        mails = []
        for m in rep.get("messages", []):
            msg = service.users().messages().get(userId="me", id=m["id"], format="metadata",
                                                 metadataHeaders=["From", "Subject"]).execute()
            entetes = {h["name"].lower(): _decoder_entete(h["value"]) for h in msg["payload"].get("headers", [])}
            nom_de, adresse = parseaddr(entetes.get("from", ""))
            mails.append({"de": nom_de or adresse, "objet": entetes.get("subject", "").strip() or "(sans objet)",
                          "date": datetime.fromtimestamp(int(msg.get("internalDate", 0)) / 1000)})
        resultat[nom] = mails
    return resultat


# --- ⏰ Les rappels du jour (app Rappels, comme core/rappels.py) -----------------------------------

# Lit seulement : aucun rappel n'est créé, modifié ni coché.
SCRIPT_RAPPELS = """on iso(d)
set texteDate to (year of d as string) & "-" & text -2 thru -1 of ("0" & ((month of d) as integer))
set texteDate to texteDate & "-" & text -2 thru -1 of ("0" & (day of d))
return texteDate & "T" & text -2 thru -1 of ("0" & (hours of d)) & ":" & text -2 thru -1 of ("0" & (minutes of d)) & ":00"
end iso
on run
set fin to current date
set hours of fin to 23
set minutes of fin to 59
set seconds of fin to 59
set sortie to ""
tell application "Reminders"
repeat with l in lists
set nomListe to name of l
set lesNoms to name of (reminders of l whose completed is false)
set lesDates to due date of (reminders of l whose completed is false)
repeat with i from 1 to count of lesNoms
set d to item i of lesDates
if d is not missing value then
if d is less than or equal to fin then set sortie to sortie & (item i of lesNoms) & tab & (my iso(d)) & tab & nomListe & linefeed
end if
end repeat
end repeat
end tell
return sortie
end run"""


def _osascript(script: str, appli: str) -> str:
    lignes = [x for ligne in script.splitlines() for x in ("-e", ligne)]
    try:
        r = subprocess.run(["osascript", *lignes], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise BlocIndisponible(f"l'app {appli} ne répond pas ({type(e).__name__})")
    if r.returncode != 0:
        erreur = (r.stderr or "").strip()
        if "-1743" in erreur or "not allowed" in erreur.lower() or "pas autoris" in erreur.lower():
            raise BlocIndisponible(f"macOS n'autorise pas encore l'Assistant à lire {appli} : Réglages Système → "
                                   f"Confidentialité et sécurité → Automatisation → autorise « {appli} »")
        raise BlocIndisponible(f"l'app {appli} a renvoyé une erreur ({erreur[:160]})")
    return r.stdout


def rappels_du_jour() -> list[dict]:
    """[{quoi, quand, liste, en_retard}] : les rappels pas faits, prévus aujourd'hui ou avant."""
    sortie = _osascript(SCRIPT_RAPPELS, "Rappels")
    debut, _ = _jour()
    rappels = []
    for ligne in sortie.splitlines():
        morceaux = ligne.split("\t")
        if len(morceaux) != 3:
            continue
        try:
            quand = datetime.fromisoformat(morceaux[1].strip())
        except ValueError:
            continue
        rappels.append({"quoi": morceaux[0].strip(), "quand": quand, "liste": morceaux[2].strip(),
                        "en_retard": quand < debut})
    return sorted(rappels, key=lambda x: x["quand"])[:RAPPELS_MAX]


# --- Le brief ----------------------------------------------------------------------------------------


def _bloc(lire):
    try:
        return lire(), ""
    except BlocIndisponible as e:
        return None, str(e)
    except Exception as e:  # un bloc ne doit jamais empêcher les autres
        log.exception("Brief : un bloc a échoué")
        return None, f"erreur inattendue ({type(e).__name__}, voir le journal)"


def composer(maintenant: datetime | None = None) -> str:
    maintenant = maintenant or datetime.now()
    debut = time.time()
    lignes = [f"☀️ Brief du {JOURS[maintenant.weekday()]} {maintenant.day} {MOIS[maintenant.month - 1]}"]

    lu, erreur = _bloc(lambda: agenda(maintenant))
    evenements, remarque = lu if lu else (None, "")
    lignes.append(f"\n📅 Agenda ({len(evenements)})" if evenements is not None else "\n📅 Agenda")
    if remarque:
        lignes.append(f"   ({remarque})")
    if erreur:
        lignes.append(f"   ⚠️ {erreur}")
    elif not evenements:
        lignes.append("   Rien de prévu aujourd'hui.")
    for e in evenements or []:
        heure = "Toute la journée" if e["journee"] else f"{e['debut']:%H:%M}–{e['fin']:%H:%M}"
        lignes.append(f"   {heure}  {e['titre']}" + (f" · {e['lieu']}" if e["lieu"] else ""))

    mails, erreur = _bloc(mails_a_traiter)
    total = sum(len(x) for x in mails.values()) if mails else 0
    lignes.append(f"\n📬 Mails à traiter ({total}{'+' if mails and any(len(x) >= MAILS_MAX for x in mails.values()) else ''})"
                  if mails is not None else "\n📬 Mails à traiter")
    if erreur:
        lignes.append(f"   ⚠️ {erreur}")
    elif not total:
        lignes.append("   Aucun : ta boîte est à jour.")
    for etiquette, liste in (mails or {}).items():
        for m in liste:
            objet = m["objet"] if len(m["objet"]) <= 60 else m["objet"][:59] + "…"
            lignes.append(f"   {etiquette.split()[0]} {m['de']} · « {objet} » ({m['date']:%d/%m})")

    rappels, erreur = _bloc(rappels_du_jour)
    lignes.append(f"\n⏰ Rappels du jour ({len(rappels)})" if rappels is not None else "\n⏰ Rappels du jour")
    if erreur:
        lignes.append(f"   ⚠️ {erreur}")
    elif not rappels:
        lignes.append("   Aucun rappel pour aujourd'hui.")
    for r in rappels or []:
        quand = (f"⚠️ en retard ({r['quand']:%d/%m})" if r["en_retard"]
                 else "aujourd'hui" if r["quand"].hour == 0 and r["quand"].minute == 0 else f"{r['quand']:%H:%M}")
        lignes.append(f"   {quand}  {r['quoi']}" + (f" ({r['liste']})" if r["liste"] else ""))

    log.info("Brief composé en %.1f s (%d événement(s), %d mail(s), %d rappel(s))", time.time() - debut,
             len(evenements or []), total, len(rappels or []))
    return "\n".join(lignes)
