"""C4 — L'historique zsh (~/.zsh_history), lu par petits bouts : seulement ce qui a été ajouté depuis la dernière fois.

Gère le format étendu « : horodatage:durée;commande », les commandes sur plusieurs lignes (un « \\ » en fin de ligne)
et l'encodage propre à zsh (octet 0x83 suivi du caractère XOR 0x20). Ne touche jamais à ton .zshrc. Au premier
passage, on commence à la fin du fichier : le passé d'avant l'installation n'est pas lu.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from modules.corvees.capteurs.base import Capteur
from modules.corvees.normalize import tok_commande
from modules.corvees.privacy import caviarder

_ETENDU = re.compile(r"^: (\d+):(\d+);(.*)$", re.S)
CLE = "curseur.shell"


def demetafier(octets: bytes) -> bytes:
    """L'encodage de zsh : 0x83 annonce un octet « méta » (XOR 0x20)."""
    if b"\x83" not in octets:
        return octets
    sortie = bytearray()
    i = 0
    while i < len(octets):
        if octets[i] == 0x83 and i + 1 < len(octets):
            sortie.append(octets[i + 1] ^ 0x20)
            i += 2
        else:
            sortie.append(octets[i])
            i += 1
    return bytes(sortie)


def lire_historique(octets: bytes) -> list[tuple[int | None, str]]:
    """[(horodatage ou None, commande)] : une entrée par commande, les commandes multi-lignes réunies."""
    lignes = demetafier(octets).decode("utf-8", errors="replace").split("\n")
    entrees: list[tuple[int | None, str]] = []
    actuelle: str | None = None
    for ligne in lignes:
        actuelle = ligne if actuelle is None else actuelle + "\n" + ligne
        if actuelle.endswith("\\"):  # la commande continue sur la ligne suivante
            actuelle = actuelle[:-1]
            continue
        m = _ETENDU.match(actuelle)
        ts, commande = (int(m.group(1)), m.group(3)) if m else (None, actuelle)
        if commande.strip():
            entrees.append((ts, commande.strip()))
        actuelle = None
    return entrees


def _cle(commande: str) -> str:
    """Une empreinte courte de la commande déjà caviardée : ni la commande, ni un secret qu'elle contiendrait, ne
    peuvent être retrouvés depuis le curseur."""
    return hashlib.sha1(caviarder(commande).encode()).hexdigest()[:12]


def _empreinte_avant(f, position: int) -> str:
    """L'empreinte des 64 octets qui précèdent la position : si elle change, le fichier a été réécrit (même si
    le système a redonné le même numéro de fichier et que le nouveau est plus long)."""
    debut = max(0, position - 64)
    f.seek(debut)
    return hashlib.sha1(f.read(position - debut)).hexdigest()


class Shell(Capteur):
    nom = "shell"
    intervalle = 60.0

    def __init__(self, *args, maison: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.chemin = Path(os.path.expanduser(self.reglages["shell"]["historique"]))
        self.maison = maison

    def demarrer(self) -> None:
        if not self.chemin.exists():
            self.degrader(f"pas (encore) d'historique : {self.chemin}")

    def relever(self, maintenant: float) -> None:
        curseur = self.memoire.lire(CLE) or {}
        try:
            infos = os.stat(self.chemin)
        except FileNotFoundError:
            self.degrader(f"pas (encore) d'historique : {self.chemin}")
            return
        except OSError as e:
            self.degrader(f"historique illisible ({e.__class__.__name__})")
            return
        if not curseur:  # premier passage : on part de la fin
            with open(self.chemin, "rb") as f:
                empreinte = _empreinte_avant(f, infos.st_size)
            self.memoire.ecrire(
                CLE,
                {
                    "inode": infos.st_ino,
                    "position": infos.st_size,
                    "dernier_ts": int(maintenant),
                    "empreinte": empreinte,
                },
            )
            self.statut, self.detail = "ok", ""
            return
        position = int(curseur.get("position", 0))
        try:
            with open(self.chemin, "rb") as f:
                # zsh sauve souvent par copie (nouveau numéro de fichier, même début) : ce n'est une réécriture que
                # si ce qui précède notre position a changé.
                reecrit = infos.st_size < position or _empreinte_avant(f, position) != curseur.get(
                    "empreinte", _empreinte_avant(f, position)
                )
                if reecrit:  # zsh a réécrit le fichier (taille limite, autre shell) : on relit, sans redonner l'ancien
                    position = 0
                f.seek(position)
                brut = f.read()
        except OSError as e:  # verrouillé, droits… : on réessaiera
            self.degrader(f"historique illisible ({e.__class__.__name__})")
            return
        self.statut, self.detail = "ok", ""
        complet = brut[: brut.rfind(b"\n") + 1]  # la dernière ligne pas encore finie attend le prochain passage
        dernier = int(curseur.get("dernier_ts", 0))
        deja_vues = set(curseur.get("vues", [])) if reecrit else set()
        vues = list(curseur.get("vues", []))  # les commandes déjà lues dans la seconde « dernier »
        for ts, commande in lire_historique(complet):
            # Lu depuis la position : tout est nouveau, même dans la seconde de la commande précédente (zsh note
            # l'heure à la seconde). Fichier réécrit : l'horodatage, et les commandes déjà lues dans la dernière
            # seconde, disent ce qui est nouveau.
            if ts is None:
                if reecrit:
                    continue  # sans horodatage, impossible de savoir si c'est nouveau : on ne redonne rien
                ts = int(maintenant)
            elif reecrit and (ts < dernier or (ts == dernier and _cle(commande) in deja_vues)):
                continue
            self.emettre(float(ts), "cmd", tok_commande(commande, self.maison))
            if ts > dernier:
                dernier, vues = ts, []
            if ts == dernier:
                vues.append(_cle(commande))
        fin = position + len(complet)
        with open(self.chemin, "rb") as f:
            empreinte = _empreinte_avant(f, fin)
        self.memoire.ecrire(
            CLE,
            {
                "inode": infos.st_ino,
                "position": fin,
                "dernier_ts": max(dernier, 0),
                "empreinte": empreinte,
                "vues": vues[-50:],
            },
        )
