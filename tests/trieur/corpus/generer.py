"""Le générateur du corpus (§10.1) : au moins 120 documents fictifs, avec leur vérité terrain dans verite.json.

    python -m tests.trieur.corpus.generer DOSSIER [--corpus 2]

Le corpus 1 sert à régler les règles. Le corpus 2 (generer2.py) apporte de nouveaux émetteurs et de nouvelles
mises en page, jamais vus pendant le réglage.
"""

from __future__ import annotations

import json
import random
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.trieur.corpus import rendu
from tests.trieur.corpus.contenu import FABRIQUES, Contexte
from tests.trieur.corpus.donnees import emetteurs, personne
from tests.trieur.corpus.modele import Doc, Verite

ENTREPRISE = {"nom": "Atelier Démo", "siret": "123 456 789 00012"}  # la micro-entreprise fictive des tests

# (type, nombre de documents, supports) : les supports sont distribués dans l'ordre, en boucle.
PLAN_1: list[tuple[str, int, list[str]]] = [
    ("facture_achat", 24, ["pdf_texte"] * 5 + ["scan_pdf", "pdf_texte", "scan_jpg"]),
    ("ticket_caisse", 12, ["photo_ticket", "photo_ticket", "pdf_texte", "heic", "photo_ticket", "photo_exif"]),
    ("facture_service", 8, ["pdf_texte", "pdf_texte", "pdf_texte", "scan_pdf", "pdf_texte", "pdf_texte", "pdf_texte", "scan_jpg"]),
    ("releve_bancaire", 5, ["pdf_texte", "pdf_texte", "scan_pdf", "pdf_texte", "pdf_texte"]),
    ("avis_imposition", 4, ["pdf_texte", "scan_jpg", "pdf_texte", "pdf_texte"]),
    ("quittance_loyer", 4, ["pdf_texte", "pdf_texte", "scan_jpg", "pdf_texte"]),
    ("bail_contrat", 4, ["pdf_texte", "pdf_texte", "scan_pdf", "pdf_texte"]),
    ("attestation", 6, ["pdf_texte", "pdf_texte", "pdf_texte", "scan_jpg", "pdf_texte", "pdf_texte"]),
    ("bulletin_paie", 4, ["pdf_texte", "scan_pdf", "pdf_texte", "pdf_texte"]),
    ("assurance", 4, ["pdf_texte"]),
    ("billet_transport", 5, ["pdf_texte", "pdf_texte", "heic", "pdf_texte", "pdf_texte"]),
    ("reservation", 4, ["pdf_texte"]),
    ("sante", 5, ["pdf_texte", "pdf_texte", "scan_jpg", "pdf_texte", "pdf_texte"]),
    ("identite", 4, ["scan_jpg", "scan_jpg", "heic", "photo_exif"]),
    ("devis", 4, ["pdf_texte", "scan_pdf", "pdf_texte", "pdf_texte"]),
    ("facture_emise", 3, ["pdf_texte"]),
    ("garantie_notice", 3, ["pdf_texte"]),
    ("courrier_admin", 4, ["pdf_texte", "scan_jpg", "pdf_texte", "pdf_texte"]),
    ("autre", 3, ["pdf_texte"]),
]  # fmt: skip
MISES_EN_PAGE_1 = ["classique", "moderne", "logo"]
NOMS = ["Scan_{n}.pdf", "document ({n}).pdf", "facture_{n}.pdf", "Téléchargement {n}.pdf", "PDF {n}.pdf",
        "releve {n}.pdf", "fichier-{n}.pdf"]  # fmt: skip


@dataclass
class Corpus:
    dossier: Path
    verites: list[Verite]

    def par_fichier(self) -> dict[str, Verite]:
        return {v.fichier: v for v in self.verites}


def _nom(r: random.Random, n: int, support: str) -> str:
    if support in ("scan_jpg", "photo_ticket", "photo_exif"):
        return f"IMG_{4000 + n}.JPG" if r.random() < 0.7 else f"Photo {n}.jpg"
    if support == "heic":
        return f"IMG_{4000 + n}.HEIC"
    return r.choice(NOMS).format(n=n)


