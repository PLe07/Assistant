"""Minuteurs et rappels : « minuteur 10 minutes », « rappelle-moi dans 20 minutes de sortir le linge ».

Gardés dans `minuteurs.json` (survivent à un redémarrage du moteur) ; à l'échéance, une notification locale (par
l'app, sinon `osascript` avec le message en **argument**), et un son. Rien ne part sur le réseau.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from voix.actions.base import Outils, Reponse, erreur, fait, info
from voix.nlu.durees import dire_duree

MAX_MINUTEURS = 20
NOTIFIER = ("-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
            "-e", "end run")  # fmt: skip


@dataclass(frozen=True)
class Minuteur:
    ident: int
    fin: datetime
    message: str | None
    duree_s: int


class Minuteurs:
    def __init__(self, fichier: Path) -> None:
        self.fichier = fichier
        self.liste: list[Minuteur] = []
        self._lire()

    def _lire(self) -> None:
        try:
            brut = json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for m in brut if isinstance(brut, list) else []:
            if not isinstance(m, dict):
                continue
            try:
                message = m.get("message")
                self.liste.append(Minuteur(int(m["ident"]), datetime.fromisoformat(m["fin"]),
                                           str(message)[:300] if message else None, int(m["duree_s"])))  # fmt: skip
            except (KeyError, TypeError, ValueError):
                continue

    def _ecrire(self) -> None:
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        donnees = [{"ident": m.ident, "fin": m.fin.isoformat(), "message": m.message, "duree_s": m.duree_s}
                   for m in self.liste]  # fmt: skip
        fd, tmp = tempfile.mkstemp(dir=self.fichier.parent, prefix=".minuteurs.")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.fichier)

    def ajouter(self, duree_s: int, message: str | None, maintenant: datetime) -> Minuteur | None:
        if len(self.liste) >= MAX_MINUTEURS:
            return None
        m = Minuteur(max((x.ident for x in self.liste), default=0) + 1, maintenant + timedelta(seconds=duree_s),
                     message, duree_s)  # fmt: skip
        self.liste.append(m)
        self._ecrire()
        return m

    def annuler_dernier(self) -> Minuteur | None:
        if not self.liste:
            return None
        m = max(self.liste, key=lambda x: x.ident)
        self.liste.remove(m)
        self._ecrire()
        return m

    def prochain(self) -> Minuteur | None:
        return min(self.liste, key=lambda x: x.fin, default=None)

    def echus(self, maintenant: datetime) -> list[Minuteur]:
        partis = [m for m in self.liste if m.fin <= maintenant]
        if partis:
            self.liste = [m for m in self.liste if m.fin > maintenant]
            self._ecrire()
        return sorted(partis, key=lambda x: x.fin)


def lancer(o: Outils, minuteurs: Minuteurs, duree_s: int) -> Reponse:
    m = minuteurs.ajouter(duree_s, None, o.maintenant())
    if m is None:
        return erreur("Il y a déjà trop de minuteurs.", "minuteur.lancer")
    return fait(f"Minuteur de {dire_duree(duree_s)}", "minuteur.lancer", duree_s=duree_s)


def rappel(o: Outils, minuteurs: Minuteurs, duree_s: int, message: str, heure: str | None = None) -> Reponse:
    m = minuteurs.ajouter(duree_s, message, o.maintenant())
    if m is None:
        return erreur("Il y a déjà trop de rappels.", "rappel.creer")
    quand = f"à {heure.replace(':', ' h ')}" if heure else f"dans {dire_duree(duree_s)}"
    return fait(f"Je te rappelle « {message} » {quand}", "rappel.creer", duree_s=duree_s)


def annuler(minuteurs: Minuteurs) -> Reponse:
    m = minuteurs.annuler_dernier()
    if m is None:
        return info("Il n'y a pas de minuteur en cours.", "minuteur.annuler")
    return fait("Rappel annulé" if m.message else "Minuteur annulé", "minuteur.annuler")


def restant(o: Outils, minuteurs: Minuteurs) -> Reponse:
    m = minuteurs.prochain()
    if m is None:
        return info("Il n'y a pas de minuteur en cours.", "minuteur.restant")
    reste = max(1, int((m.fin - o.maintenant()).total_seconds()))
    quoi = f"avant « {m.message} »" if m.message else "sur le minuteur"
    return info(f"Il reste {dire_duree(reste)} {quoi}.", "minuteur.restant", restant_s=reste)


def notifier(o: Outils, m: Minuteur) -> bool:
    """À l'échéance : la notification par l'app, sinon par osascript (le texte en argument, jamais dans le script)."""
    titre = "Rappel" if m.message else "Minuteur"
    texte = m.message or f"{dire_duree(m.duree_s)} écoulées"
    if o.demander("notification", titre=titre, message=texte).ok:
        return True
    return o.lancer("osascript", *NOTIFIER, titre, texte).ok
