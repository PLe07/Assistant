"""Les notifications du Trieur (§9) : une par document, ou un seul résumé quand plus de 3 arrivent ensemble.

Les événements attendent quelques secondes (un envoi de 10 photos arrive en rafale) ; au-delà de 3, un résumé
« 10 documents : 8 rangés, 2 à vérifier ». Les heures silencieuses et la limite par heure sont celles de
l'Assistant (core.notifications) ; en mode test, rien ne s'affiche : tout va dans le journal.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.journal import journal
from modules.trieur.base import Element

log = journal("trieur")
ATTENTE_S = 5.0


@dataclass
class Evenement:
    quand: float
    genre: str  # classe, a_verifier, photos, doublon, erreur
    titre: str
    message: str


def _envoyer_vraiment(titre: str, message: str, reponse: bool = True) -> None:
    """Un document que tu viens d'envoyer mérite sa réponse : elle passe la limite par heure de l'Assistant (c'est
    toi qui l'as demandée), mais jamais les heures silencieuses. Les rappels du matin suivent la règle commune."""
    from core import config
    from core.notifications import en_heures_silencieuses, notifier

    urgent = reponse and not en_heures_silencieuses(config.charger())
    notifier(titre, message, module="trieur", urgent=urgent)


class Notifieur:
    def __init__(self, reglages: dict[str, Any], envoyer: Callable[[str, str], Any] | None = None,
                 horloge: Callable[[], float] = time.time):  # fmt: skip
        self.reglages, self.horloge = reglages, horloge
        self._envoyer = envoyer or _envoyer_vraiment
        self.attente: list[Evenement] = []

    def envoyer(self, titre: str, message: str) -> None:
        if self.reglages.get("mode_test"):
            log.info("(mode test) notification : %s · %s", titre, message)
            return
        self._envoyer(titre, message)

    def _dossier(self, destination: Path) -> str:
        """« Factures/2026 » plutôt que « 2026 » : le chemin depuis Classés (ou depuis ton dossier personnel)."""
        from modules.trieur import config

        for racine in (config.chemin(self.reglages, "classes"), Path.home()):
            try:
                return str(destination.parent.relative_to(racine)) or racine.name
            except ValueError:
                continue
        return destination.parent.name

    def element(self, el: Element, garantie: str | None = None) -> None:
        nom = Path(el.destination).name if el.destination else el.nom
        dossier = self._dossier(Path(el.destination)) if el.destination else ""
        if el.etat == "classe":
            message = f"{nom} → {dossier}" + (f" · garantie jusqu'au {garantie}" if garantie else "")
            e = Evenement(self.horloge(), "classe", "🗂 Rangé", message)
        elif el.etat == "a_verifier":
            e = Evenement(self.horloge(), "a_verifier", "🗂 À vérifier", f"{el.nom} : je n'ai pas su le classer seul")
        elif el.etat == "photos":
            e = Evenement(self.horloge(), "photos", "📷 Photo rangée", f"{el.nom} → {dossier}")
        elif el.etat == "doublon":
            e = Evenement(self.horloge(), "doublon", "🗂 Déjà rangé", f"{el.nom} : le même fichier est déjà classé")
        elif el.etat == "erreur":
            e = Evenement(self.horloge(), "erreur", "⚠️ Trieur", f"{el.nom} : {el.erreur or 'erreur'}")
        else:
            return
        self.attente.append(e)

    def vider(self, forcer: bool = False) -> int:
        """Envoie ce qui attend depuis assez longtemps ; renvoie le nombre de notifications affichées."""
        if not self.attente or (not forcer and self.horloge() - self.attente[0].quand < ATTENTE_S):
            return 0
        lot, self.attente = self.attente, []
        if len(lot) > int(self.reglages["notifications"]["grouper_au_dela"]):
            n = Counter(e.genre for e in lot)
            mots = (("classe", "rangé(s)"), ("a_verifier", "à vérifier"), ("photos", "photo(s)"),
                    ("doublon", "déjà rangé(s)"), ("erreur", "en erreur"))  # fmt: skip
            morceaux = [f"{n[g]} {mot}" for g, mot in mots if n[g]]
            self.envoyer(f"🗂 {len(lot)} documents traités", ", ".join(morceaux))
            return 1
        for e in lot:
            self.envoyer(e.titre, e.message)
        return len(lot)

    def echeance(self, produit: str, jours: int, fin: str) -> None:
        if self.reglages.get("mode_test"):
            log.info("(mode test) garantie : %s, fin dans %s jours", produit, jours)
        elif self._envoyer is _envoyer_vraiment:
            _envoyer_vraiment("🛡 Garantie", f"{produit} : fin dans {jours} jours ({fin})", reponse=False)
        else:
            self._envoyer("🛡 Garantie", f"{produit} : fin dans {jours} jours ({fin})")