def dessiner(doc: Doc, support: str, chemin: Path, r: random.Random, mise_en_page: str, travail: Path,
             force: float = 1.0) -> str:  # fmt: skip
    """Écrit le document au bon format ; renvoie le support réellement produit (heic → jpg si pas de HEIC)."""
    page = "lettre" if doc.lettre and mise_en_page in ("classique", "moderne") else mise_en_page
    pdf = travail / f"{chemin.stem}.source.pdf"
    rendu.pdf_texte(doc, pdf, page, r)
    if support == "pdf_texte":
        shutil.copyfile(pdf, chemin)
        return support
    if doc.ticket and support in ("photo_ticket", "heic", "photo_exif"):
        img = rendu.photo_ticket(pdf, r)
    else:
        img = rendu.degrader(rendu.page_en_image(pdf, dpi=150), r, force)
    if support == "scan_pdf":
        rendu.en_pdf_image(img, chemin)
    elif support == "heic":
        if not rendu.en_heic(img, chemin):
            img.save(chemin.with_suffix(".jpg"), "JPEG", quality=85)
            return "scan_jpg"
    elif support == "photo_exif":
        rendu.avec_orientation_exif(img, chemin)
    else:
        img.save(chemin, "JPEG", quality=82)
    return support


def _verite(fichier: str, support: str, valeurs: dict[str, Any], lot: str) -> Verite:
    return Verite(fichier=fichier, type=valeurs["type"], issue="classe", support=support, emetteur=valeurs.get("emetteur"),
                  date=valeurs.get("date"), montant=valeurs.get("montant"), garanties=valeurs.get("garanties", []),
                  retractation=valeurs.get("retractation"), sensible=valeurs.get("sensible", False), lot=lot)  # fmt: skip


def generer(dossier: Path, graine: int = 20261006) -> Corpus:
    """Le corpus principal (≥ 120 documents) dans « dossier », et verite.json."""
    dossier.mkdir(parents=True, exist_ok=True)
    travail = dossier / ".sources"
    travail.mkdir(exist_ok=True)
    r = random.Random(graine)
    c = Contexte(r, emetteurs(random.Random(graine + 1)), personne(r), ENTREPRISE)
    verites: list[Verite] = []
    n = 0
    sources: dict[str, Path] = {}
    for type_, nombre, supports in PLAN_1:
        fabrique, variantes = FABRIQUES[type_]
        for i in range(nombre):
            n += 1
            support = supports[i % len(supports)]
            doc, valeurs = fabrique(c, variantes[i % len(variantes)])
            nom = _nom(r, n, support)
            chemin = dossier / nom
            reel = dessiner(doc, support, chemin, r, MISES_EN_PAGE_1[n % len(MISES_EN_PAGE_1)], travail)
            if reel != support:
                nom = chemin.with_suffix(".jpg").name
            verites.append(_verite(nom, reel, valeurs, "corpus1"))
            sources[nom] = travail / f"{Path(nom).stem}.source.pdf"
    verites += _pieges(dossier, travail, r, c, verites, sources)
    _notes(verites)
    (dossier / "verite.json").write_text(json.dumps([v.vers_dict() for v in verites], ensure_ascii=False, indent=1),
                                         encoding="utf-8")  # fmt: skip
    return Corpus(dossier, verites)


def _notes(verites: list[Verite]) -> None:
    """Deux factures envoyées de l'iPhone avec une note « garantie 3 ans » : la note l'emporte (§7)."""
    from datetime import date

    from tests.trieur.corpus.modele import ajouter_mois

    avec = [v for v in verites if v.type == "facture_achat" and v.garanties and v.support == "pdf_texte"][:2]
    for v in avec:
        v.note = "garantie 3 ans"
        for g in v.garanties:
            g["fin"] = ajouter_mois(date.fromisoformat(v.date or ""), 36).isoformat()
            g["source"] = "note"
    autre = next(v for v in verites if v.type == "facture_service")
    autre.note = "ouvre-le"


