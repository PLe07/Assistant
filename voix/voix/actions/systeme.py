"""Le système : verrouiller, mettre en veille (avec confirmation), éteindre l'écran, l'apparence, le Wi-Fi, la batterie,
l'heure, la date, la météo.

- Veille et écran : `pmset sleepnow` / `pmset displaysleepnow` (sans sudo).
- Apparence : lue avec `defaults read -g AppleInterfaceStyle` (lecture seule), changée par l'app (Apple Events vers
  « Événements système », autorisation demandée au nom de l'app) ; annulable.
- Wi-Fi : `networksetup -setairportpower <interface> on|off` ; l'interface est lue dans
  `networksetup -listallhardwareports` ; annulable.
- Batterie : `pmset -g batt`. Heure et date : l'horloge. Météo : l'app Météo (Voix n'utilise pas le réseau).
"""

from __future__ import annotations

import re
from datetime import datetime

from voix.actions.base import Annulation, Etat, Outils, Reponse, erreur, fait, info

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
        "décembre"]  # fmt: skip
INTERFACE = re.compile(r"^(?:en|wl)\d{1,2}$")


def verrouiller(o: Outils) -> Reponse:
    r = o.demander("ecran.verrouiller")
    if not r.ok:
        return erreur(f"Je n'ai pas pu verrouiller : {r.erreur or 'refusé'}.", "systeme.verrouiller")
    return fait("Écran verrouillé", "systeme.verrouiller")


def veille(o: Outils) -> Reponse:
    r = o.lancer("pmset", "sleepnow")
    return fait("Mise en veille", "systeme.veille") if r.ok else erreur("La mise en veille a échoué.", "systeme.veille")


def ecran(o: Outils) -> Reponse:
    r = o.lancer("pmset", "displaysleepnow")
    if not r.ok:
        return erreur("L'écran ne s'est pas éteint.", "systeme.ecran_eteindre")
    return fait("Écran éteint", "systeme.ecran_eteindre")


# --- apparence ------------------------------------------------------------------------------------------------------


def sombre_actuel(o: Outils) -> bool | None:
    r = o.lancer("defaults", "read", "-g", "AppleInterfaceStyle")
    if r.ok:
        return r.sortie.strip().lower() == "dark"
    # La clé absente veut dire « clair » ; une autre erreur, on ne sait pas.
    return False if "does not exist" in r.erreur else None


def regler_apparence(o: Outils, sombre: bool) -> bool:
    return o.demander("apparence.regler", sombre=sombre).ok


def apparence(o: Outils, etat: Etat, sombre: bool) -> Reponse:
    intention = "systeme.mode_sombre" if sombre else "systeme.mode_clair"
    avant = sombre_actuel(o)
    r = o.demander("apparence.regler", sombre=sombre)
    if not r.ok:
        return erreur(f"Je n'ai pas pu changer l'apparence : {r.erreur or 'refusé'}.", intention)
    if avant is not None and avant != sombre:
        etat.retenir(Annulation("apparence", {"sombre": avant}, "mode sombre" if sombre else "mode clair"))
    return fait("Mode sombre" if sombre else "Mode clair", intention)


# --- Wi-Fi ----------------------------------------------------------------------------------------------------------


def interface_wifi(o: Outils) -> str | None:
    r = o.lancer("networksetup", "-listallhardwareports")
    if not r.ok:
        return None
    lignes = r.sortie.splitlines()
    for i, ligne in enumerate(lignes):
        if ligne.strip() in ("Hardware Port: Wi-Fi", "Hardware Port: AirPort"):
            for suite in lignes[i + 1 : i + 3]:
                m = re.match(r"^\s*Device:\s*(\S+)\s*$", suite)
                if m and INTERFACE.match(m.group(1)):
                    return m.group(1)
    return None


def wifi_actuel(o: Outils, interface: str) -> bool | None:
    r = o.lancer("networksetup", "-getairportpower", interface)
    if not r.ok:
        return None
    s = r.sortie.strip()
    return True if s.endswith(": On") else False if s.endswith(": Off") else None


def regler_wifi(o: Outils, interface: str, actif: bool) -> bool:
    return o.lancer("networksetup", "-setairportpower", interface, "on" if actif else "off").ok


def wifi(o: Outils, etat: Etat, actif: bool) -> Reponse:
    intention = "systeme.wifi_activer" if actif else "systeme.wifi_desactiver"
    interface = interface_wifi(o)
    if interface is None:
        return erreur("Je ne trouve pas le Wi-Fi de ce Mac.", intention)
    avant = wifi_actuel(o, interface)
    if not regler_wifi(o, interface, actif):
        return erreur("Le Wi-Fi n'a pas changé.", intention)
    if avant is not None and avant != actif:
        etat.retenir(Annulation("wifi", {"actif": avant, "interface": interface}, "Wi-Fi"))
    return fait("Wi-Fi activé" if actif else "Wi-Fi coupé", intention)


# --- informations ---------------------------------------------------------------------------------------------------


def batterie(o: Outils) -> Reponse:
    r = o.lancer("pmset", "-g", "batt")
    if not r.ok:
        return erreur("Je n'arrive pas à lire la batterie.", "systeme.batterie")
    m = re.search(r"(\d{1,3})%;\s*([^;]+);\s*([^\s;]+)?", r.sortie)
    if not m:
        return info("Ce Mac n'a pas de batterie.", "systeme.batterie")
    pourcent, etat_brut, reste = int(m.group(1)), m.group(2).strip(), (m.group(3) or "")
    etats = {"charging": "en charge", "charged": "chargée", "discharging": "sur batterie", "finishing charge":
             "presque chargée", "AC attached": "branchée"}  # fmt: skip
    texte = f"Batterie à {pourcent} %, {etats.get(etat_brut, etat_brut)}"
    if re.fullmatch(r"\d{1,2}:\d{2}", reste) and etat_brut == "discharging":
        h, mi = reste.split(":")
        texte += f", environ {int(h)} h {mi} restantes"
    return info(texte + ".", "systeme.batterie", pourcent=pourcent)


def heure(maintenant: datetime) -> Reponse:
    return info(f"Il est {maintenant.hour} h {maintenant.minute:02d}.", "systeme.heure")


def date(maintenant: datetime) -> Reponse:
    jour = "1er" if maintenant.day == 1 else str(maintenant.day)
    return info(f"Nous sommes le {JOURS[maintenant.weekday()]} {jour} {MOIS[maintenant.month - 1]} {maintenant.year}.",
                "systeme.date")  # fmt: skip


def meteo(o: Outils) -> Reponse:
    r = o.lancer("open", "-b", "com.apple.weather")
    if not r.ok:
        return erreur("L'app Météo n'a pas pu s'ouvrir.", "systeme.meteo")
    return fait("Météo ouverte", "systeme.meteo")
