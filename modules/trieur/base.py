"""La base du Trieur (SQLite, dans donnees/trieur/trieur.db) : la file d'attente, le journal des actions (pour
annuler), ce qui a été appris de tes corrections, le coffre à garanties et les dépenses de Claude.

La file est idempotente : un même fichier ajouté deux fois n'est qu'un élément. Un élément est « pris » par une
seule boucle à la fois (mise à jour conditionnelle), même si le démon et une commande tournent ensemble.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS elements (
    id INTEGER PRIMARY KEY,
    chemin TEXT NOT NULL,          -- là où le fichier a été trouvé
    nom TEXT NOT NULL,             -- son nom d'origine
    source TEXT NOT NULL,          -- boite, a_trier, finder, cli, api, telechargements, courriel
    note TEXT,
    parent INTEGER,                -- la pièce jointe d'un courriel : l'élément du courriel
    empreinte TEXT,                -- SHA-256 du contenu
    taille INTEGER,
    etat TEXT NOT NULL,            -- en_attente, en_cours, classe, a_verifier, photos, doublon, ignore, erreur, annule
    ajoute REAL NOT NULL,
    traite REAL,
    essais INTEGER NOT NULL DEFAULT 0,
    erreur TEXT,
    type TEXT, confiance REAL, emetteur TEXT, date TEXT, montant TEXT, par TEXT,
    destination TEXT,              -- le fichier rangé
    infos TEXT                     -- JSON : numéro, détail, raisons, original archivé…
);
CREATE INDEX IF NOT EXISTS elements_etat ON elements(etat);
CREATE INDEX IF NOT EXISTS elements_empreinte ON elements(empreinte);
CREATE INDEX IF NOT EXISTS elements_destination ON elements(destination);
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY,
    element INTEGER NOT NULL,
    quand REAL NOT NULL,
    genre TEXT NOT NULL,           -- range, archive, cree, supprime_source, alias, rappel, tag
    source TEXT, cible TEXT, empreinte TEXT,
    defaite REAL                   -- quand l'action a été annulée
);
CREATE INDEX IF NOT EXISTS actions_element ON actions(element);
CREATE TABLE IF NOT EXISTS appris (
    cle TEXT NOT NULL, type TEXT NOT NULL, points REAL NOT NULL, fois INTEGER NOT NULL DEFAULT 1, quand REAL,
    PRIMARY KEY (cle, type)
);
CREATE TABLE IF NOT EXISTS garanties (
    id INTEGER PRIMARY KEY,
    element INTEGER,               -- la facture (vide : une garantie saisie à la main)
    produit TEXT NOT NULL, emetteur TEXT, prix TEXT,
    achat TEXT NOT NULL, fin TEXT NOT NULL, mois INTEGER NOT NULL, source TEXT NOT NULL,
    facture TEXT,                  -- le chemin de la facture rangée
    alias TEXT,                    -- l'alias dans Garanties/
    rappels TEXT,                  -- JSON : les rappels créés dans l'app Rappels
    retractation TEXT,             -- la date du rappel de rétractation (achat en ligne)
    cree REAL NOT NULL, supprimee REAL
);
CREATE TABLE IF NOT EXISTS meta (cle TEXT PRIMARY KEY, valeur TEXT);
CREATE TABLE IF NOT EXISTS depenses_ia (
    id INTEGER PRIMARY KEY, quand REAL NOT NULL, mois TEXT NOT NULL, element INTEGER,
    entree INTEGER, sortie INTEGER, cout_usd REAL NOT NULL, resultat TEXT
);
"""
FINIS = ("classe", "a_verifier", "photos")


@dataclass
class Element:
    id: int
    chemin: str
    nom: str
    source: str
    note: str | None
    parent: int | None
    empreinte: str | None
    taille: int | None
    etat: str
    ajoute: float
    traite: float | None
    essais: int
    erreur: str | None
    type: str | None
    confiance: float | None
    emetteur: str | None
    date: str | None
    montant: str | None
    par: str | None
    destination: str | None
    infos: str | None

    @property
    def details(self) -> dict[str, Any]:
        try:
            return dict(json.loads(self.infos or "{}"))
        except ValueError:
            return {}