def _pieges(dossier: Path, travail: Path, r: random.Random, c: Contexte, verites: list[Verite],
            sources: dict[str, Path]) -> list[Verite]:  # fmt: skip
    pieges: list[Verite] = []
    factures = [v for v in verites if v.type == "facture_achat" and v.support == "pdf_texte"]
    # Photos de vacances : vers Pictures.
    rendu.paysage(r).save(dossier / "IMG_5101.JPG", "JPEG", quality=85)
    pieges.append(Verite("IMG_5101.JPG", None, "photos", "piege", lot="piege:paysage"))
    if rendu.en_heic(rendu.paysage(r), dossier / "IMG_5102.HEIC"):
        pieges.append(Verite("IMG_5102.HEIC", None, "photos", "piege", lot="piege:paysage_heic"))
    # PDF protégé, corrompu, vide : à vérifier.
    rendu.pdf_protege(sources[factures[0].fichier], dossier / "facture_protegee.pdf")
    pieges.append(Verite("facture_protegee.pdf", None, "a_verifier", "piege", lot="piege:protege"))
    rendu.pdf_corrompu(sources[factures[1].fichier], dossier / "facture_abimee.pdf")
    pieges.append(Verite("facture_abimee.pdf", None, "a_verifier", "piege", lot="piege:corrompu"))
    (dossier / "vide.pdf").write_bytes(b"")
    pieges.append(Verite("vide.pdf", None, "a_verifier", "piege", lot="piege:vide"))
    # Un doublon exact d'une facture.
    original = factures[2]
    shutil.copyfile(dossier / original.fichier, dossier / "facture (copie).pdf")
    pieges.append(Verite("facture (copie).pdf", original.type, "doublon", "piege", emetteur=original.emetteur,
                         date=original.date, montant=original.montant, lot="piege:doublon"))  # fmt: skip
    # Un document de santé peu lisible : jamais chez Claude, classé en santé ou mis à vérifier.
    fabrique, _ = FABRIQUES["sante"]
    doc, valeurs = fabrique(c, "ameli")
    dessiner(doc, "scan_jpg", dossier / "IMG_5103.JPG", r, "classique", travail, force=2.3)
    v = _verite("IMG_5103.JPG", "scan_jpg", valeurs, "piege:sante_illisible")
    v.accepte = ["a_verifier"]
    pieges.append(v)
    # Deux factures qui donneraient le même nom : la seconde reçoit « -2 ».
    fabrique, _ = FABRIQUES["facture_achat"]
    etat = r.getstate()
    doc_a, val_a = fabrique(c, "neuf")
    r.setstate(etat)
    doc_b, val_b = fabrique(c, "neuf")
    doc_b.meta = [(k, v + "-B" if k == "Facture n°" else v) for k, v in doc_b.meta]
    for nom, doc, val in (("collision_a.pdf", doc_a, val_a), ("collision_b.pdf", doc_b, val_b)):
        dessiner(doc, "pdf_texte", dossier / nom, r, "classique", travail)
        pieges.append(_verite(nom, "pdf_texte", val, "piege:collision"))
    # Un nom avec un emoji.
    doc, val = fabrique(c, "mention_2ans")
    dessiner(doc, "pdf_texte", dossier / "Facture 🎧 casque.pdf", r, "moderne", travail)
    pieges.append(_verite("Facture 🎧 casque.pdf", "pdf_texte", val, "piege:emoji"))
    # Un fichier fantôme iCloud (.nom.pdf.icloud) : le vrai fichier arrive quand on le télécharge.
    doc, val = fabrique(c, "en_ligne")
    dessiner(doc, "pdf_texte", travail / "Facture-en-ligne.pdf", r, "classique", travail)
    (dossier / ".Facture-en-ligne.pdf.icloud").write_bytes(b"bplist00 fantome iCloud")
    v = _verite(".Facture-en-ligne.pdf.icloud", "fantome", val, "piege:fantome")
    pieges.append(v)
    # Un PDF de 300 pages : seules les 3 premières et la dernière sont lues.
    doc, val = FABRIQUES["facture_service"][0](c, "energie")
    dessiner(doc, "pdf_texte", travail / "p1.pdf", r, "classique", travail)
    rendu.pdf_300_pages(travail / "p1.pdf", dossier / "contrat-et-facture-300-pages.pdf")
    pieges.append(_verite("contrat-et-facture-300-pages.pdf", "pdf_texte", val, "piege:300_pages"))
    # Un courriel avec la facture en pièce jointe.
    doc, val = fabrique(c, "en_ligne")
    dessiner(doc, "pdf_texte", travail / "piece.pdf", r, "moderne", travail)
    rendu.courriel_avec_piece_jointe(travail / "piece.pdf", "Facture-commande.pdf", "factures@boutique.example",
                                     dossier / "Votre facture.eml")  # fmt: skip
    pieges.append(Verite("Votre facture.eml", None, "a_verifier", "eml", lot="piege:eml", accepte=["classe"]))
    pj = _verite("Facture-commande.pdf", "piece_jointe", val, "piege:eml_piece")
    pj.issue = "piece_jointe"
    pieges.append(pj)
    return pieges


def main(argv: list[str]) -> int:
    dossier = Path(argv[0]) if argv else Path("corpus")
    if "--corpus" in argv and argv[argv.index("--corpus") + 1] == "2":
        from tests.trieur.corpus.generer2 import generer as generer2

        corpus = generer2(dossier)
    else:
        corpus = generer(dossier)
    print(f"{len(corpus.verites)} documents dans {dossier}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
