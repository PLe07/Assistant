"""Les anniversaires des Contacts du Mac (§6), en LECTURE SEULE (`CNContactStore`, via pyobjc).

- Seules ces informations sont lues : identifiant, prénom, nom, surnom, anniversaire et numéros (pour préremplir
  Messages). Aucune requête d'écriture n'existe ici (un test le vérifie).
- L'accès est demandé une seule fois, depuis le Terminal (`quotidien anniversaires`) : le démon ne fait jamais
  apparaître de fenêtre ; sans accès, il passe en mode dégradé (`proches.toml` et notifications).
- Un contact supprimé disparaît simplement de la lecture suivante : ses rappels à venir ne sont plus émis.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from quotidien.anniversaires import dates
from quotidien.anniversaires.proches import Personne, cle_de

# Un « fournisseur » rend (statut, fiches brutes) : le vrai lit les Contacts du Mac, les tests en imitent un.
Fournisseur = Callable[[], tuple[str, list[dict[str, Any]]]]
STATUTS = {
    "ok": "accès accordé",
    "non_demande": "accès jamais demandé : lance « quotidien anniversaires » dans le Terminal",
    "refuse": "accès refusé : Réglages Système → Confidentialité et sécurité → Contacts",
    "indisponible": "Contacts indisponibles sur cette machine (pas un Mac ?)",
    "erreur": "lecture des Contacts impossible",
}
INDEFINI = 9223372036854775807  # NSDateComponentUndefined (année absente)


@dataclass
class LectureContacts:
    statut: str
    personnes: list[Personne] = field(default_factory=list)
    sans_date: int = 0  # contacts lus mais sans anniversaire (comptés, jamais listés)
    ignores: int = 0  # date impossible (30 février…)


def _mobile(numeros: list[tuple[str, str]]) -> str:
    """Le numéro à préremplir : le mobile ou l'iPhone d'abord, sinon le premier."""
    for etiquette, numero in numeros:
        if any(m in (etiquette or "").lower() for m in ("mobile", "iphone", "portable")):
            return numero
    return numeros[0][1] if numeros else ""


def lire(aujourdhui: date, fournisseur: Fournisseur | None = None) -> LectureContacts:
    statut, bruts = (fournisseur or contacts_du_mac)()
    lecture = LectureContacts(statut)
    if statut != "ok":
        return lecture
    for b in bruts:
        jour, mois = b.get("jour"), b.get("mois")
        if not jour or not mois:
            lecture.sans_date += 1
            continue
        annee = b.get("annee")
        try:
            naissance = dates.valider(int(jour), int(mois), None, aujourdhui)
            if annee and annee != INDEFINI:
                naissance = dates.valider(int(jour), int(mois), int(annee), aujourdhui)
        except dates.DateInvalide:
            if annee and annee != INDEFINI and naissance_sans_annee_valide(int(jour), int(mois)):
                naissance = dates.DateNaissance(int(jour), int(mois))  # année absurde : on garde le jour
            else:
                lecture.ignores += 1
                continue
        prenom = (b.get("prenom") or b.get("surnom") or "").strip()
        if not prenom:
            lecture.ignores += 1
            continue
        lecture.personnes.append(Personne(
            cle=cle_de("contact", str(b.get("identifiant") or prenom + (b.get("nom") or ""))),
            prenom=prenom, nom=(b.get("nom") or "").strip(), naissance=naissance,
            telephone=_mobile(list(b.get("telephones") or [])), source="contacts",
        ))  # fmt: skip
    return lecture


def naissance_sans_annee_valide(jour: int, mois: int) -> bool:
    try:
        dates.valider(jour, mois)
    except dates.DateInvalide:
        return False
    return True


# --- Le vrai Mac ----------------------------------------------------------------------------------------------------


def _contacts() -> Any:  # pragma: no cover - sur le Mac
    import Contacts

    return Contacts


def statut_mac() -> str:  # pragma: no cover - sur le Mac
    try:
        cn = _contacts()
    except ImportError:
        return "indisponible"
    etat = int(cn.CNContactStore.authorizationStatusForEntityType_(cn.CNEntityTypeContacts))
    return {0: "non_demande", 1: "refuse", 2: "refuse"}.get(etat, "ok")  # 3 : accordé, 4 : accès limité


def demander_acces(delai: float = 120) -> str:  # pragma: no cover - sur le Mac, depuis le Terminal
    """La fenêtre « Autoriser l'accès à tes Contacts » (une seule fois ; macOS retient la réponse)."""
    statut = statut_mac()
    if statut != "non_demande":
        return statut
    cn = _contacts()
    fini = threading.Event()
    reponse: list[bool] = []

    def rappel(accorde: bool, _erreur: Any) -> None:
        reponse.append(bool(accorde))
        fini.set()

    cn.CNContactStore.alloc().init().requestAccessForEntityType_completionHandler_(cn.CNEntityTypeContacts, rappel)
    fini.wait(delai)
    return "ok" if reponse and reponse[0] else statut_mac()


def contacts_du_mac() -> tuple[str, list[dict[str, Any]]]:  # pragma: no cover - sur le Mac
    statut = statut_mac()
    if statut != "ok":
        return statut, []
    cn = _contacts()
    magasin = cn.CNContactStore.alloc().init()
    cles = [cn.CNContactIdentifierKey, cn.CNContactGivenNameKey, cn.CNContactFamilyNameKey, cn.CNContactNicknameKey,
            cn.CNContactBirthdayKey, cn.CNContactPhoneNumbersKey]  # fmt: skip
    requete = cn.CNContactFetchRequest.alloc().initWithKeysToFetch_(cles)
    trouves: list[dict[str, Any]] = []

    def un_contact(contact: Any, _stop: Any) -> None:
        naissance = contact.birthday()
        numeros = [(str(n.label() or ""), str(n.value().stringValue())) for n in (contact.phoneNumbers() or [])]
        trouves.append({
            "identifiant": str(contact.identifier()),
            "prenom": str(contact.givenName() or ""), "nom": str(contact.familyName() or ""),
            "surnom": str(contact.nickname() or ""),
            "jour": int(naissance.day()) if naissance is not None else None,
            "mois": int(naissance.month()) if naissance is not None else None,
            "annee": int(naissance.year()) if naissance is not None else None,
            "telephones": numeros,
        })  # fmt: skip

    try:
        ok, erreur = magasin.enumerateContactsWithFetchRequest_error_usingBlock_(requete, None, un_contact)
    except Exception:  # noqa: BLE001 - pyobjc : toute erreur des Contacts → mode dégradé
        return "erreur", []
    if not ok:
        return "erreur", []
    for t in trouves:  # un jour ou un mois « indéfini » : pas de date
        if t["jour"] in (None, INDEFINI) or t["mois"] in (None, INDEFINI):
            t["jour"] = t["mois"] = None
    return "ok", trouves