class Base:
    def __init__(self, fichier: Path):
        fichier.parent.mkdir(parents=True, exist_ok=True)
        self.fichier = fichier
        self.verrou = threading.RLock()
        self.db = sqlite3.connect(fichier, timeout=15, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def fermer(self) -> None:
        with self.verrou:
            self.db.close()

    def _x(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        with self.verrou:
            return self.db.execute(sql, params)

    # --- la file ---------------------------------------------------------------------------------------------------

    def ajouter(self, chemin: Path, source: str, note: str | None = None, parent: int | None = None) -> int:
        """L'identifiant de l'élément : le même si ce fichier attend déjà (ou est en cours)."""
        with self.verrou:
            deja = self.db.execute("SELECT id FROM elements WHERE chemin = ? AND etat IN ('en_attente', 'en_cours')",
                                   (str(chemin),)).fetchone()  # fmt: skip
            if deja:
                if note:
                    self.db.execute("UPDATE elements SET note = ? WHERE id = ?", (note, deja["id"]))
                return int(deja["id"])
            c = self.db.execute("INSERT INTO elements (chemin, nom, source, note, parent, etat, ajoute) "
                                "VALUES (?, ?, ?, ?, ?, 'en_attente', ?)",
                                (str(chemin), chemin.name, source, note, parent, time.time()))  # fmt: skip
            return int(c.lastrowid or 0)

    def prendre(self, element: int) -> bool:
        """Réserve l'élément pour le traiter ; False si quelqu'un d'autre l'a déjà pris."""
        c = self._x("UPDATE elements SET etat = 'en_cours', essais = essais + 1 WHERE id = ? AND etat = 'en_attente'",
                    (element,))  # fmt: skip
        return c.rowcount == 1

    def en_attente(self, limite: int = 50) -> list[Element]:
        lignes = self._x("SELECT * FROM elements WHERE etat = 'en_attente' ORDER BY id LIMIT ?", (limite,)).fetchall()
        return [Element(**dict(x)) for x in lignes]

    def relacher_les_interrompus(self) -> int:
        """Au démarrage : ce qui était « en cours » quand le Mac s'est éteint repart dans la file."""
        return self._x("UPDATE elements SET etat = 'en_attente' WHERE etat = 'en_cours'").rowcount

    def element(self, element: int) -> Element | None:
        x = self._x("SELECT * FROM elements WHERE id = ?", (element,)).fetchone()
        return Element(**dict(x)) if x else None

    def par_destination(self, chemin: Path) -> Element | None:
        x = self._x("SELECT * FROM elements WHERE destination = ? AND etat IN ('classe', 'a_verifier', 'photos') "
                    "ORDER BY id DESC LIMIT 1", (str(chemin),)).fetchone()  # fmt: skip
        return Element(**dict(x)) if x else None

    def doublon_de(self, empreinte: str, sauf: int) -> Element | None:
        x = self._x("SELECT * FROM elements WHERE empreinte = ? AND id != ? AND etat IN ('classe', 'a_verifier', "
                    "'photos') ORDER BY id LIMIT 1", (empreinte, sauf)).fetchone()  # fmt: skip
        return Element(**dict(x)) if x else None

    def annule_avec(self, empreinte: str) -> bool:
        x = self._x("SELECT 1 FROM elements WHERE empreinte = ? AND etat = 'annule' LIMIT 1", (empreinte,)).fetchone()
        return x is not None

    def mettre_a_jour(self, element: int, **valeurs: Any) -> None:
        if "infos" in valeurs and not isinstance(valeurs["infos"], str):
            valeurs["infos"] = json.dumps(valeurs["infos"], ensure_ascii=False, default=str)
        colonnes = ", ".join(f"{k} = ?" for k in valeurs)
        self._x(f"UPDATE elements SET {colonnes} WHERE id = ?", (*valeurs.values(), element))

    def derniers(self, limite: int = 20, etats: tuple[str, ...] | None = None) -> list[Element]:
        if etats:
            marques = ",".join("?" * len(etats))
            sql = f"SELECT * FROM elements WHERE etat IN ({marques}) ORDER BY COALESCE(traite, ajoute) DESC, id DESC"
            lignes = self._x(sql + " LIMIT ?", (*etats, limite)).fetchall()
        else:
            lignes = self._x("SELECT * FROM elements ORDER BY COALESCE(traite, ajoute) DESC, id DESC LIMIT ?",
                             (limite,)).fetchall()  # fmt: skip
        return [Element(**dict(x)) for x in lignes]

    def venus_de(self, source: str, etats: tuple[str, ...]) -> list[Element]:
        marques = ",".join("?" * len(etats))
        lignes = self._x(f"SELECT * FROM elements WHERE source = ? AND etat IN ({marques}) ORDER BY id",
                         (source, *etats)).fetchall()  # fmt: skip
        return [Element(**dict(x)) for x in lignes]

    def oublier(self, ids: list[int]) -> int:
        """Retire ces éléments de la base, sauf ceux qui ont une action au journal (un fichier qui a bougé reste
        suivi, pour pouvoir l'annuler)."""
        n = 0
        for i in ids:
            n += self._x("DELETE FROM elements WHERE id = ? AND NOT EXISTS (SELECT 1 FROM actions WHERE element = ?)",
                         (i, i)).rowcount  # fmt: skip
        return n

    def dedoublonner_erreurs(self) -> int:
        """Un fichier repris en boucle (avant D-59) a laissé une ligne d'erreur par passage : seule la dernière reste
        (jamais une ligne qui a une action au journal)."""
        return self._x("DELETE FROM elements WHERE etat = 'erreur' AND id NOT IN (SELECT MAX(id) FROM elements "
                       "WHERE etat = 'erreur' GROUP BY chemin) AND NOT EXISTS (SELECT 1 FROM actions "
                       "WHERE actions.element = elements.id)").rowcount  # fmt: skip

    def erreurs(self) -> list[Element]:
        return [Element(**dict(x)) for x in self._x("SELECT * FROM elements WHERE etat = 'erreur' ORDER BY id")]

    def compter(self) -> dict[str, int]:
        return {x["etat"]: int(x["n"]) for x in self._x("SELECT etat, COUNT(*) n FROM elements GROUP BY etat")}

    def deja_laisse(self, chemin: Path, taille: int) -> bool:
        """Ce fichier (même chemin, même taille) a déjà été examiné et laissé à sa place : pas assez sûr
        (Téléchargements), doublon, ou en erreur. Il n'est repris que s'il change."""
        sql = "SELECT 1 FROM elements WHERE chemin = ? AND taille = ? AND etat IN ('ignore', 'doublon', 'erreur')"
        x = self._x(sql + " LIMIT 1", (str(chemin), taille)).fetchone()
        return x is not None

    def lire_meta(self, cle: str) -> str | None:
        x = self._x("SELECT valeur FROM meta WHERE cle = ?", (cle,)).fetchone()
        return str(x["valeur"]) if x else None

    def ecrire_meta(self, cle: str, valeur: str) -> None:
        self._x("INSERT INTO meta (cle, valeur) VALUES (?, ?) ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
                (cle, valeur))  # fmt: skip

    # --- le journal des actions ------------------------------------------------------------------------------------

    def noter_action(self, element: int, genre: str, source: str | None = None, cible: str | None = None,
                     empreinte: str | None = None) -> int:  # fmt: skip
        c = self._x("INSERT INTO actions (element, quand, genre, source, cible, empreinte) VALUES (?, ?, ?, ?, ?, ?)",
                    (element, time.time(), genre, source, cible, empreinte))  # fmt: skip
        return int(c.lastrowid or 0)

    def actions(self, element: int, toutes: bool = False) -> list[sqlite3.Row]:
        sql = "SELECT * FROM actions WHERE element = ?" + ("" if toutes else " AND defaite IS NULL")
        return list(self._x(sql + " ORDER BY id", (element,)).fetchall())

    def defaire(self, action: int) -> None:
        self._x("UPDATE actions SET defaite = ? WHERE id = ?", (time.time(), action))

    # --- l'apprentissage -------------------------------------------------------------------------------------------

    def apprendre(self, cle: str, type_: str, points: float) -> None:
        self._x("INSERT INTO appris (cle, type, points, fois, quand) VALUES (?, ?, ?, 1, ?) ON CONFLICT(cle, type) DO "
                "UPDATE SET points = MIN(points + excluded.points, 20), fois = fois + 1, quand = excluded.quand",
                (cle, type_, points, time.time()))  # fmt: skip

    def appris(self) -> dict[str, dict[str, float]]:
        sortie: dict[str, dict[str, float]] = {}
        for x in self._x("SELECT cle, type, points FROM appris"):
            sortie.setdefault(x["cle"], {})[x["type"]] = float(x["points"])
        return sortie


def ouvrir(reglages: dict[str, Any]) -> Base:
    from modules.trieur import config

    return Base(config.dossier_donnees(reglages) / "trieur.db")
