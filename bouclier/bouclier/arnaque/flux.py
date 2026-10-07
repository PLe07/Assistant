"""Les flux publics de liens piégés, téléchargés en entier une fois par jour puis consultés **sur le Mac**.

- OpenPhish (flux communautaire gratuit) : https://openphish.com/feed.txt, ou son miroir officiel sur GitHub ;
- URLhaus (abuse.ch) : https://urlhaus.abuse.ch/downloads/text_online/

Aucun lien n'est envoyé à ces services : c'est toi qui télécharges leur liste, la recherche se fait en local.
Si un flux est indisponible, la copie de la veille reste utilisée (et `doctor` affiche sa date).
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bouclier import reseau
from bouclier.arnaque import liens

SOURCES = {
    # Le miroir officiel sur GitHub (mis à jour toutes les 12 h) si openphish.com refuse ou ne répond pas.
    "OpenPhish": (
        "https://openphish.com/feed.txt",
        "https://raw.githubusercontent.com/openphish/public_feed/main/feed.txt",
    ),
    "URLhaus": ("https://urlhaus.abuse.ch/downloads/text_online/",),
}
FRAIS_S = 20 * 3600  # une liste plus récente n'est pas retéléchargée (le démon retente les autres toutes les heures)
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

    def _fichier_erreurs(self) -> Path:
        return self.dossier / "flux-erreurs.json"

    def _erreurs(self) -> dict[str, str]:
        try:
            data = json.loads(self._fichier_erreurs().read_text(encoding="utf-8"))
            return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def mettre_a_jour(self, forcer: bool = True) -> list[EtatFlux]:
        """Télécharge chaque liste (sauf, sans `forcer`, celles de moins de 20 h). La raison d'un échec est gardée
        pour `doctor` ; la copie précédente reste utilisée."""
        self.dossier.mkdir(parents=True, exist_ok=True)
        erreurs = self._erreurs()
        etats = []
        for nom, urls in SOURCES.items():
            f = self._fichier(nom)
            if not forcer and f.exists() and time.time() - f.stat().st_mtime < FRAIS_S:
                erreurs.pop(nom, None)
                etats.append(self._etat(nom))
                continue
            echecs: list[str] = []
            for url in urls:
                hote = urllib.parse.urlsplit(url).hostname
                try:
                    r = self.telecharger(url, delai=60, max_octets=80_000_000)
                    if r.statut == 200 and r.corps.strip():
                        temporaire = f.with_suffix(".tmp")
                        temporaire.write_bytes(r.corps)
                        os.replace(temporaire, f)
                        echecs = []
                        break
                    echecs.append(f"{hote} : HTTP {r.statut}")
                except (reseau.ErreurReseau, reseau.HoteInterdit) as e:
                    echecs.append(str(e))
            if echecs:
                erreurs[nom] = " ; ".join(echecs)
            else:
                erreurs.pop(nom, None)
            etats.append(self._etat(nom, erreurs.get(nom, "")))
        temporaire = self._fichier_erreurs().with_suffix(".tmp")
        temporaire.write_text(json.dumps(erreurs, ensure_ascii=False), encoding="utf-8")
        os.replace(temporaire, self._fichier_erreurs())
        self._charge_le = 0.0
        return etats

    def _etat(self, nom: str, erreur: str = "") -> EtatFlux:
        f = self._fichier(nom)
        if not f.exists():
            return EtatFlux(nom, None, 0, erreur or "jamais téléchargé")
        lignes = sum(1 for ligne in f.read_text("utf-8", "replace").splitlines() if ligne.strip())
        return EtatFlux(nom, f.stat().st_mtime, lignes, erreur)

    def etats(self) -> list[EtatFlux]:
        erreurs = self._erreurs()
        return [self._etat(nom, erreurs.get(nom, "")) for nom in SOURCES]

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
