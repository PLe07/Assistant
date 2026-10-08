"""Les notifications du Mac (Centre de notifications), et leur double pour les tests.

Une notification passe par `osascript -e 'display notification …'`, seule forme permise par la liste blanche
(`systeme.py`). Hors d'un Mac, rien n'est affiché : la notification est seulement notée dans notre base (page,
`tableau doctor`). Le texte est échappé pour AppleScript : ni guillemet ni barre oblique inverse ne peuvent sortir de
la chaîne.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol

from tableau import systeme

LONGUEUR_MAX = 400


class Notificateur(Protocol):
    def envoyer(self, titre: str, texte: str) -> tuple[bool, str]:
        """(envoyée, motif d'échec)."""
        ...


def echapper_applescript(texte: str) -> str:
    propre = "".join(c if c >= " " or c == "\n" else " " for c in texte)[:LONGUEUR_MAX]
    return propre.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class NotificateurMac:
    def envoyer(self, titre: str, texte: str) -> tuple[bool, str]:
        if not systeme.est_un_mac():
            return False, "pas un Mac : notification seulement notée"
        script = f'display notification "{echapper_applescript(texte)}" with title "{echapper_applescript(titre)}"'
        r = systeme.executer(["osascript", "-e", script], delai=10)
        if r.ok:
            return True, ""
        return False, (r.erreur.strip().splitlines() or [f"code {r.code}"])[-1][:200]


@dataclass
class NotificateurMemoire:
    """Le notificateur des tests (et du faux écosystème) : il garde ce qu'on lui envoie."""

    envoyees: list[tuple[str, str]] = field(default_factory=list)
    en_panne: bool = False

    def envoyer(self, titre: str, texte: str) -> tuple[bool, str]:
        if self.en_panne:
            return False, "notificateur en panne (test)"
        self.envoyees.append((titre, texte))
        return True, ""


class NotificateurCoupe:
    """Notifications coupées (faux écosystème, mesures) : chacune est notée dans notre base, aucune n'est affichée."""

    def envoyer(self, titre: str, texte: str) -> tuple[bool, str]:
        return False, "notifications coupées (test)"


def choisir() -> Notificateur:
    """`TABLEAU_NOTIFICATIONS=coupees` : rien ne s'affiche (tests sur ton Mac) ; sinon le Centre de notifications."""
    return NotificateurCoupe() if os.environ.get("TABLEAU_NOTIFICATIONS") == "coupees" else NotificateurMac()
