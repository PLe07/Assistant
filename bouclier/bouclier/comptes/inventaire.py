"""L'inventaire de tes comptes (n°18), sans jamais lire le contenu de tes mails.

Sources, toutes en lecture seule :
- Gmail : seulement les en-têtes FROM, SUBJECT, DATE et LIST-UNSUBSCRIBE du dossier « Tous les messages »
  (attribut \\All), par lots, en reprenant au dernier message vu ;
- navigateurs : seulement le site et le nom d'utilisateur des identifiants enregistrés.

Classement :
- **compte probable** : un mail de bienvenue, de vérification d'adresse, de réinitialisation de mot de passe, de
  connexion inhabituelle ou de confirmation de commande, ou un identifiant enregistré dans un navigateur ;
- **simple abonnement** : uniquement des lettres d'information (en-tête de désinscription) ;
- **autre expéditeur** : ni l'un ni l'autre (non affiché comme un compte).
Les mails de personnes (adresse Gmail, Outlook…) ne sont jamais comptés.

Aucune action automatique : tu poses toi-même les statuts (à garder, à supprimer, supprimé).
"""

from __future__ import annotations

import datetime as dt
import email.utils
import json
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesHeaderParser
from typing import Any

from bouclier.arnaque.entetes import WEBMAILS
from bouclier.comptes import regroupement
from bouclier.comptes.imap_lecture_seule import LecteurImap
from bouclier.comptes.navigateurs import Identifiant
from bouclier.db import Base

SIGNAUX = {
    "creation": re.compile(
        r"bienvenue|welcome|votre compte (a été|a bien été|est) (créé|activé|ouvert)|account (created|activated)"
        r"|merci (de vous être|de t'être|pour votre) inscri|thanks? for (signing up|joining|registering)"
        r"|confirm(ez|ation de) (votre|ton) inscription|activ(ez|ate) (votre|ton|your) (compte|account)"
        r"|finalis(ez|e) (votre|ton) inscription|création de (votre|ton) compte|your new account",
        re.IGNORECASE,
    ),
    "verification": re.compile(
        r"v[ée]rifi(ez|cation|er|e) (de )?(votre |ton |l')?(adresse|e-?mail|compte)|confirm(ez|er|e) (votre|ton) "
        r"(adresse|e-?mail)|verify (your )?(email|e-mail|account|address)|confirm your (email|e-mail|address)"
        r"|code de (vérification|confirmation|sécurité)|verification code|security code|one-time (code|password)",
        re.IGNORECASE,
    ),
    "reinitialisation": re.compile(
        r"r[ée]initialis\w*.{0,20}mot de passe|mot de passe (oublié|modifié|changé)|nouveau mot de passe"
        r"|reset (your )?password|password (reset|changed|change|updated)|forgot (your )?password"
        r"|changement de (votre |ton )?mot de passe",
        re.IGNORECASE,
    ),
    "connexion": re.compile(
        r"nouvelle connexion|connexion (inhabituelle|depuis un nouvel appareil|détectée)|nouvel appareil"
        r"|new (sign-?in|login|device)|sign-?in (attempt|alert|from)|security alert|alerte de sécurité"
        r"|login (from|alert)|someone (signed|logged) in",
        re.IGNORECASE,
    ),
    "commande": re.compile(
        r"confirmation de (votre |ta )?commande|votre commande|commande n°|n° de commande|order confirm"
        r"|your order|order #|reçu de (votre |ta )?(paiement|commande)|your receipt|votre reçu|votre facture"
        r"|votre réservation|booking confirm|réservation confirmée",
        re.IGNORECASE,
    ),
}
SIGNAUX_DE_COMPTE = frozenset(SIGNAUX)
ORDRE_NATURE = {"compte": 2, "abonnement": 1, "autre": 0}


@dataclass
class Observation:
    hote: str
    date: dt.date | None
    signaux: set[str]
    lettre: bool  # en-tête de désinscription (lettre d'information)


def _valeur(entetes: Any, nom: str) -> str:
    """Un en-tête décodé (=?utf-8?…?= comme UTF-8 brut, RFC 6532) ; un en-tête abîmé vaut « »."""
    try:
        v = entetes.get(nom)
    except Exception:  # noqa: BLE001 - un en-tête mal formé est ignoré
        return ""
    return str(v) if v is not None else ""


