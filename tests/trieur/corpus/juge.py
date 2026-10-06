"""Le juge du corpus (§10.1) : chaque document est extrait et classé sans Claude, puis comparé à verite.json.

    python -m tests.trieur.corpus.juge DOSSIER_DU_CORPUS [-v]

Règles de comptage (D-14) :
- type : juste si le type final est le bon. « À vérifier » compte faux, sauf pour un document « autre » (rien à
  reconnaître) et pour un piège qui l'accepte (santé illisible) ;
- date, montant : justes s'ils sont égaux à la vérité, absence comprise (un relevé n'a pas de montant) ;
- garantie : les dates de fin trouvées = celles attendues, pour chaque achat qui en a ; une garantie sur un
  document qui n'en a pas est une « fausse garantie » ;
- pièges : photo → Pictures, PDF protégé / abîmé / vide → À vérifier.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modules.trieur import classement as cl
from modules.trieur import config
from modules.trieur.classement import emetteurs
from modules.trieur.extraction import extraire, ocr

IDENTITE = {"nom": "Atelier Démo", "siret": "123 456 789 00012"}  # la micro-entreprise du corpus (generer.py)


@dataclass
class Bilan:
    total: Counter[str] = field(default_factory=Counter)
    justes: Counter[str] = field(default_factory=Counter)
    erreurs: list[str] = field(default_factory=list)
    durees: dict[str, list[float]] = field(default_factory=dict)

    def taux(self, cle: str) -> float:
        return 100.0 * self.justes[cle] / self.total[cle] if self.total[cle] else 100.0

    def compter(self, cle: str, juste: bool, message: str = "") -> None:
        self.total[cle] += 1
        self.justes[cle] += bool(juste)
        if not juste and message:
            self.erreurs.append(f"{cle:12} {message}")

    def tableau(self) -> str:
        lignes = [f"{'critère':16} {'justes':>9} {'taux':>7}"]
        for cle in ("type_texte", "type_image", "date", "montant", "emetteur", "garantie", "retractation", "pieges"):
            if self.total[cle]:
                lignes.append(f"{cle:16} {self.justes[cle]:>4}/{self.total[cle]:<4} {self.taux(cle):6.1f} %")
        lignes.append(f"{'fausse_garantie':16} {self.total['fausse_garantie']:>4}")
        return "\n".join(lignes)


def reglages_du_juge(racine: Path) -> dict[str, Any]:
    return config.pour_le_bac_a_sable(racine, {"identite": IDENTITE})


def _classer(chemin: Path, moteur: ocr.Moteur | None, travail: Path, reglages: dict[str, Any], note: str | None,
             bilan: Bilan, support: str) -> tuple[str, cl.Classement | None, Any]:  # fmt: skip
    e = extraire(chemin, moteur, travail)
    bilan.durees.setdefault(support, []).append(e.duree_s)
    c = cl.classer(e.texte, reglages, note=note) if e.texte.strip() else None
    return cl.issue(c, e.nature, e.mots, e.erreur, reglages), c, e


def juger(dossier: Path, moteur: ocr.Moteur | None, travail: Path, reglages: dict[str, Any] | None = None) -> Bilan:
    reglages = reglages or reglages_du_juge(travail / "bac")
    verites = json.loads((dossier / "verite.json").read_text(encoding="utf-8"))
    pieces: dict[str, tuple[str, cl.Classement | None]] = {}
    bilan = Bilan()
    for v in verites:
        nom, support = v["fichier"], v["support"]
        if v["issue"] == "doublon":
            continue  # le même fichier : la file d'attente le reconnaît à son empreinte (P4)
        if support == "piece_jointe":
            resultat, c = pieces.get(nom, ("absente", None))
        else:
            chemin = dossier / nom
            if support == "fantome":  # le vrai fichier, une fois téléchargé par iCloud
                chemin = dossier / ".sources" / nom.removeprefix(".").removesuffix(".icloud")
            resultat, c, e = _classer(chemin, moteur, travail, reglages, v.get("note"), bilan, support)
            for nom_pj, contenu in e.pieces_jointes:
                pj = travail / "pieces" / nom_pj
                pj.parent.mkdir(parents=True, exist_ok=True)
                pj.write_bytes(contenu)
                r_pj, c_pj, _ = _classer(pj, moteur, travail, reglages, None, bilan, "piece_jointe")
                pieces[nom_pj] = (r_pj, c_pj)
        _comparer(v, resultat, c, bilan)
    return bilan


def _comparer(v: dict[str, Any], resultat: str, c: cl.Classement | None, bilan: Bilan) -> None:
    nom = v["fichier"]
    if v["type"] is None:  # un piège : photo, PDF protégé, abîmé, vide, courriel
        attendu = [v["issue"]] + v.get("accepte", [])
        bilan.compter("pieges", resultat in attendu, f"{nom} : attendu {v['issue']}, obtenu {resultat}")
        return
    type_final = c.type if (c is not None and resultat == "classe") else resultat
    juste = type_final == v["type"] or (v["type"] == "autre" and resultat == "a_verifier")
    juste = juste or resultat in v.get("accepte", [])
    groupe = "type_texte" if v["support"] == "pdf_texte" else "type_image"
    detail = f"({c.type} {c.confiance:.2f} {c.scores[:3]})" if c else ""
    bilan.compter(groupe, juste, f"{nom} [{v['support']}] : attendu {v['type']}, obtenu {type_final} {detail}")
    if resultat in v.get("accepte", []):
        return  # le piège illisible : à vérifier, sans date ni montant
    date = c.date.isoformat() if c and c.date else None
    bilan.compter("date", date == v["date"], f"{nom} {v['type']} : attendu {v['date']}, obtenu {date}")
    montant = f"{c.montant:.2f}" if c and c.montant is not None else None
    bilan.compter("montant", montant == v["montant"], f"{nom} {v['type']} : attendu {v['montant']}, obtenu {montant}")
    trouve = c.emetteur if c else None
    attendu_e = v["emetteur"] or ""
    e_juste = (trouve is None and not attendu_e) or (
        trouve is not None
        and (
            emetteurs.cle(trouve) == emetteurs.cle(attendu_e)
            or (c is not None and c.emetteur_connu and emetteurs.cle(attendu_e).startswith(emetteurs.cle(trouve)))
        )
    )
    bilan.compter("emetteur", e_juste, f"{nom} {v['type']} : attendu {attendu_e}, obtenu {trouve}")
    attendues = sorted(g["fin"] for g in v["garanties"])
    vues = sorted(g.fin.isoformat() for g in c.garanties) if c else []
    if attendues:
        bilan.compter("garantie", attendues == vues, f"{nom} : attendu {attendues}, obtenu {vues}")
    elif vues:
        bilan.total["fausse_garantie"] += 1
        bilan.erreurs.append(f"{'fausse_gar.':12} {nom} {v['type']} : {vues}")
    retractation = c.retractation.isoformat() if c and c.retractation else None
    if v.get("retractation") or retractation:
        bilan.compter("retractation", retractation == v.get("retractation"),
                      f"{nom} : attendu {v.get('retractation')}, obtenu {retractation}")  # fmt: skip


def moteur_des_tests() -> ocr.Moteur | None:
    """Le meilleur moteur d'ici (Vision sur le Mac, RapidOCR dans le conteneur), avec un cache sur disque."""
    import os

    moteur = ocr.choisir()
    cache = os.getenv("TRIEUR_CACHE_OCR") or str(Path(__file__).resolve().parents[1] / ".cache-ocr")
    return ocr.AvecCache(moteur, Path(cache)) if moteur is not None else None


def main(argv: list[str]) -> int:
    dossier = Path(argv[0])
    travail = Path(argv[1]) if len(argv) > 1 and not argv[1].startswith("-") else dossier.parent / "travail-juge"
    shutil.rmtree(travail, ignore_errors=True)
    bilan = juger(dossier, moteur_des_tests(), travail)
    print(bilan.tableau())
    if "-v" in argv:
        print("\n".join(sorted(bilan.erreurs)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
