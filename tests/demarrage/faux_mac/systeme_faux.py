"""Le faux Mac : une arborescence dans un dossier temporaire, des réponses de commandes préparées, une horloge
simulée, et le registre de chaque commande lancée (pour les tests de sécurité).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TypeAlias

from modules.demarrage.systeme import Resultat, verifier_commande

Reponse: TypeAlias = "Resultat | Callable[[list[str], FauxMac], Resultat]"

# Les commandes d'un Mac ordinaire ; un test peut en retirer pour simuler un mode dégradé.
COMMANDES_MAC = {
    "launchctl", "ps", "top", "pmset", "codesign", "mdls", "sfltool", "osascript", "systemextensionsctl",
    "crontab", "sysctl", "last", "log", "zsh", "uname", "sw_vers", "open", "caffeinate", "id",
}  # fmt: skip


class FauxMac:
    def __init__(self, racine: Path, uid: int = 501, utilisateur: str = "utilisateur", debut: float = 1_791_176_000.0):
        self.racine = racine
        self.maison = f"/Users/{utilisateur}"
        self.uid = uid
        self.utilisateur = utilisateur
        self.horloge = debut
        self.commandes = set(COMMANDES_MAC)
        self.exactes: dict[tuple[str, ...], Reponse] = {}
        self.prefixes: list[tuple[tuple[str, ...], Reponse]] = []
        self.appels: list[list[str]] = []
        self.environnements: list[dict[str, str] | None] = []
        self.chemin(self.maison).mkdir(parents=True, exist_ok=True)

    # --- préparer ---------------------------------------------------------------------------------------------

    def repondre(self, commande: list[str], reponse: Reponse | str, code: int = 0, erreur: str = "") -> None:
        """Réponse à une commande exacte (une chaîne : sa sortie)."""
        self.exactes[tuple(commande)] = Resultat(code, reponse, erreur) if isinstance(reponse, str) else reponse

    def repondre_debut(self, debut: list[str], reponse: Reponse | str, code: int = 0, erreur: str = "") -> None:
        """Réponse à toute commande qui commence ainsi (la plus longue l'emporte)."""
        r = Resultat(code, reponse, erreur) if isinstance(reponse, str) else reponse
        self.prefixes.append((tuple(debut), r))
        self.prefixes.sort(key=lambda p: len(p[0]), reverse=True)

    def fichier(self, absolu: str, contenu: bytes | str = b"") -> Path:
        p = self.chemin(absolu)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(contenu.encode() if isinstance(contenu, str) else contenu)
        return p

    # --- l'interface Systeme ----------------------------------------------------------------------------------

    def chemin(self, absolu: str | Path) -> Path:
        p = Path(absolu)
        return self.racine / p.relative_to("/") if p.is_absolute() else p

    def executer(self, commande: list[str], delai: float = 10.0, env: dict[str, str] | None = None) -> Resultat:
        verifier_commande(commande)
        self.appels.append(list(commande))
        self.environnements.append(env)
        if Path(commande[0]).name not in self.commandes:
            return Resultat(127, "", f"{commande[0]} : commande introuvable")
        reponse = self.exactes.get(tuple(commande))
        if reponse is None:
            for debut, r in self.prefixes:
                if tuple(commande[: len(debut)]) == debut:
                    reponse = r
                    break
        if reponse is None:
            return Resultat(1, "", f"faux Mac : pas de réponse prévue pour {commande}")
        return reponse(commande, self) if callable(reponse) else reponse

    def maintenant(self) -> float:
        return self.horloge

    def attendre(self, secondes: float) -> None:
        self.horloge += max(0.0, secondes)

    def a_la_commande(self, nom: str) -> bool:
        return nom in self.commandes

    # --- vérifier ---------------------------------------------------------------------------------------------

    def lancees(self, nom: str) -> list[list[str]]:
        return [c for c in self.appels if Path(c[0]).name == nom]