def observer(brut: bytes) -> Observation | None:
    entetes = BytesHeaderParser(policy=policy.default).parsebytes(brut)
    _, adresse = email.utils.parseaddr(_valeur(entetes, "From"))
    if "@" not in adresse:
        return None
    hote = adresse.rsplit("@", 1)[1].lower().strip(">. ")
    sujet = _valeur(entetes, "Subject")
    date: dt.date | None = None
    try:
        d = email.utils.parsedate_to_datetime(_valeur(entetes, "Date"))
        date = d.date() if d else None
    except (TypeError, ValueError, IndexError):
        date = None
    signaux = {nom for nom, motif in SIGNAUX.items() if motif.search(sujet)}
    return Observation(hote, date, signaux, bool(_valeur(entetes, "List-Unsubscribe")))


@dataclass
class CompteTrouve:
    service: regroupement.Service
    domaines: set[str] = field(default_factory=set)
    signaux: dict[str, int] = field(default_factory=dict)
    sources: set[str] = field(default_factory=set)
    lettres: int = 0
    mails: int = 0
    premiere_vue: dt.date | None = None
    derniere_activite: dt.date | None = None

    @property
    def nature(self) -> str:
        if "navigateur" in self.sources or SIGNAUX_DE_COMPTE & set(self.signaux):
            return "compte"
        if self.lettres:
            return "abonnement"
        return "autre"

    def dater(self, date: dt.date | None) -> None:
        if date is None:
            return
        self.premiere_vue = min(filter(None, (self.premiere_vue, date)))
        self.derniere_activite = max(filter(None, (self.derniere_activite, date)))


class Inventaire:
    def __init__(self, exclus: Iterable[str] = ()) -> None:
        self.comptes: dict[str, CompteTrouve] = {}
        self.exclus = {e.lower() for e in exclus} | set(WEBMAILS)

    def _compte(self, hote: str) -> CompteTrouve | None:
        hote = hote.lower().strip(".")
        if not hote or "." not in hote or hote in self.exclus:
            return None
        service = regroupement.identifier(hote)
        c = self.comptes.setdefault(service.id, CompteTrouve(service))
        c.domaines.add(hote)
        return c

    def ajouter_mail(self, obs: Observation) -> None:
        c = self._compte(obs.hote)
        if c is None:
            return
        c.sources.add("gmail")
        c.mails += 1
        c.lettres += int(obs.lettre)
        for s in obs.signaux:
            c.signaux[s] = c.signaux.get(s, 0) + 1
        c.dater(obs.date)

    def ajouter_identifiant(self, ident: Identifiant) -> None:
        hote = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", ident.site.lower()).split("/")[0].split(":")[0]
        if hote.startswith(("android", "ios")) or not hote:
            return
        c = self._compte(hote)
        if c is not None:
            c.sources.add("navigateur")


# --- Gmail ---------------------------------------------------------------------------------------------------------


@dataclass
class ResultatGmail:
    dossier: str
    lus: int
    total_uid: int


def releve_gmail(
    lecteur: LecteurImap, base: Base, inventaire: Inventaire, max_messages: int = 100_000, lot: int = 500
) -> ResultatGmail:
    """Les en-têtes des messages pas encore vus du dossier « Tous les messages » (lecture seule)."""
    dossier = lecteur.dossier_special("\\All")
    _, validite = lecteur.examiner(dossier)
    ligne = base.cx.execute("SELECT uidvalidity, dernier_uid FROM gmail WHERE dossier = 'inventaire'").fetchone()
    dernier = int(ligne["dernier_uid"]) if ligne and ligne["uidvalidity"] == validite else 0
    uids = lecteur.uids_depuis(dernier)[-max_messages:]
    lus = 0
    for entete in lecteur.entetes(uids, lot=lot):
        obs = observer(entete.brut)
        if obs is not None:
            inventaire.ajouter_mail(obs)
        lus += 1
    if uids:
        with base.transaction() as cx:
            cx.execute("INSERT OR REPLACE INTO gmail(dossier, uidvalidity, dernier_uid) VALUES ('inventaire', ?, ?)",
                       (validite, max(uids)))  # fmt: skip
    return ResultatGmail(dossier, lus, len(uids))


# --- Enregistrement ------------------------------------------------------------------------------------------------


