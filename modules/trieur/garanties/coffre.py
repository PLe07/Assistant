"""Le coffre à garanties (§7) : une fiche par bien durable, un alias de la facture dans Classés/Garanties, deux
rappels dans l'app Rappels (30 et 7 jours avant la fin), et le rappel de rétractation d'un achat en ligne.

Tout ce qui est créé est noté dans le journal des actions : annuler ou corriger un document retire ses fiches,
ses alias et ses rappels. En mode test, les rappels vont dans la liste « Trieur-TEST ».
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from core.journal import journal
from modules.trieur import config
from modules.trieur.base import Base
from modules.trieur.classement import Classement
from modules.trieur.classement.nommage import libre, propre
from modules.trieur.garanties.duree import ajouter_mois
from modules.trieur.systeme import Systeme

log = journal("trieur")
LISTE_TEST = "Trieur-TEST"


@dataclass
class Fiche:
    id: int
    element: int | None
    produit: str
    emetteur: str | None
    prix: str | None
    achat: date
    fin: date
    mois: int
    source: str
    facture: str | None
    alias: str | None
    rappels: list[str]
    retractation: date | None

    def jours_restants(self, aujourd_hui: date | None = None) -> int:
        return (self.fin - (aujourd_hui or date.today())).days

    def etat(self, aujourd_hui: date | None = None) -> str:
        j = self.jours_restants(aujourd_hui)
        return "expirée" if j < 0 else "bientôt" if j <= 30 else "active"


def _fiche(x: Any) -> Fiche:
    retractation = date.fromisoformat(x["retractation"]) if x["retractation"] else None
    return Fiche(x["id"], x["element"], x["produit"], x["emetteur"], x["prix"], date.fromisoformat(x["achat"]),
                 date.fromisoformat(x["fin"]), x["mois"], x["source"], x["facture"], x["alias"],
                 json.loads(x["rappels"] or "[]"), retractation)  # fmt: skip


class Coffre:
    def __init__(self, reglages: dict[str, Any], base: Base, systeme: Systeme):
        self.reglages, self.base, self.systeme = reglages, base, systeme

    @property
    def liste_rappels(self) -> str:
        return LISTE_TEST if self.reglages.get("mode_test") else str(self.reglages["garanties"]["liste_rappels"])

    def _heure(self, jour: date) -> datetime:
        h, m = (int(x) for x in str(self.reglages["garanties"]["heure_rappel"]).split(":"))
        return datetime(jour.year, jour.month, jour.day, h, m)

    # --- créer ------------------------------------------------------------------------------------------------------

    def enregistrer(self, element: int | None, c: Classement, facture: Path | None) -> list[int]:
        """Les fiches des garanties trouvées sur ce document (et le rappel de rétractation)."""
        ids = []
        retractation_faite = False
        for g in c.garanties:
            retractation = c.retractation if (c.en_ligne and not retractation_faite) else None
            ids.append(self.creer(element, g.produit, c.emetteur, str(g.prix) if g.prix is not None else None, g.debut,
                                  g.fin, g.mois, g.source, facture, retractation))  # fmt: skip
            retractation_faite = retractation_faite or retractation is not None
        return ids

    def creer(self, element: int | None, produit: str, emetteur: str | None, prix: str | None, achat: date, fin: date,
              mois: int, source: str, facture: Path | None, retractation: date | None = None) -> int:  # fmt: skip
        c = self.base._x("INSERT INTO garanties (element, produit, emetteur, prix, achat, fin, mois, source, facture, "
                         "retractation, cree) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                         (element, produit, emetteur, prix, achat.isoformat(), fin.isoformat(), mois, source,
                          str(facture) if facture else None, retractation.isoformat() if retractation else None,
                          time.time()))  # fmt: skip
        fiche_id = int(c.lastrowid or 0)
        alias = self._alias(element, fiche_id, produit, emetteur, fin, facture)
        rappels = self._rappels(element, produit, emetteur, fin, facture, retractation)
        self.base._x("UPDATE garanties SET alias = ?, rappels = ? WHERE id = ?",
                     (str(alias) if alias else None, json.dumps(rappels), fiche_id))  # fmt: skip
        log.info("garantie : %s jusqu'au %s (%s)", produit, fin.isoformat(), source)
        return fiche_id

    def _alias(self, element: int | None, fiche: int, produit: str, emetteur: str | None, fin: date,
               facture: Path | None) -> Path | None:  # fmt: skip
        if facture is None or not facture.exists():
            return None
        dossier = config.chemin(self.reglages, "classes") / self.reglages["arborescence"]["garanties"]
        nom = f"{propre(produit, 50)}_{propre(emetteur or '', 25)}_fin-{fin.isoformat()}{facture.suffix}".replace(
            "__", "_"
        )
        alias = libre(dossier, nom)
        if not self.systeme.creer_alias(facture, alias):
            return None
        if element is not None:
            self.base.noter_action(element, "alias", str(facture), str(alias))
        return alias

    def _rappels(self, element: int | None, produit: str, emetteur: str | None, fin: date, facture: Path | None,
                 retractation: date | None) -> list[str]:  # fmt: skip
        maintenant = datetime.now()
        de = f" ({emetteur})" if emetteur else ""
        note = f"Facture : {facture.name}" if facture else ""
        a_creer = []
        for jours in self.reglages["garanties"]["rappels_jours_avant"]:
            quand = self._heure(fin - timedelta(days=int(jours)))
            a_creer.append((quand, f"Garantie : {produit}{de} — fin le {fin.strftime('%d/%m/%Y')}"))
        if retractation is not None:
            g = self.reglages["garanties"]
            dernier = retractation + timedelta(days=int(g["retractation_jours"]) - int(g["retractation_rappel_jours"]))
            titre = f"Rétractation : {produit}{de} — dernier jour le {dernier.strftime('%d/%m/%Y')}"
            a_creer.append((self._heure(retractation), titre))
        identifiants = []
        for quand, titre in a_creer:
            if quand <= maintenant:
                continue  # une échéance déjà passée (un vieux document) : pas de rappel
            identifiant = self.systeme.rappel_creer(self.liste_rappels, titre, quand, note)
            if identifiant:
                identifiants.append(identifiant)
                if element is not None:
                    self.base.noter_action(element, "rappel", self.liste_rappels, identifiant)
        return identifiants

    # --- lire, modifier, supprimer ----------------------------------------------------------------------------------

    def fiches(self, toutes: bool = False) -> list[Fiche]:
        sql = "SELECT * FROM garanties" + ("" if toutes else " WHERE supprimee IS NULL") + " ORDER BY fin, id"
        return [_fiche(x) for x in self.base._x(sql)]

    def fiche(self, fiche: int) -> Fiche | None:
        x = self.base._x("SELECT * FROM garanties WHERE id = ? AND supprimee IS NULL", (fiche,)).fetchone()
        return _fiche(x) if x else None

    def _retirer(self, f: Fiche) -> list[str]:
        faits = []
        for identifiant in f.rappels:
            if self.systeme.rappel_supprimer(self.liste_rappels, identifiant):
                faits.append(f"rappel retiré : {f.produit}")
        if f.alias and (Path(f.alias).is_symlink() or Path(f.alias).exists()):
            Path(f.alias).unlink()
            faits.append(f"alias retiré : {Path(f.alias).name}")
        self.base._x("UPDATE garanties SET supprimee = ? WHERE id = ?", (time.time(), f.id))
        return faits

    def oublier(self, element: int) -> list[str]:
        """Les fiches d'un document annulé ou corrigé disparaissent (avec leurs rappels et alias)."""
        lignes = self.base._x("SELECT * FROM garanties WHERE element = ? AND supprimee IS NULL", (element,))
        faits: list[str] = []
        for x in list(lignes):
            faits += self._retirer(_fiche(x))
        for a in self.base.actions(element):
            if a["genre"] in ("alias", "rappel"):
                self.base.defaire(a["id"])
        return faits

    def supprimer(self, fiche: int) -> list[str]:
        f = self.fiche(fiche)
        if f is None:
            raise KeyError(f"aucune garantie n°{fiche}")
        return self._retirer(f)

    def ajouter_a_la_main(self, produit: str, achat: date, mois: int | None = None, fin: date | None = None,
                          emetteur: str | None = None, prix: str | None = None,
                          facture: Path | None = None) -> int:  # fmt: skip
        """« trieur garantie ajouter » : un bien sans facture passée par le Trieur (ou une extension achetée à part)."""
        if fin is None:
            mois = mois or int(self.reglages["garanties"]["legale_neuf_mois"])
            fin = ajouter_mois(achat, mois)
        elif mois is None:
            mois = max(1, (fin.year - achat.year) * 12 + fin.month - achat.month)
        return self.creer(None, produit, emetteur, prix, achat, fin, int(mois), "manuelle", facture)

    def modifier(self, fiche: int, **champs: Any) -> int:
        """Change une fiche (produit, fin, mois…) : l'ancienne est retirée, une nouvelle est créée avec ses rappels."""
        f = self.fiche(fiche)
        if f is None:
            raise KeyError(f"aucune garantie n°{fiche}")
        connus = {"produit", "emetteur", "prix", "achat", "fin", "mois"}
        inconnus = set(champs) - connus
        if inconnus:
            raise ValueError(f"champ inconnu : {', '.join(sorted(inconnus))}")
        produit = str(champs.get("produit") or f.produit)
        emetteur = champs.get("emetteur") or f.emetteur
        prix = champs.get("prix") or f.prix
        achat: date = champs.get("achat") or f.achat
        mois = int(champs.get("mois") or f.mois)
        fin: date = champs.get("fin") or (ajouter_mois(achat, mois) if champs.get("mois") else f.fin)
        retractation = f.retractation if f.retractation and f.retractation >= date.today() else None
        self._retirer(f)
        facture = Path(f.facture) if f.facture else None
        return self.creer(f.element, produit, emetteur, prix, achat, fin, mois, "manuelle", facture, retractation)

    def echeances(self, jour: date) -> list[tuple[Fiche, int]]:
        """Les fiches dont la fin tombe dans 30 ou 7 jours exactement (la notification du matin)."""
        jours = {int(j) for j in self.reglages["garanties"]["rappels_jours_avant"]}
        return [(f, f.jours_restants(jour)) for f in self.fiches() if f.jours_restants(jour) in jours]
