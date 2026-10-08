"""Des requêtes HTTP à la page locale, en maîtrisant chaque en-tête (Host, Origin, jeton)."""

from __future__ import annotations

import http.client
import json
from dataclasses import dataclass
from typing import Any

from tests.fabrique_web import JETON


@dataclass
class Reponse:
    code: int
    entetes: dict[str, str]
    corps: bytes

    @property
    def texte(self) -> str:
        return self.corps.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.corps)


def requete(
    port: int,
    chemin: str,
    methode: str = "GET",
    entetes: dict[str, str] | None = None,
    corps: Any = None,
    jeton: str | None = JETON,
    hote: str | None = None,
) -> Reponse:
    """`jeton` est ajouté à l'adresse (None : sans jeton). Un POST porte aussi `X-Jeton` et un corps JSON."""
    if jeton is not None:
        chemin += ("&" if "?" in chemin else "?") + f"t={jeton}"
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    toutes = {"Host": hote if hote is not None else f"127.0.0.1:{port}"}
    donnees = None
    if methode == "POST":
        toutes["Content-Type"] = "application/json"
        if jeton is not None:
            toutes["X-Jeton"] = jeton
        donnees = json.dumps(corps if corps is not None else {}).encode()
    toutes.update(entetes or {})
    c.putrequest(methode, chemin, skip_host=True, skip_accept_encoding=True)
    for nom, valeur in toutes.items():
        if valeur is not None:
            c.putheader(nom, valeur)
    if donnees is not None:
        c.putheader("Content-Length", str(len(donnees)))
    c.endheaders(donnees)
    r = c.getresponse()
    reponse = Reponse(r.status, {k: v for k, v in r.getheaders()}, r.read())
    c.close()
    return reponse
