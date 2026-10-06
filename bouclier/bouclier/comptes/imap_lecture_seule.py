"""Gmail en IMAP, en lecture seule absolue (§1.2).

Seules deux commandes partent vers le serveur une fois connecté, en plus de LIST et EXAMINE :
- `UID SEARCH` (trouver des messages) ;
- `UID FETCH` avec des éléments qui ne marquent rien : `BODY.PEEK[…]`, `FLAGS`, `X-GM-LABELS`, `UID`,
  `RFC822.SIZE`, `INTERNALDATE`. Un `BODY[…]` sans PEEK, `RFC822` ou `BINARY[…]` marquerait le message comme lu :
  ils sont refusés avant d'être envoyés.

Toute boîte est ouverte avec `readonly=True` (commande EXAMINE). Aucune autre méthode du client IMAP n'est appelée.
"""

from __future__ import annotations

import imaplib
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

SERVEUR = "imap.gmail.com"
_ELEMENTS_PERMIS = re.compile(
    r"^\(?\s*(?:(?:BODY\.PEEK\[[^\]]*\](?:<\d+\.\d+>)?|FLAGS|X-GM-LABELS|X-GM-MSGID|UID|RFC822\.SIZE|INTERNALDATE)"
    r"(?:\s+|(?=\))|$))+\)?\s*$",
    re.IGNORECASE,
)
_LISTE = re.compile(rb'^\((?P<attributs>[^)]*)\)\s+(?:"[^"]*"|NIL)\s+(?P<nom>.+)$')


def _entre_guillemets(nom: str) -> str:
    """imaplib n'entoure pas lui-même un nom de dossier avec espaces (« [Gmail]/Tous les messages »)."""
    if nom.startswith('"') or re.fullmatch(r"[A-Za-z0-9_./\-\[\]&]+", nom):
        return nom
    return '"' + nom.replace("\\", "\\\\").replace('"', '\\"') + '"'


class ImapInterdit(Exception):
    """Une commande qui pourrait modifier la boîte a été demandée : elle n'est jamais envoyée."""


class ErreurImap(Exception):
    """Connexion, identifiants, boîte introuvable : Bouclier passe en mode dégradé et l'explique."""


Fabrique = Callable[[str], Any]


def _fabrique_reelle(serveur: str) -> Any:
    return imaplib.IMAP4_SSL(serveur, 993, timeout=60)


def verifier_elements(elements: str) -> None:
    if not _ELEMENTS_PERMIS.match(elements.strip()):
        raise ImapInterdit(f"éléments refusés (pourraient marquer le message comme lu) : {elements}")


@dataclass
class Entete:
    uid: int
    brut: bytes


