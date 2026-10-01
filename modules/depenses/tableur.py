"""Ton tableur de dépenses (donnees/depenses/depenses.csv) : une ligne par reçu, à la française
(« ; » entre les colonnes, « 12,50 » pour les montants), il s'ouvre tel quel dans Numbers ou Excel.

L'Assistant AJOUTE des lignes à la fin, il ne modifie ni n'efface jamais celles qui existent :
tu peux corriger une ligne à la main dans le fichier.
"""

import csv
import fcntl
import io
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime

from modules.depenses import parametres as p


@dataclass
class Depense:
    date: date
    commercant: str
    montant: float  # TTC, en euros
    tva: float
    categorie: str
    paiement: str
    date_lue: bool = True  # False : pas de date sur le reçu, c'est celle du jour

    def decrire(self) -> str:
        return (f"{euros(self.montant)} · {self.commercant} · {self.categorie} · {self.date:%d/%m/%Y}"
                + ("" if self.date_lue else " (date du jour : pas de date lue sur le reçu)"))


def euros(montant: float) -> str:
    return f"{montant:,.2f} €".replace(",", " ").replace(".", ",")


def _nombre(texte: str) -> float | None:
    t = (texte or "").replace("€", "").replace("\xa0", "").replace(" ", "").strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")  # « 1.234,50 » ou « 12,50 »
    try:
        return float(t)
    except ValueError:
        return None


@contextmanager
def verrou():
    """Le module en fond et l'icône n'écrivent jamais en même temps."""
    p.DOSSIER.mkdir(parents=True, exist_ok=True)
    with open(p.DOSSIER / ".verrou", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def lire() -> list[dict]:
    """Les lignes du tableur, même s'il a été réenregistré par Excel (séparateur « , » ou « ; »)."""
    if not p.TABLEUR.exists():
        return []
    texte = p.TABLEUR.read_text(encoding="utf-8-sig", errors="replace")
    separateur = ";" if texte.split("\n", 1)[0].count(";") >= texte.split("\n", 1)[0].count(",") else ","
    lignes = []
    for l in csv.reader(io.StringIO(texte), delimiter=separateur):
        if len(l) < 5 or l[0] == p.COLONNES[0]:
            continue
        try:
            jour = datetime.strptime(l[0].strip(), "%d/%m/%Y").date()
        except ValueError:
            continue  # une ligne que tu as écrite autrement est ignorée dans les totaux (jamais effacée)
        montant = _nombre(l[2])
        if montant is not None:
            lignes.append({"date": jour, "commercant": l[1], "montant": montant, "categorie": l[4]})
    return lignes


def deja_la(d: Depense) -> bool:
    """Même jour, même montant, même commerçant : sûrement le même reçu (photographié deux fois)."""
    return any(x["date"] == d.date and abs(x["montant"] - d.montant) < 0.005
               and x["commercant"].strip().lower() == d.commercant.strip().lower() for x in lire())


def ajouter(d: Depense, photo: str) -> None:
    nouveau = not p.TABLEUR.exists()
    with open(p.TABLEUR, "a", encoding="utf-8-sig" if nouveau else "utf-8", newline="") as f:
        if nouveau:
            os.chmod(p.TABLEUR, 0o600)
        ecrivain = csv.writer(f, delimiter=";")
        if nouveau:
            ecrivain.writerow(p.COLONNES)
        ecrivain.writerow([f"{d.date:%d/%m/%Y}", d.commercant, f"{d.montant:.2f}".replace(".", ","),
                           f"{d.tva:.2f}".replace(".", ","), d.categorie, d.paiement, photo,
                           f"{datetime.now():%d/%m/%Y %H:%M}"])


def bilan(mois: str | None = None) -> dict:
    """{mois, total, nombre, par_categorie: [(catégorie, total), …]} pour un mois « AAAA-MM »."""
    mois = mois or f"{date.today():%Y-%m}"
    du_mois = [x for x in lire() if f"{x['date']:%Y-%m}" == mois]
    totaux: dict[str, float] = {}
    for x in du_mois:
        totaux[x["categorie"] or "Autre"] = totaux.get(x["categorie"] or "Autre", 0) + x["montant"]
    return {"mois": mois, "total": sum(x["montant"] for x in du_mois), "nombre": len(du_mois),
            "par_categorie": sorted(totaux.items(), key=lambda c: -c[1])}


def texte_bilan(b: dict) -> str:
    if not b["nombre"]:
        return f"Aucune dépense enregistrée pour {b['mois']}."
    lignes = [f"Total {b['mois']} : {euros(b['total'])} ({b['nombre']} reçu(s))"]
    lignes += [f"   {categorie} : {euros(total)}" for categorie, total in b["par_categorie"]]
    return "\n".join(lignes)
