"""Les alertes : utiles, rares, jamais en double (§6).

Chaque problème vu par la santé (`sante.problemes`) a une clé stable (« bouclier:boucle », « trieur:file:BoiteMac »).
Il vit dans la table `problemes` de notre base, ce qui survit à un redémarrage du tableau de bord : jamais deux
alertes pour le même problème.

- **Confirmé** avant d'alerter : vu au moins deux tours de suite et depuis `confirmation_s` (90 s). Pas d'alerte
  dans les `reveil_grace_s` (10 min) qui suivent un réveil ou un redémarrage : le temps que tout se remette en route.
- **Une alerte**, puis **un rappel** toutes les `rappel_heures` (24 h) tant qu'il dure, et **un message de
  résolution** quand il a disparu depuis `resolution_s` (150 s). Revenu avant ce délai : rien n'a été dit, rien
  n'est répété. Un problème réglé sans avoir été annoncé ne fait aucun bruit.
- **Au plus `max_par_jour` notifications** (3) par jour : ce qui arrive en même temps part **dans une seule**
  (on attend jusqu'à `regroupement_s` qu'un problème en cours de confirmation rejoigne les autres).
- **Rien entre 23 h et 8 h**, sauf une boucle de plantages qui consomme (`nuit_permise`) ; le reste part à 8 h, en
  une notification.
- **Sourdine** (« 1 h », « 30 min », « jusqu'à demain ») : rien ne part ; ce qui est encore vrai à la fin part alors.
- Le code changé que tu acceptes (« C'était moi, nouvelle référence ») est clos sans message.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from tableau import planif, textes
from tableau.config import Reglages
from tableau.db import Base
from tableau.module import EtatModule, Pastille, Probleme
from tableau.notifier import Notificateur

TITRE = "Tableau de bord"
LIGNES_MAX = 4
# Les problèmes d'un même module qui se remplacent l'un l'autre.
FAMILLES = {"boucle": "marche", "arrete": "marche", "fige": "marche", "n8n": "marche", "budget80": "budget",
            "budget100": "budget"}  # fmt: skip


def famille(genre: str) -> str:
    return FAMILLES.get(genre, "")


@dataclass
class Element:
    """Une ligne à annoncer : alerte, rappel, résolution ou information (rapport de la semaine)."""

    genre: str  # alerte, rappel, resolution, info
    cle: str
    texte: str
    gravite: str = "attention"
    nuit_permise: bool = False
    depuis: float = 0.0  # depuis quand elle attend de partir

    @property
    def ordre(self) -> tuple[int, float]:
        rang = {"alerte": 0 if self.gravite == "grave" else 1, "rappel": 2, "resolution": 3, "info": 4}
        return rang.get(self.genre, 5), self.depuis


@dataclass
class Envoi:
    titre: str
    texte: str
    elements: list[Element] = field(default_factory=list)
    envoyee: bool = False
    motif: str = ""


def lire_duree(texte: str) -> float | None:
    """« 1h », « 1 h », « 30min », « 2h30 », « 45 » (minutes), « 0 » ou « fin » (lever) → secondes. None : illisible."""
    t = texte.strip().lower().replace(" ", "")
    if t in ("0", "fin", "stop", "off", "lever"):
        return 0.0
    m = re.fullmatch(r"(?:(\d{1,3})(?:h|heures?))?(?:(\d{1,4})(?:m|min|minutes?)?)?", t)
    if not m or not (m.group(1) or m.group(2)):
        return None
    heures = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    total = heures * 3600 + minutes * 60
    return float(total) if 0 < total <= 7 * 86400 else None


class Alertes:
    def __init__(
        self,
        base: Base,
        reglages: Reglages,
        notificateur: Notificateur,
        horloge: Callable[[], float] = time.time,
    ) -> None:
        self.base = base
        self.r = reglages["alertes"]
        self.notificateur = notificateur
        self.horloge = horloge

    # --- sourdine ----------------------------------------------------------------------------------------------------

    def sourdine(self, duree_s: float, maintenant: float | None = None) -> float | None:
        """Met les alertes en sourdine pour `duree_s` secondes (0 : la lève). Renvoie la fin, ou None."""
        maintenant = self.horloge() if maintenant is None else maintenant
        if duree_s <= 0:
            self.base.effacer_meta("sourdine_jusqua")
            self.base.noter_evenement(maintenant, "tableau", "sourdine", "info", "Sourdine levée")
            return None
        fin = maintenant + duree_s
        self.base.ecrire_meta("sourdine_jusqua", str(fin))
        texte = f"Alertes en sourdine jusqu'à {textes.heure(fin)}"
        self.base.noter_evenement(maintenant, "tableau", "sourdine", "info", texte)
        return fin

    def sourdine_jusqua(self, maintenant: float | None = None) -> float | None:
        maintenant = self.horloge() if maintenant is None else maintenant
        brut = self.base.lire_meta("sourdine_jusqua")
        try:
            fin = float(brut) if brut else None
        except ValueError:
            fin = None
        return fin if fin is not None and fin > maintenant else None

    # --- suivi des problèmes ---------------------------------------------------------------------------------------

    def suivre(
        self,
        problemes: Iterable[Probleme],
        observes: Iterable[str],
        maintenant: float,
        eteints: Iterable[str] = (),
        connus: Iterable[str] | None = None,
        noms: dict[str, str] | None = None,
    ) -> None:
        """Un tour : les problèmes vus maintenant, pour les modules observés à ce tour.

        `eteints` : modules passés à ⚪ (éteints, en pause, désinstallés) : leurs problèmes sont clos, avec un message
        seulement s'ils avaient été annoncés. `connus` : les modules du registre ; un problème d'un module qui n'y
        est plus est clos sans bruit. Un problème remplacé par un autre de sa famille (la boucle devenue arrêt, le
        budget passé de 80 % à 100 %) est clos sans message : le nouveau parle pour lui."""
        vus = {p.cle: p for p in problemes}
        familles_vues = {(p.module, famille(p.genre)) for p in vus.values() if famille(p.genre)}
        observes = set(observes) | set(eteints)
        eteints = set(eteints)
        connus = set(connus) if connus is not None else None
        noms = noms or {}
        with self.base.transaction():
            for p in vus.values():
                self._vu(p, maintenant)
            for r in self.base.db.execute("SELECT * FROM problemes WHERE resolu_le IS NULL").fetchall():
                if r["cle"] in vus:
                    continue
                notifie = r["notifie_le"] is not None
                if connus is not None and r["module"] not in connus:
                    self._clore(r, maintenant, silencieux=True, pourquoi="module retiré du registre")
                elif r["module"] in eteints:
                    nom = noms.get(r["module"], r["module"])
                    fin = f"⚪ {nom} est éteint, en pause ou désinstallé : l'alerte est close."
                    self._clore(r, maintenant, silencieux=not notifie, pourquoi="module éteint", resolution=fin)
                elif (r["module"], famille(r["genre"])) in familles_vues:
                    self._clore(r, maintenant, silencieux=True, pourquoi="remplacé par un autre problème")
                elif r["module"] in observes:
                    if r["absent_depuis"] is None:
                        self.base.db.execute(
                            "UPDATE problemes SET absent_depuis = ? WHERE cle = ?", (maintenant, r["cle"])
                        )
                    elif maintenant - float(r["absent_depuis"]) >= float(self.r["resolution_s"]):
                        self._clore(r, maintenant, silencieux=not notifie, pourquoi="réglé")

    def _vu(self, p: Probleme, maintenant: float) -> None:
        db = self.base.db
        r = db.execute("SELECT * FROM problemes WHERE cle = ?", (p.cle,)).fetchone()
        if r is None or (r["resolu_le"] is not None and (r["resolution_envoyee"] or r["notifie_le"] is None)):
            # Nouveau (ou revenu après une résolution annoncée) : une nouvelle histoire commence.
            db.execute(
                "INSERT INTO problemes (cle, module, genre, gravite, message, resolution, nuit_permise, ouvert_le, "
                "vu_le, observations, phrase) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?) ON CONFLICT(cle) DO UPDATE SET "
                "gravite = excluded.gravite, message = excluded.message, resolution = excluded.resolution, "
                "nuit_permise = excluded.nuit_permise, ouvert_le = excluded.ouvert_le, vu_le = excluded.vu_le, "
                "observations = 1, absent_depuis = NULL, notifie_le = NULL, rappel_le = NULL, resolu_le = NULL, "
                "resolution_envoyee = 0, confirme_le = NULL, phrase = excluded.phrase",
                (p.cle, p.module, p.genre, p.gravite, p.message, p.resolution, int(p.nuit_permise), maintenant,
                 maintenant, p.phrase or p.message),
            )  # fmt: skip
            return
        # Toujours là (ou revenu avant que sa résolution ait été annoncée : on ne dit rien, on continue).
        db.execute(
            "UPDATE problemes SET gravite = ?, message = ?, resolution = ?, nuit_permise = ?, vu_le = ?, "
            "observations = observations + 1, absent_depuis = NULL, resolu_le = NULL, phrase = ? WHERE cle = ?",
            (p.gravite, p.message, p.resolution, int(p.nuit_permise), maintenant, p.phrase or p.message, p.cle),
        )
        r = db.execute("SELECT * FROM problemes WHERE cle = ?", (p.cle,)).fetchone()
        if r["confirme_le"] is None and self._confirme(r, maintenant):
            db.execute("UPDATE problemes SET confirme_le = ? WHERE cle = ?", (maintenant, p.cle))
            db.execute(
                "INSERT INTO evenements (ts, module, genre, gravite, message, details) VALUES (?, ?, ?, ?, ?, ?)",
                (maintenant, p.module, p.genre, p.gravite, p.message, p.cle),
            )

    def _confirme(self, r: sqlite3.Row, maintenant: float) -> bool:
        return int(r["observations"]) >= 2 and maintenant - float(r["ouvert_le"]) >= float(self.r["confirmation_s"])

    def _clore(
        self, r: sqlite3.Row, maintenant: float, silencieux: bool, pourquoi: str, resolution: str | None = None
    ) -> None:
        self.base.db.execute(
            "UPDATE problemes SET resolu_le = ?, resolution_envoyee = ?, resolution = ? WHERE cle = ?",
            (maintenant, 1 if silencieux else 0, resolution or r["resolution"], r["cle"]),
        )
        if r["confirme_le"] is not None:
            message = r["resolution"] if pourquoi == "réglé" else f"Clos ({pourquoi}) : {r['phrase'] or r['message']}"
            self.base.db.execute(
                "INSERT INTO evenements (ts, module, genre, gravite, message, details) "
                "VALUES (?, ?, 'resolution', 'info', ?, ?)",
                (maintenant, r["module"], message, r["cle"]),
            )

    def accepter(self, module: str, maintenant: float | None = None) -> None:
        """Tu as validé le code changé (« C'était moi ») : l'alerte d'intégrité est close, sans message."""
        maintenant = self.horloge() if maintenant is None else maintenant
        self.base.executer(
            "UPDATE problemes SET resolu_le = ?, resolution_envoyee = 1 WHERE cle = ? AND resolu_le IS NULL",
            (maintenant, f"{module}:integrite"),
        )

    def ajouter_info(self, cle: str, texte: str, maintenant: float) -> None:
        """Une information à faire partir avec les règles des alertes (le rapport de la semaine), une seule fois."""
        infos = self._infos()
        if cle in self._infos_parties() or any(i["cle"] == cle for i in infos):
            return
        infos.append({"cle": cle, "texte": texte, "depuis": maintenant})
        self.base.ecrire_meta("infos_en_attente", json.dumps(infos, ensure_ascii=False))

    def _infos(self) -> list[dict[str, Any]]:
        try:
            infos = json.loads(self.base.lire_meta("infos_en_attente") or "[]")
            return [i for i in infos if isinstance(i, dict) and "cle" in i and "texte" in i]
        except ValueError:
            return []

    def _infos_parties(self) -> list[str]:
        try:
            return [str(c) for c in json.loads(self.base.lire_meta("infos_parties") or "[]")][-50:]
        except ValueError:
            return []

    # --- décider et envoyer ------------------------------------------------------------------------------------------

    def candidats(self, maintenant: float) -> list[Element]:
        """Tout ce qui pourrait partir maintenant si rien ne le retenait."""
        elements: list[Element] = []
        rappel_s = float(self.r["rappel_heures"]) * 3600
        confirmation_s = float(self.r["confirmation_s"])
        for r in self.base.lignes("SELECT * FROM problemes ORDER BY ouvert_le"):
            if r["resolu_le"] is None and r["notifie_le"] is None and self._confirme(r, maintenant):
                elements.append(
                    Element("alerte", r["cle"], r["message"], r["gravite"], bool(r["nuit_permise"]),
                            float(r["ouvert_le"]) + confirmation_s)
                )  # fmt: skip
            elif r["resolu_le"] is None and r["notifie_le"] is not None:
                dernier = float(r["rappel_le"] or r["notifie_le"])
                if maintenant - dernier >= rappel_s:
                    depuis = textes.duree(maintenant - float(r["ouvert_le"]))
                    elements.append(
                        Element("rappel", r["cle"], f"Toujours en cours depuis {depuis} : {r['message']}",
                                r["gravite"], bool(r["nuit_permise"]), dernier + rappel_s)
                    )  # fmt: skip
            elif r["resolu_le"] is not None and r["notifie_le"] is not None and not r["resolution_envoyee"]:
                elements.append(Element("resolution", r["cle"], r["resolution"], "info", False, float(r["resolu_le"])))
        for i in self._infos():
            elements.append(Element("info", str(i["cle"]), str(i["texte"]), "info", False, float(i.get("depuis", 0))))
        return sorted(elements, key=lambda e: e.ordre)

    def en_silence(self, maintenant: float) -> bool:
        heure = time.localtime(maintenant).tm_hour
        debut, fin = int(self.r["silence_debut"]), int(self.r["silence_fin"])
        if debut == fin:
            return False
        return debut <= heure or heure < fin if debut > fin else debut <= heure < fin

    def envoyees_aujourdhui(self, maintenant: float) -> int:
        return int(
            self.base.valeur(
                "SELECT COUNT(*) FROM notifications WHERE envoyee = 1 AND ts >= ?",
                (planif.debut_du_jour(maintenant),),
                0,
            )
        )

    def retenue(self, maintenant: float) -> str | None:
        """Pourquoi rien ne part en ce moment (pour la page et `tableau etat`), ou None."""
        fin = self.sourdine_jusqua(maintenant)
        if fin is not None:
            return f"en sourdine jusqu'à {textes.heure(fin)}"
        if self.envoyees_aujourdhui(maintenant) >= int(self.r["max_par_jour"]):
            return f"{self.r['max_par_jour']} notifications aujourd'hui : la suite attend demain"
        if self.en_silence(maintenant):
            return f"silence de nuit jusqu'à {int(self.r['silence_fin'])}h"
        reveil = planif.dernier_reveil(self.base)
        if reveil is not None and maintenant - reveil < float(self.r["reveil_grace_s"]):
            return "le Mac vient de se réveiller : on laisse tout se remettre en route"
        return None

    def choisir(self, maintenant: float) -> list[Element]:
        """Ce qui part à ce tour (une seule notification), selon la sourdine, le quota, la nuit et le réveil."""
        candidats = self.candidats(maintenant)
        if not candidats or self.sourdine_jusqua(maintenant) is not None:
            return []
        if self.envoyees_aujourdhui(maintenant) >= int(self.r["max_par_jour"]):
            return []
        reveil = planif.dernier_reveil(self.base)
        if reveil is not None and maintenant - reveil < float(self.r["reveil_grace_s"]):
            candidats = [e for e in candidats if e.genre != "alerte"]
        if self.en_silence(maintenant):
            candidats = [e for e in candidats if e.nuit_permise and e.genre in ("alerte", "rappel")]
        if not candidats:
            return []
        # Regroupement : ce qui est sur le point d'être confirmé ou réglé part avec le reste, sans trop tarder.
        plus_ancien = min(e.depuis for e in candidats)
        if maintenant - plus_ancien < float(self.r["regroupement_s"]) and self._bientot_confirme(maintenant):
            return []
        return candidats

    def _bientot_confirme(self, maintenant: float) -> bool:
        """Un problème sur le point d'être confirmé, ou un problème annoncé sur le point d'être réglé."""
        confirmation = self.base.valeur(
            "SELECT COUNT(*) FROM problemes WHERE resolu_le IS NULL AND notifie_le IS NULL AND confirme_le IS NULL "
            "AND ouvert_le > ?",
            (maintenant - float(self.r["confirmation_s"]) - 1,),
            0,
        )
        resolution = self.base.valeur(
            "SELECT COUNT(*) FROM problemes WHERE resolu_le IS NULL AND notifie_le IS NOT NULL "
            "AND absent_depuis IS NOT NULL"
        )
        return bool(confirmation or resolution)

    @staticmethod
    def composer(elements: list[Element]) -> tuple[str, str]:
        titre = TITRE if len(elements) == 1 else f"{TITRE} : {len(elements)} points"
        lignes = [e.texte for e in elements[:LIGNES_MAX]]
        reste = len(elements) - LIGNES_MAX
        if reste > 0:
            lignes.append(f"… et {textes.pluriel(reste, 'autre')} : ouvre le tableau de bord.")
        return titre, "\n".join(lignes)

    def tour(self, maintenant: float | None = None) -> Envoi | None:
        """Envoie (au plus) une notification. Les problèmes ont été suivis juste avant (`suivre`)."""
        maintenant = self.horloge() if maintenant is None else maintenant
        elements = self.choisir(maintenant)
        if not elements:
            return None
        titre, texte = self.composer(elements)
        ok, motif = self.notificateur.envoyer(titre, texte)
        cles = [e.cle for e in elements]
        with self.base.transaction():
            db = self.base.db
            db.execute(
                "INSERT INTO notifications (ts, titre, texte, cles, envoyee, motif) VALUES (?, ?, ?, ?, ?, ?)",
                (maintenant, titre, texte, json.dumps(cles, ensure_ascii=False), int(ok), motif),
            )
            # Même en cas d'échec, on ne réessaie pas en boucle : la page et le journal les montrent.
            for e in elements:
                if e.genre == "alerte":
                    db.execute("UPDATE problemes SET notifie_le = ? WHERE cle = ?", (maintenant, e.cle))
                elif e.genre == "rappel":
                    db.execute("UPDATE problemes SET rappel_le = ? WHERE cle = ?", (maintenant, e.cle))
                elif e.genre == "resolution":
                    db.execute("UPDATE problemes SET resolution_envoyee = 1 WHERE cle = ?", (e.cle,))
            infos = [e.cle for e in elements if e.genre == "info"]
            if infos:
                restantes = [i for i in self._infos() if i["cle"] not in infos]
                db.execute(
                    "INSERT INTO meta (cle, valeur) VALUES ('infos_en_attente', ?) "
                    "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
                    (json.dumps(restantes, ensure_ascii=False),),
                )
                parties = (self._infos_parties() + infos)[-50:]
                db.execute(
                    "INSERT INTO meta (cle, valeur) VALUES ('infos_parties', ?) "
                    "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
                    (json.dumps(parties, ensure_ascii=False),),
                )
            details = "" if ok else f"non affichée : {motif}"
            db.execute(
                "INSERT INTO evenements (ts, module, genre, gravite, message, details) "
                "VALUES (?, 'tableau', 'notification', 'info', ?, ?)",
                (maintenant, texte.replace("\n", " · "), details),
            )
        return Envoi(titre, texte, elements, ok, motif)

    def traiter(
        self, etats: Iterable[EtatModule], maintenant: float, connus: Iterable[str] | None = None
    ) -> Envoi | None:
        """Le tour complet depuis les états des modules : suivre, puis envoyer."""
        etats = list(etats)
        problemes = [p for e in etats for p in e.problemes]
        eteints = [e.id for e in etats if e.pastille == Pastille.GRIS]
        observes = [e.id for e in etats if e.pastille != Pastille.GRIS]
        noms = {e.id: e.nom for e in etats}
        self.suivre(problemes, observes, maintenant, eteints=eteints, connus=connus, noms=noms)
        return self.tour(maintenant)

    # --- lecture (page, CLI) -----------------------------------------------------------------------------------------

    def ouverts(self) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.base.lignes(
                "SELECT cle, module, genre, gravite, message, phrase, ouvert_le, notifie_le, rappel_le, confirme_le "
                "FROM problemes WHERE resolu_le IS NULL ORDER BY gravite = 'grave' DESC, ouvert_le"
            )
        ]

    def dernieres_notifications(self, limite: int = 20) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self.base.lignes(
                "SELECT ts, titre, texte, envoyee, motif FROM notifications ORDER BY ts DESC, id DESC LIMIT ?",
                (limite,),
            )
        ]
