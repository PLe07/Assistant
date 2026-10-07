"""Docker et n8n, en lecture seule : `docker ps`, `docker inspect`, `docker stats --no-stream`, et un GET sur
`http://127.0.0.1:5678/healthz`. Jamais d'appel en écriture à l'API de n8n, jamais `docker restart` (§1.2).

Docker éteint, n8n absent ou injoignable : un état clair, jamais une exception.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from tableau import systeme

Executer = Callable[[list[str]], systeme.Resultat]
HOTE_N8N = "127.0.0.1"


@dataclass
class EtatConteneur:
    nom: str
    image: str = ""
    etat: str = "inconnu"  # running, exited, restarting, paused…
    sante: str | None = None  # healthy, unhealthy, starting
    relances: int | None = None
    demarre_le: str | None = None
    cpu_pct: float | None = None
    memoire_mo: float | None = None


@dataclass
class EtatDocker:
    disponible: bool
    erreur: str | None = None
    conteneurs: dict[str, EtatConteneur] = field(default_factory=dict)


def _json_lignes(sortie: str) -> list[dict[str, Any]]:
    resultat = []
    for ligne in sortie.splitlines():
        ligne = ligne.strip()
        if not ligne:
            continue
        try:
            valeur = json.loads(ligne)
        except ValueError:
            continue
        if isinstance(valeur, dict):
            resultat.append(valeur)
    return resultat


_TAILLE = re.compile(r"^\s*([\d.]+)\s*([KMGT]?i?B)\s*$", re.IGNORECASE)
_FACTEURS = {"b": 1 / 1048576, "kb": 1 / 1024, "kib": 1 / 1024, "mb": 1, "mib": 1, "gb": 1024, "gib": 1024,
             "tb": 1048576, "tib": 1048576}  # fmt: skip


def _mo(texte: str) -> float | None:
    m = _TAILLE.match(texte or "")
    if not m:
        return None
    return float(m.group(1)) * _FACTEURS.get(m.group(2).lower(), 1)


class SondeDocker:
    def __init__(self, executer: Executer | None = None, horloge: Callable[[], float] = time.time,
                 stats_toutes_les_s: float = 600) -> None:  # fmt: skip
        self.executer: Executer = executer or (lambda args: systeme.executer(args, delai=20))
        self.horloge = horloge
        self.stats_toutes_les_s = stats_toutes_les_s
        self._stats: dict[str, tuple[float, float | None, float | None]] = {}

    def etat(self, noms: list[str]) -> EtatDocker:
        r = self.executer(["docker", "ps", "-a", "--format", "{{json .}}"])
        if not r.ok:
            message = (r.erreur or r.sortie or "").strip().splitlines()
            return EtatDocker(False, message[0][:200] if message else f"code {r.code}")
        etat = EtatDocker(True)
        presents = {str(c.get("Names", "")): c for c in _json_lignes(r.sortie)}
        for nom in noms:
            brut = presents.get(nom)
            if brut is None:
                continue
            c = EtatConteneur(nom=nom, image=str(brut.get("Image", "")), etat=str(brut.get("State", "inconnu")))
            self._inspecter(c)
            self._mesurer(c)
            etat.conteneurs[nom] = c
        return etat

    def _inspecter(self, c: EtatConteneur) -> None:
        r = self.executer(["docker", "inspect", c.nom])
        if not r.ok:
            return
        try:
            donnees = json.loads(r.sortie)
            info = donnees[0] if isinstance(donnees, list) and donnees else {}
        except ValueError:
            return
        state = info.get("State") if isinstance(info, dict) else None
        if isinstance(state, dict):
            c.etat = str(state.get("Status") or c.etat)
            sante = state.get("Health")
            if isinstance(sante, dict):
                c.sante = str(sante.get("Status")) if sante.get("Status") else None
            c.demarre_le = str(state.get("StartedAt")) if state.get("StartedAt") else None
        relances = info.get("RestartCount") if isinstance(info, dict) else None
        c.relances = int(relances) if isinstance(relances, int) else None

    def _mesurer(self, c: EtatConteneur) -> None:
        """`docker stats --no-stream` prend une seconde ou deux : au plus toutes les 10 minutes."""
        memo = self._stats.get(c.nom)
        if c.etat != "running":
            self._stats.pop(c.nom, None)
            return
        if memo is not None and self.horloge() - memo[0] < self.stats_toutes_les_s:
            c.cpu_pct, c.memoire_mo = memo[1], memo[2]
            return
        r = self.executer(["docker", "stats", "--no-stream", "--format", "{{json .}}", c.nom])
        cpu = memoire = None
        for ligne in _json_lignes(r.sortie) if r.ok else []:
            try:
                cpu = float(str(ligne.get("CPUPerc", "")).rstrip("%"))
            except ValueError:
                cpu = None
            memoire = _mo(str(ligne.get("MemUsage", "")).split("/")[0])
        self._stats[c.nom] = (self.horloge(), cpu, memoire)
        c.cpu_pct, c.memoire_mo = cpu, memoire


def healthz(port: int = 5678, delai: float = 3.0) -> tuple[bool, str]:
    """GET http://127.0.0.1:<port>/healthz : (répond, détail). Seulement en local, seulement en lecture."""
    url = f"http://{HOTE_N8N}:{int(port)}/healthz"
    requete = urllib.request.Request(url, method="GET", headers={"User-Agent": "tableau-de-bord"})
    ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # jamais de mandataire : c'est local
    try:
        with ouvreur.open(requete, timeout=delai) as reponse:
            corps = reponse.read(2048).decode("utf-8", errors="replace")
            return (200 <= reponse.status < 300), f"HTTP {reponse.status} {corps.strip()[:80]}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raison = getattr(e, "reason", e)
        return False, f"injoignable ({raison.__class__.__name__ if not isinstance(raison, str) else raison})"
