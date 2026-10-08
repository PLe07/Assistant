"""La mise à jour en direct (Server-Sent Events) : le démon publie une nouvelle version de l'état, chaque page
ouverte est prévenue et recharge son contenu.

Un seul message, « maj », avec le numéro de version : la page va chercher elle-même son fragment (une seule façon
de dessiner, côté serveur). Un battement toutes les 15 s garde la connexion ouverte ; au plus `CLIENTS_MAX` pages
écoutent en même temps (au-delà : 503, le navigateur réessaie plus tard).
"""

from __future__ import annotations

import threading

CLIENTS_MAX = 8
BATTEMENT_S = 15.0


class Diffuseur:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._version = 0
        self._clients = 0
        self._ferme = False

    @property
    def version(self) -> int:
        with self._condition:
            return self._version

    def publier(self) -> int:
        with self._condition:
            self._version += 1
            self._condition.notify_all()
            return self._version

    def attendre(self, vue: int, delai: float = BATTEMENT_S) -> int:
        """Rend la version dès qu'elle dépasse `vue`, ou au bout de `delai` (battement)."""
        with self._condition:
            self._condition.wait_for(lambda: self._version > vue or self._ferme, timeout=delai)
            return self._version

    def entrer(self) -> bool:
        with self._condition:
            if self._ferme or self._clients >= CLIENTS_MAX:
                return False
            self._clients += 1
            return True

    def sortir(self) -> None:
        with self._condition:
            self._clients = max(0, self._clients - 1)

    @property
    def clients(self) -> int:
        with self._condition:
            return self._clients

    @property
    def ferme(self) -> bool:
        with self._condition:
            return self._ferme

    def fermer(self) -> None:
        with self._condition:
            self._ferme = True
            self._condition.notify_all()


def message(evenement: str, donnees: str) -> bytes:
    """Un message SSE (une donnée sur une seule ligne)."""
    propre = donnees.replace("\r", " ").replace("\n", " ")
    return f"event: {evenement}\ndata: {propre}\n\n".encode()


BATTEMENT = b": battement\n\n"
