"""Tes listes de Rappels (§4, §6) : « Courses (menu) » et « Anniversaires », et SEULEMENT elles.

- Une liste de ce nom qui existe déjà et que Quotidien n'a pas créée n'est jamais touchée : la nôtre s'appelle alors
  « Courses (menu) (Quotidien) ». Ce qui est à nous est noté en base (`listes_apple`, `rappels_apple`).
- On ne lit jamais le contenu d'une autre liste ; on ne supprime que des rappels que nous avons créés (par leur
  identifiant), dans nos listes. La désinstallation propose de supprimer nos listes, et seulement elles.
- Accès refusé ou pas de Mac : mode dégradé (notifications seules), dit par `quotidien doctor`.
Les scripts reçoivent toutes les valeurs en arguments ; leurs variables commencent par « v » (leçon du Trieur).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from quotidien.db import Base as BaseDonnees
from quotidien.journal import log
from quotidien.systeme import Systeme

SUFFIXE = " (Quotidien)"
ROLES = {"courses": "liste_courses", "anniversaires": "liste_anniversaires"}

_EXISTE = """on run argv
  set vListe to item 1 of argv
  tell application "Reminders"
    if exists list vListe then return "1"
    return "0"
  end tell
end run"""

_CREER_LISTE = """on run argv
  set vListe to item 1 of argv
  tell application "Reminders"
    if not (exists list vListe) then make new list with properties {name:vListe}
    return id of list vListe
  end tell
end run"""

_CREER = """on run argv
  set vListe to item 1 of argv
  set vTitre to item 2 of argv
  set vCorps to item 3 of argv
  set vAvecDate to item 4 of argv
  tell application "Reminders"
    if not (exists list vListe) then return ""
    if vAvecDate is "1" then
      set vDate to current date
      set day of vDate to 1
      set year of vDate to (item 5 of argv) as integer
      set month of vDate to (item 6 of argv) as integer
      set day of vDate to (item 7 of argv) as integer
      set hours of vDate to (item 8 of argv) as integer
      set minutes of vDate to (item 9 of argv) as integer
      set seconds of vDate to 0
      set vProprietes to {name:vTitre, body:vCorps, remind me date:vDate}
      set vRappel to make new reminder at end of list vListe with properties vProprietes
    else
      set vRappel to make new reminder at end of list vListe with properties {name:vTitre, body:vCorps}
    end if
    return id of vRappel
  end tell
end run"""

_SUPPRIMER = """on run argv
  set vListe to item 1 of argv
  set vIdentifiants to items 2 thru -1 of argv
  tell application "Reminders"
    if not (exists list vListe) then return "0"
    set vCompte to 0
    repeat with vIdentifiant in vIdentifiants
      set vTrouves to (every reminder of list vListe whose id is (vIdentifiant as text))
      repeat with vRappel in vTrouves
        delete vRappel
        set vCompte to vCompte + 1
      end repeat
    end repeat
    return vCompte as text
  end tell
end run"""

_SUPPRIMER_LISTE = """on run argv
  set vListe to item 1 of argv
  tell application "Reminders"
    if exists list vListe then delete list vListe
    return "ok"
  end tell
end run"""

_COMPTER = """on run argv
  set vListe to item 1 of argv
  tell application "Reminders"
    if not (exists list vListe) then return "-1"
    return (count of reminders of list vListe) as text
  end tell