class LecteurImap:
    def __init__(self, fabrique: Fabrique = _fabrique_reelle, serveur: str = SERVEUR) -> None:
        self.fabrique, self.serveur = fabrique, serveur
        self.cx: Any = None
        self.dossier: str | None = None

    # --- Connexion ---------------------------------------------------------------------------------------------------
    def connecter(self, adresse: str, mot_de_passe: str) -> None:
        try:
            self.cx = self.fabrique(self.serveur)
            self.cx.login(adresse, mot_de_passe)
        except imaplib.IMAP4.error as e:
            self.cx = None
            raise ErreurImap(
                f"Gmail refuse la connexion ({str(e)[:80]}) : vérifie le mot de passe d'application"
            ) from e
        except OSError as e:
            self.cx = None
            raise ErreurImap(f"Gmail injoignable ({e.__class__.__name__})") from e

    def fermer(self) -> None:
        if self.cx is not None:
            try:
                self.cx.logout()
            except Exception:  # noqa: BLE001 - la session peut déjà être coupée
                pass
            self.cx = None

    def __enter__(self) -> LecteurImap:
        return self

    def __exit__(self, *_: object) -> None:
        self.fermer()

    # --- Dossiers ----------------------------------------------------------------------------------------------------
    def dossiers(self) -> list[tuple[set[str], str]]:
        statut, lignes = self.cx.list()
        if statut != "OK":
            raise ErreurImap("liste des dossiers illisible")
        sortie = []
        for ligne in lignes or []:
            if not isinstance(ligne, bytes):
                continue
            m = _LISTE.match(ligne)
            if m:
                attributs = {a.decode().lower() for a in m.group("attributs").split()}
                sortie.append((attributs, m.group("nom").decode()))
        return sortie

    def dossier_special(self, attribut: str) -> str:
        """Le dossier qui porte un attribut spécial (\\All = « Tous les messages », quelle que soit la langue)."""
        for attributs, nom in self.dossiers():
            if attribut.lower() in attributs:
                return nom[1:-1].replace('\\"', '"').replace("\\\\", "\\") if nom.startswith('"') else nom
        raise ErreurImap(f"dossier {attribut} introuvable (« Tous les messages » masqué dans Gmail ?)")

    def examiner(self, dossier: str) -> tuple[int, str]:
        """Ouvre une boîte en lecture seule (EXAMINE). Renvoie (nombre de messages, UIDVALIDITY)."""
        statut, donnees = self.cx.select(_entre_guillemets(dossier), readonly=True)
        if statut != "OK":
            raise ErreurImap(f"dossier {dossier} introuvable")
        self.dossier = dossier
        validite = ""
        try:
            reponse = self.cx.response("UIDVALIDITY")
            if reponse and reponse[1] and reponse[1][0]:
                validite = reponse[1][0].decode() if isinstance(reponse[1][0], bytes) else str(reponse[1][0])
        except Exception:  # noqa: BLE001 - simple information
            validite = ""
        return int(donnees[0] or 0) if donnees and donnees[0] else 0, validite

    # --- Lecture -----------------------------------------------------------------------------------------------------
    def _uid(self, commande: str, *args: str) -> Any:
        if self.dossier is None:
            raise ImapInterdit("aucune boîte ouverte en lecture seule")
        commande = commande.upper()
        if commande == "FETCH":
            verifier_elements(args[-1])
        elif commande != "SEARCH":
            raise ImapInterdit(f"commande refusée : UID {commande}")
        statut, donnees = self.cx.uid(commande, *args)
        if statut != "OK":
            raise ErreurImap(f"UID {commande} refusé par le serveur")
        return donnees

    def uids_depuis(self, dernier_uid: int) -> list[int]:
        donnees = self._uid("SEARCH", "UID", f"{dernier_uid + 1}:*")
        uids = [int(x) for x in (donnees[0] or b"").split()] if donnees else []
        return sorted(u for u in uids if u > dernier_uid)  # « n:* » renvoie toujours le dernier, même plus ancien

    def _par_lots(self, uids: list[int], taille: int) -> Iterator[list[int]]:
        for i in range(0, len(uids), taille):
            yield uids[i : i + taille]

    def entetes(
        self, uids: list[int], champs: str = "FROM SUBJECT DATE LIST-UNSUBSCRIBE", lot: int = 500
    ) -> Iterator[Entete]:
        elements = f"(UID BODY.PEEK[HEADER.FIELDS ({champs})])"
        for morceau in self._par_lots(uids, lot):
            for uid, brut in self._lire(self._uid("FETCH", ",".join(map(str, morceau)), elements)):
                yield Entete(uid, brut)

    def message(self, uid: int, max_octets: int) -> bytes:
        """Le message entier (ou ses `max_octets` premiers octets), sans le marquer comme lu."""
        elements = f"(UID BODY.PEEK[]<0.{max_octets}>)"
        lus = list(self._lire(self._uid("FETCH", str(uid), elements)))
        return lus[0][1] if lus else b""

    def drapeaux(self, uids: list[int]) -> dict[int, tuple[str, ...]]:
        """Drapeaux (\\Seen…) et libellés Gmail : relevés avant et après une analyse, ils doivent être identiques."""
        sortie: dict[int, tuple[str, ...]] = {}
        donnees = self._uid("FETCH", ",".join(map(str, uids)), "(UID FLAGS X-GM-LABELS)")
        for element in donnees or []:
            texte = element.decode("utf-8", "replace") if isinstance(element, bytes) else ""
            m = re.search(r"UID (\d+)", texte)
            if m:
                jetons = texte.split("(", 1)[-1].replace("(", " ").replace(")", " ").split()
                sortie[int(m.group(1))] = tuple(sorted(jetons))
        return sortie

    @staticmethod
    def _lire(donnees: Any) -> Iterator[tuple[int, bytes]]:
        for element in donnees or []:
            if isinstance(element, tuple) and len(element) == 2:
                m = re.search(rb"UID (\d+)", element[0])
                if m:
                    yield int(m.group(1)), element[1]