def enregistrer(base: Base, inventaire: Inventaire, horloge: Callable[[], float] = time.time) -> int:
    """Fusionne avec ce qui est déjà en base (dates, signaux, sources) ; ton statut n'est jamais changé."""
    n = 0
    with base.transaction() as cx:
        for ident, c in inventaire.comptes.items():
            ancien = cx.execute("SELECT * FROM comptes WHERE service = ?", (ident,)).fetchone()
            signaux = dict(c.signaux)
            sources = set(c.sources)
            domaines = set(c.domaines)
            premiere, derniere = c.premiere_vue, c.derniere_activite
            nature = c.nature
            if ancien:
                for k, v in json.loads(ancien["signaux"]).items():
                    signaux[k] = signaux.get(k, 0) + int(v)
                sources |= set(json.loads(ancien["sources"]))
                domaines |= set(json.loads(ancien["domaines"]))
                dates_p = [d for d in (premiere, _date(ancien["premiere_vue"])) if d]
                dates_d = [d for d in (derniere, _date(ancien["derniere_activite"])) if d]
                premiere, derniere = (min(dates_p) if dates_p else None), (max(dates_d) if dates_d else None)
                if ORDRE_NATURE[ancien["nature"]] > ORDRE_NATURE[nature]:
                    nature = ancien["nature"]
            cx.execute(
                "INSERT INTO comptes(service, nom, categorie, nature, domaines, premiere_vue, derniere_activite,"
                " sources, signaux, vu_le) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(service) DO UPDATE SET nom=excluded.nom, categorie=excluded.categorie,"
                " nature=excluded.nature, domaines=excluded.domaines, premiere_vue=excluded.premiere_vue,"
                " derniere_activite=excluded.derniere_activite, sources=excluded.sources, signaux=excluded.signaux,"
                " vu_le=excluded.vu_le",
                (ident, c.service.nom, c.service.categorie, nature, json.dumps(sorted(domaines)),
                 premiere.isoformat() if premiere else None, derniere.isoformat() if derniere else None,
                 json.dumps(sorted(sources)), json.dumps(signaux, sort_keys=True), horloge()),
            )  # fmt: skip
            n += 1
    return n


def _date(texte: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat(texte) if texte else None
    except ValueError:
        return None


STATUTS = {"garder": "a_garder", "supprimer": "a_supprimer", "supprime": "supprime", "a_trier": "a_trier"}


def poser_statut(base: Base, ident: str, statut: str) -> bool:
    with base.transaction() as cx:
        return cx.execute("UPDATE comptes SET statut = ? WHERE service = ?", (STATUTS[statut], ident)).rowcount == 1


@dataclass
class Ligne:
    id: str
    nom: str
    categorie: str
    nature: str
    statut: str
    premiere_vue: str | None
    derniere_activite: str | None
    sources: list[str]
    signaux: dict[str, int]
    service: regroupement.Service | None


def lignes(base: Base, natures: tuple[str, ...] = ("compte", "abonnement")) -> list[Ligne]:
    marques = ",".join("?" for _ in natures)
    sortie = []
    for r in base.lignes(f"SELECT * FROM comptes WHERE nature IN ({marques}) ORDER BY categorie, nom", natures):
        sortie.append(Ligne(r["service"], r["nom"], r["categorie"], r["nature"], r["statut"], r["premiere_vue"],
                            r["derniere_activite"], json.loads(r["sources"]), json.loads(r["signaux"]),
                            regroupement.service(r["service"])))  # fmt: skip
    return sortie


def compter(base: Base) -> dict[str, int]:
    return {str(r[0]): int(r[1]) for r in base.lignes("SELECT nature, COUNT(*) FROM comptes GROUP BY nature")}


def domaines_des_comptes(base: Base) -> dict[str, list[str]]:
    """Pour l'alerte fuites (n°19) : service → domaines, seulement les comptes probables pas encore supprimés."""
    return {str(r["service"]): json.loads(r["domaines"]) for r in base.lignes(
        "SELECT service, domaines FROM comptes WHERE nature = 'compte' AND statut != 'supprime'")}  # fmt: skip


def resume(inventaire: Inventaire) -> dict[str, Any]:
    natures: dict[str, int] = {}
    for c in inventaire.comptes.values():
        natures[c.nature] = natures.get(c.nature, 0) + 1
    return natures