end run"""


@dataclass
class Element:
    cle: str  # stable : « courses:2026-10-12:poulet_filet », « anniv:<personne>/<jour> »
    titre: str
    note: str = ""
    quand: datetime | None = None


class Rappels:
    def __init__(self, db: BaseDonnees, systeme: Systeme, reglages: dict[str, Any]) -> None:
        self.db, self.systeme, self.r = db, systeme, reglages["rappels"]
        self.statut = "inconnu"

    # --- Nos listes -----------------------------------------------------------------------------------------------
    def nom_voulu(self, role: str) -> str:
        return str(self.r[ROLES[role]])

    def liste(self, role: str, creer: bool = True) -> str | None:
        """Le nom de NOTRE liste pour ce rôle (créée au besoin). None : Rappels indisponibles, refusés ou désactivés."""
        if not self.r["active"]:
            self.statut = "desactive"
            return None
        if not self.systeme.mac:
            self.statut = "indisponible"
            return None
        connue = self.db.cx.execute("SELECT nom FROM listes_apple WHERE role = ?", (role,)).fetchone()
        if connue is not None:
            nom = str(connue[0])
            existe = self._existe(nom)
            if existe is None or (not existe and not creer):
                return None
            if existe:
                return nom
            # Notre liste supprimée à la main : on la recrée (elle reste la nôtre), vide.
            with self.db.transaction() as cx:
                cx.execute("DELETE FROM rappels_apple WHERE liste = ?", (nom,))
            return nom if self._creer_liste(nom) else None
        if not creer:
            return None
        voulu = self.nom_voulu(role)
        for nom in (voulu, voulu + SUFFIXE):
            existe = self._existe(nom)
            if existe is None:
                return None
            if existe:  # une liste de ce nom existe et n'est pas la nôtre : on n'y touche pas
                continue
            if not self._creer_liste(nom):
                return None
            with self.db.transaction() as cx:
                cx.execute("INSERT OR REPLACE INTO listes_apple(role, nom, creee_par_nous) VALUES (?, ?, 1)",
                           (role, nom))  # fmt: skip
            return nom
        log().warning("Rappels : « %s » et « %s » existent déjà sans être à nous ; rien n'est créé", voulu,
                      voulu + SUFFIXE)  # fmt: skip
        self.statut = "collision"
        return None

    def _existe(self, nom: str) -> bool | None:
        r = self.systeme.applescript(_EXISTE, nom, delai=30)
        if r.code != 0:
            self.statut = "refuse" if "-1743" in r.erreur or "autoris" in r.erreur.lower() else "erreur"
            return None
        self.statut = "ok"
        return r.sortie.strip() == "1"

    def _creer_liste(self, nom: str) -> bool:
        r = self.systeme.applescript(_CREER_LISTE, nom, delai=30)
        if r.code != 0:
            self.statut = "erreur"
            return False
        return True

    # --- Nos rappels ------------------------------------------------------------------------------------------------
    def deja(self, cle: str) -> bool:
        return self.db.cx.execute("SELECT 1 FROM rappels_apple WHERE cle = ?", (cle,)).fetchone() is not None

    def ajouter(self, role: str, elements: list[Element]) -> int:
        """Ajoute ce qui n'y est pas encore (une clé = un rappel, jamais deux). Renvoie le nombre ajouté."""
        nouveaux = [e for e in elements if not self.deja(e.cle)]
        if not nouveaux:
            return 0
        nom = self.liste(role)
        if nom is None:
            return 0
        ajoutes = 0
        for e in nouveaux:
            args = [nom, e.titre[:200], e.note[:2000], "1" if e.quand else "0"]
            if e.quand is not None:
                args += [str(e.quand.year), str(e.quand.month), str(e.quand.day), str(e.quand.hour),
                         str(e.quand.minute)]  # fmt: skip
            r = self.systeme.applescript(_CREER, *args, delai=30)
            identifiant = r.sortie.strip()
            if r.code != 0 or not identifiant:
                log().warning("Rappels : ajout impossible dans notre liste (%s)", r.erreur[:120])
                continue
            with self.db.transaction() as cx:
                cx.execute("INSERT OR IGNORE INTO rappels_apple(liste, identifiant, cle, cree_le) VALUES (?, ?, ?, ?)",
                           (nom, identifiant, e.cle, time.time()))  # fmt: skip
            ajoutes += 1
        return ajoutes

    def retirer(self, role: str, prefixe: str) -> int:
        """Supprime NOS rappels dont la clé commence par `prefixe` (ex. l'ancienne liste de courses d'une semaine)."""
        nom = self.liste(role, creer=False)
        lignes = self.db.lignes("SELECT identifiant, cle FROM rappels_apple WHERE cle LIKE ? AND liste = ?",
                                (prefixe.replace("%", "") + "%", nom or ""))  # fmt: skip
        if not lignes or nom is None:
            return 0
        r = self.systeme.applescript(_SUPPRIMER, nom, *[str(x[0]) for x in lignes], delai=60)
        if r.code != 0:
            return 0
        with self.db.transaction() as cx:
            cx.executemany("DELETE FROM rappels_apple WHERE cle = ?", [(x[1],) for x in lignes])
        return int(r.sortie.strip() or 0)

    def compter(self, nom: str) -> int | None:
        r = self.systeme.applescript(_COMPTER, nom, delai=30)
        if r.code != 0:
            return None
        n = int(r.sortie.strip() or -1)
        return None if n < 0 else n

    def nos_listes(self) -> list[str]:
        return [str(x[0]) for x in self.db.lignes("SELECT nom FROM listes_apple WHERE creee_par_nous = 1")]

    def supprimer_nos_listes(self) -> list[str]:
        """Pour la désinstallation, après ta confirmation : nos listes seulement (celles que nous avons créées)."""
        supprimees = []
        for nom in self.nos_listes():
            if self.systeme.applescript(_SUPPRIMER_LISTE, nom, delai=30).code == 0:
                supprimees.append(nom)
        with self.db.transaction() as cx:
            cx.executemany("DELETE FROM listes_apple WHERE nom = ?", [(n,) for n in supprimees])
            cx.executemany("DELETE FROM rappels_apple WHERE liste = ?", [(n,) for n in supprimees])
        return supprimees

    def retirer_cles(self, role: str, cles: list[str]) -> int:
        """Supprime NOS rappels de ces clés précises (dans notre liste seulement)."""
        nom = self.liste(role, creer=False)
        if nom is None or not cles:
            return 0
        lignes = [x for x in self.db.lignes("SELECT identifiant, cle FROM rappels_apple WHERE liste = ?", (nom,))
                  if x[1] in set(cles)]  # fmt: skip
        if not lignes:
            return 0
        r = self.systeme.applescript(_SUPPRIMER, nom, *[str(x[0]) for x in lignes], delai=60)
        if r.code != 0:
            return 0
        with self.db.transaction() as cx:
            cx.executemany("DELETE FROM rappels_apple WHERE cle = ?", [(x[1],) for x in lignes])
        return int(r.sortie.strip() or 0)

    def synchroniser(self, role: str, prefixe: str, elements: list[Element]) -> tuple[int, int]:
        """La liste de la semaine devient exactement `elements` : ajoute ce qui manque, retire NOS rappels de ce
        préfixe qui n'y sont plus (un article dont la quantité a changé, un plat remplacé). (ajoutés, retirés)"""
        voulues = {e.cle for e in elements}
        anciennes = [str(x[0]) for x in self.db.lignes("SELECT cle FROM rappels_apple WHERE cle LIKE ?",
                                                        (prefixe.replace("%", "") + "%",))]  # fmt: skip
        retires = self.retirer_cles(role, [c for c in anciennes if c not in voulues])
        return self.ajouter(role, elements), retires

    def retirer_anniversaires_passes(self, aujourdhui: date, garde_jours: int = 2) -> int:
        """Un rappel d'anniversaire passé depuis plus de 2 jours est retiré (le nôtre seulement)."""
        limite = (aujourdhui - timedelta(days=garde_jours)).isoformat()
        passees = [str(x[0]) for x in self.db.lignes("SELECT cle FROM rappels_apple WHERE cle LIKE 'anniv:%'")
                   if str(x[0]).rsplit("/", 1)[-1] < limite]  # fmt: skip
        return self.retirer_cles("anniversaires", passees)

    def retirer_semaines_passees(self, role: str, semaine: date) -> int:
        """L'ancienne liste de courses s'efface quand la nouvelle arrive (nos rappels seulement)."""
        retires = 0
        anciennes = sorted({str(x[0]).split(":")[1] for x in self.db.lignes(
            "SELECT cle FROM rappels_apple WHERE cle LIKE 'courses:%'")})  # fmt: skip
        for s in anciennes:
            if s < semaine.isoformat():
                retires += self.retirer(role, f"courses:{s}:")
        return retires


