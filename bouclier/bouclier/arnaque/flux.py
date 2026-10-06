"""Les flux publics de liens piégés, téléchargés en entier une fois par jour puis consultés **sur le Mac**.

- OpenPhish (flux communautaire gratuit) : https://openphish.com/feed.txt
- URLhaus (abuse.ch) : https://urlhaus.abuse.ch/downloads/text_online/

Aucun lien n'est envoyé à ces services : c'est toi qui télécharges leur liste, la recherche se fait en local.
Si un flux est indisponible, la copie de la veille reste utilisée (et `doctor` affiche sa date).
"""

from __future__ import annotations

import os
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bouclier import reseau
from bouclier.arnaque import liens

SOURCES = {
    "OpenPhish": "https://openphish.com/feed.txt",
    "URLhaus": "https://urlhaus.abuse.ch/downloads/text_online/",
}
# Sur ces hôtes, chaque page appartient à quelqu'un de différent : seule l'adresse exacte compte.
_HOTES_PARTAGES = liens.RACCOURCISSEURS | liens.HEBERGEURS_PAR_CHEMIN | liens.MESSAGERIES | {
    "google.com", "www.google.com", "drive.google.com", "dropbox.com", "www.dropbox.com", "onedrive.live.com",
    "1drv.ms", "github.com", "raw.githubusercontent.com", "discord.com", "cdn.discordapp.com", "mega.nz",
    "wetransfer.com", "we.tl", "outlook.office365.com", "forms.office.com", "www.canva.com", "canva.com",
}  # fmt: skip

Telecharger = Callable[..., reseau.Reponse]


def normaliser(url: str) -> str:
    try:
        m = urllib.parse.urlsplit(url.strip() if "://" in url else "https://" + url.strip())
    except ValueError:
        return url.strip().lower()
    chemin = m.path.rstrip("/")
    requete = f"?{m.query}" if m.query else ""
    return f"{(m.hostname or '').lower()}{chemin}{requete}"


@dataclass
class EtatFlux:
    nom: str
    date: float | None  # dernière copie réussie
    entrees: int
    erreur: str = ""


class Flux:
    def __init__(self, dossier: Path, telecharger: Telecharger = reseau.telecharger) -> None:
        self.dossier = dossier
        self.telecharger = telecharger
        self._urls: dict[str, str] = {}
        self._hotes: dict[str, str] = {}
        self._charge_le: float = 0.0

    def _fichier(self, nom: str) -> Path:
        return self.dossier / f"flux-{nom.lower()}.txt"

    def mettre_a_jour(self) -> list[EtatFlux]:
        self.dossier.mkdir(parents=True, exist_ok=True)
        etats = []
        for nom, url in SOURCES.items():
            erreur = ""
            try:
                r = self.telecharger(url, delai=60, max_octets=80_000_000)
                if r.statut == 200 and r.corps.strip():
                    temporaire = self._fichier(nom).with_suffix(".tmp")
                    temporaire.write_bytes(r.corps)
                    os.replace(temporaire, self._fichier(nom))
                else:
                    erreur = f"HTTP {r.statut}"
            except (reseau.ErreurReseau, reseau.HoteInterdit) as e:
                erreur = str(e)
            etats.append(self._etat(nom, erreur))
        self._charge_le = 0.0
        return etats

    def _etat(self, nom: str, erreur: str = "") -> EtatFlux:
        f = self._fichier(nom)
        if not f.exists():
            return EtatFlux(nom, None, 0, erreur or "jamais téléchargé")
        lignes = sum(1 for ligne in f.read_text("utf-8", "replace").splitlines() if ligne.strip())
        return EtatFlux(nom, f.stat().st_mtime, lignes, erreur)

    def etats(self) -> list[EtatFlux]:
        return [self._etat(nom) for nom in SOURCES]

    def _charger(self) -> None:
        dates = [self._fichier(n).stat().st_mtime for n in SOURCES if self._fichier(n).exists()]
        derniere = max(dates, default=0.0)
        if self._charge_le and derniere <= self._charge_le:
            return
        self._urls, self._hotes = {}, {}
        for nom in SOURCES:
            f = self._fichier(nom)
            if not f.exists():
                continue
            for ligne in f.read_text("utf-8", "replace").splitlines():
                ligne = ligne.strip()
                if not ligne or ligne.startswith("#"):
                    continue
                n = normaliser(ligne)
                self._urls.setdefault(n, nom)
                hote = n.split("/", 1)[0].split("?", 1)[0]
                if hote and hote not in _HOTES_PARTAGES and liens.domaine_enregistrable(hote) not in _HOTES_PARTAGES:
                    self._hotes.setdefault(hote, nom)
        self._charge_le = derniere or time.time()

    def __call__(self, url: str) -> str | None:
        """Le nom du flux qui signale ce lien (adresse exacte, ou site entier s'il n'est pas partagé)."""
        self._charger()
        n = normaliser(url)
        if n in self._urls:
            return self._urls[n]
        return self._hotes.get(n.split("/", 1)[0].split("?", 1)[0])
