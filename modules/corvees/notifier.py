"""La notification du soir : au plus une par jour, jamais entre 23 h et 8 h, et aucune s'il n'y a rien de nouveau.

Après l'analyse, une notification est préparée seulement si une corvée n'a encore jamais été annoncée. Elle part
tout de suite si l'heure le permet ; sinon, le démon réessaie chaque quart d'heure, et elle part le matin venu. Elle
passe par les notifications de l'Assistant, qui ajoutent leurs propres garde-fous (pause générale, limites). En
mode test (réglage notifications.vers_journal), elle est écrite dans notifications.log au lieu d'apparaître.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from modules.corvees import config
from modules.corvees.normalize import debut_du_jour, local

REESSAI_S = 15 * 60
_VERROU = threading.Lock()
MEMOIRE_MAX = 500  # signatures déjà annoncées, gardées pour ne pas répéter


def en_silence(reglages: dict[str, Any], maintenant: float) -> bool:
    n = reglages["notifications"]
    debut, fin = n["silence_debut"], n["silence_fin"]
    heure = local(maintenant).strftime("%H:%M")
    if debut == fin:
        return False
    if debut < fin:
        return debut <= heure < fin
    return heure >= debut or heure < fin  # passe minuit : 23:00 → 08:00


def texte(candidats: list[dict[str, Any]], descriptions: dict[str, dict[str, Any]]) -> tuple[str, str]:
    """(titre, message) : « 🔁 3 corvées repérées », « Environ 45 min/mois à récupérer… »."""
    n = len(candidats)
    gain = 0.0
    for c in candidats:
        d = descriptions.get(c["signature"]) or {}
        gain += min(float(d.get("gain_minutes_mois", c["minutes_mois"])), float(c["minutes_mois"]))
    titre = f"🔁 {n} corvée{'s' if n > 1 else ''} repérée{'s' if n > 1 else ''}"
    return titre, f"Environ {round(gain)} min/mois à récupérer. Tape « corvees rapport »."


def preparer(
    base: Any, candidats: list[dict[str, Any]], descriptions: dict[str, dict[str, Any]], maintenant: float
) -> dict[str, Any] | None:
    """Prépare la notification du soir s'il y a du nouveau (sinon, rien, et l'ancienne en attente est oubliée)."""
    deja = set(base.lire("notifiees", []) or [])
    if not any(c["signature"] not in deja for c in candidats):
        base.effacer("notification_en_attente")
        return None
    titre, message = texte(candidats, descriptions)
    attente = {
        "titre": titre,
        "message": message,
        "signatures": [c["signature"] for c in candidats],
        "quand": maintenant,
    }
    base.ecrire("notification_en_attente", attente)
    return attente


def _vers_journal(reglages: dict[str, Any]) -> Callable[[str, str], bool]:
    def ecrire(titre: str, message: str) -> bool:
        chemin = config.dossier_donnees(reglages) / "notifications.log"
        chemin.parent.mkdir(parents=True, exist_ok=True)
        with open(chemin, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} · {titre} · {message}\n")
        chemin.chmod(0o600)
        return True

    return ecrire


def _par_l_assistant(titre: str, message: str) -> bool:
    from core.notifications import notifier

    affichee, _ = notifier(titre, message, module="corvees")
    return affichee


def tenter(
    base: Any,
    reglages: dict[str, Any],
    maintenant: float,
    afficher: Callable[[str, str], bool] | None = None,
    journal: Callable[[str], None] | None = None,
) -> bool:
    """Envoie la notification en attente si c'est permis. Renvoie True si elle est partie."""
    with _VERROU:  # le démon (au battement) et la suite du soir peuvent tenter au même moment
        return _tenter(base, reglages, maintenant, afficher, journal)


def _tenter(
    base: Any,
    reglages: dict[str, Any],
    maintenant: float,
    afficher: Callable[[str, str], bool] | None,
    journal: Callable[[str], None] | None,
) -> bool:
    attente = base.lire("notification_en_attente")
    if not attente or en_silence(reglages, maintenant):
        return False
    if float(base.lire("derniere_notification", 0) or 0) >= debut_du_jour(maintenant):
        return False  # déjà une aujourd'hui
    if maintenant - float(base.lire("notification_essai", 0) or 0) < REESSAI_S:
        return False
    base.ecrire("notification_essai", maintenant)
    if afficher is None:
        afficher = _vers_journal(reglages) if reglages["notifications"]["vers_journal"] else _par_l_assistant
    try:
        partie = bool(afficher(attente["titre"], attente["message"]))
    except Exception as e:  # une notification ratée ne fait rien tomber : nouvel essai plus tard
        if journal:
            journal(f"Notification impossible : {e.__class__.__name__} : {e}")
        return False
    if partie:
        base.ecrire("derniere_notification", maintenant)
        deja = list(base.lire("notifiees", []) or [])
        deja += [s for s in attente["signatures"] if s not in deja]
        base.ecrire("notifiees", deja[-MEMOIRE_MAX:])
        base.effacer("notification_en_attente")
        if journal:
            journal(f"Notification : {attente['titre']} · {attente['message']}")
    return partie