# --- Ce qu'on met dans nos listes -----------------------------------------------------------------------------------


def elements_courses(liste: Any, base: Any) -> list[Element]:
    """Un rappel par article (« 🥬 Courgettes ×3 »), le détail en note (« il en faut 600 g · à congeler »).

    La clé contient une empreinte du texte : si le menu change (« un autre menu », « remplacer jeudi »), un article
    dont la quantité change est un nouveau rappel, et l'ancien est retiré par `synchroniser`."""
    elements = []
    for a in liste.articles:
        note = a.detail + (f" · {a.a_congeler}" if a.a_congeler else "")
        empreinte = hashlib.sha256(f"{a.texte}|{note}".encode()).hexdigest()[:8]
        elements.append(Element(f"courses:{liste.debut}:{a.ingredient}:{empreinte}", a.texte, note))
    return elements


def synchroniser_courses(db: BaseDonnees, systeme: Systeme, reglages: dict[str, Any], liste: Any, base: Any) -> int:
    """Ta liste « Courses (menu) » suit le menu de la semaine (nouveau, régénéré, plat remplacé) ; l'ancienne
    semaine s'efface. Renvoie le nombre d'articles ajoutés."""
    r = Rappels(db, systeme, reglages)
    ajoutes, _ = r.synchroniser("courses", f"courses:{liste.debut}:", elements_courses(liste, base))
    r.retirer_semaines_passees("courses", date.fromisoformat(liste.debut))
    return ajoutes


def elements_anniversaires(db: BaseDonnees, reglages: dict[str, Any], personnes: list[Any], aujourdhui: date,
                           maintenant: float, **ia_kwargs: Any) -> list[Element]:  # fmt: skip
    """La veille et le jour J : « 🎂 Anniversaire de Léa (25 ans) », les 3 messages prêts dans la note (à copier
    depuis l'iPhone). Le rappel sonne le jour J à 9 h."""
    from quotidien.anniversaires import dates, service

    a = reglages["anniversaires"]
    h = reglages["horaires"]
    elements = []
    for jour, p in service.a_venir(personnes, aujourdhui, 1, a["date_29_fevrier"]):
        m = service.message_pret(db, reglages, p, jour, maintenant, **ia_kwargs)
        age = dates.age(p.naissance, jour)
        heure, minute = (int(x) for x in h["anniversaire_jour"].split(":"))
        note = "Messages prêts (copie celui que tu préfères) :\n\n" + "\n\n".join(
            f"{i}. {v}" for i, v in enumerate(m.variantes, 1))  # fmt: skip
        elements.append(Element(f"anniv:{p.cle}/{jour.isoformat()}",
                                f"🎂 Anniversaire de {p.prenom}" + (f" ({age} ans)" if age else ""), note,
                                datetime(jour.year, jour.month, jour.day, heure, minute)))  # fmt: skip
    return elements
