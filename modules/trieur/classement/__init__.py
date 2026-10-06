"""Le classement local (§5) : à partir du texte extrait, le type, l'émetteur, la date, le montant, le numéro, les
produits et leurs garanties, avec une confiance. Gratuit, sans réseau ; Claude n'est appelé qu'en dessous du seuil.

classer(texte, reglages, note=…) → Classement.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from modules.trieur.classement import champs, dates, emetteurs, montants, regles
from modules.trieur.classement.texte import normaliser
from modules.trieur.garanties import duree

ACHATS = ("facture_achat", "ticket_caisse")
SANS_MONTANT = ("releve_bancaire", "bail_contrat", "attestation", "identite", "sante", "garantie_notice",
                "courrier_admin", "autre")  # fmt: skip


@dataclass
class Garantie:
    produit: str
    prix: Decimal | None
    debut: dt.date
    fin: dt.date
    mois: int
    source: str  # note, facture, légale
    occasion: bool = False


@dataclass
class Classement:
    type: str
    confiance: float
    libelle: str = ""
    emetteur: str | None = None
    emetteur_connu: bool = False
    categorie: str | None = None
    date: dt.date | None = None
    montant: Decimal | None = None
    numero: str | None = None
    detail: str = ""
    produits: list[champs.Produit] = field(default_factory=list)
    garanties: list[Garantie] = field(default_factory=list)
    en_ligne: bool = False
    commande: dt.date | None = None
    livraison: dt.date | None = None
    retractation: dt.date | None = None
    scores: list[tuple[str, float]] = field(default_factory=list)
    raisons: list[str] = field(default_factory=list)
    source: str = "règles"  # règles, ia, correction

    @property
    def sur(self) -> bool:
        return self.type != "autre"


def _identite(lignes_haut: list[str], identite: dict[str, Any]) -> bool:
    """Ta micro-entreprise en haut du document : c'est une facture que tu as émise."""
    nom = normaliser(identite.get("nom", "")).strip()
    siret = re.sub(r"\D", "", identite.get("siret", ""))
    haut = "\n".join(lignes_haut)
    if nom and len(nom) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(nom)}(?![a-z0-9])", haut):
        return True
    return bool(siret) and len(siret) >= 9 and siret[:9] in re.sub(r"\D", "", haut)


def classer(texte: str, reglages: dict[str, Any], note: str | None = None,
            appris: dict[str, dict[str, float]] | None = None,
            base_emetteurs: tuple[emetteurs.Emetteur, ...] | None = None,
            regles_: regles.Regles | None = None) -> Classement:  # fmt: skip
    """appris : ce que tes corrections ont appris, {clé de l'émetteur: {type: points}}."""
    r = regles_ or regles.charger()
    lignes = [li for li in normaliser(texte).splitlines() if li.strip()]
    trouve = emetteurs.trouver(texte, base_emetteurs)
    categorie = trouve.categorie if trouve else None
    bonus: dict[str, float] = {}
    if _identite(lignes[:6], reglages.get("identite", {})):
        bonus["facture_emise"] = 8.0
    if trouve and appris:
        for t, p in appris.get(emetteurs.cle(trouve.nom), {}).items():
            bonus[t] = bonus.get(t, 0.0) + p
    scores = regles.scorer(lignes, r, categorie, bonus)
    type_, confiance = regles.decider(scores, r)
    c = Classement(type_, confiance, r.libelles.get(type_, type_), scores=scores.classement()[:4])
    c.raisons = scores.raisons.get(type_, [])
    if trouve:
        c.emetteur, c.emetteur_connu, c.categorie = trouve.nom, trouve.connu, trouve.categorie
    if type_ == "facture_emise" and reglages.get("identite", {}).get("nom"):
        c.emetteur = reglages["identite"]["nom"]
    if type_ == "autre":
        c.emetteur = None
    remplir(c, texte, reglages, note)
    return c


def remplir(c: Classement, texte: str, reglages: dict[str, Any], note: str | None = None) -> None:
    """Les champs qui dépendent du type (appelé aussi après une correction ou la réponse de Claude)."""
    trouvees = dates.toutes(texte)
    c.date = dates.date_du_document(trouvees, c.type) if c.type != "autre" else None
    c.montant = None if c.type in SANS_MONTANT else montants.montant_ttc(texte)
    c.numero = (
        champs.numero(texte) if c.type in ("facture_achat", "facture_service", "facture_emise", "devis") else None
    )
    c.produits = champs.produits(texte) if c.type in ACHATS else []
    c.detail = champs.detail(c.type, texte, c.produits)
    c.garanties, c.retractation, c.en_ligne = [], None, False
    c.commande, c.livraison = dates.premiere(trouvees, "commande"), dates.premiere(trouvees, "livraison")
    if c.type not in ACHATS or c.date is None:
        return
    prix_min = Decimal(str(reglages["garanties"]["prix_min_eur"]))
    note_mois = champs.garantie_de_la_note(note)
    mention = champs.mention_garantie(texte)
    tout_occasion = champs.occasion(texte)
    durables = [p for p in c.produits if p.durable and p.prix is not None and p.prix >= prix_min]
    for p in durables:
        occasion = p.occasion or (tout_occasion and len(durables) == 1)
        d = duree.duree(note_mois, mention, occasion, reglages)
        c.garanties.append(Garantie(p.libelle, p.prix, c.date, duree.ajouter_mois(c.date, d.mois), d.mois, d.source,
                                    occasion))  # fmt: skip
    c.en_ligne = c.type == "facture_achat" and champs.achat_en_ligne(texte, c.categorie)
    if c.en_ligne:
        c.retractation = duree.rappel_retractation(c.livraison, c.commande, reglages)


def issue(c: Classement | None, nature: str, mots: int, erreur: str | None, reglages: dict[str, Any]) -> str:
    """Où va le document, sans Claude : « classe », « photos » (une vraie photo) ou « a_verifier ».
    Claude (§6) n'intervient qu'entre les deux, pour un document lisible sous le seuil de confiance."""
    if erreur in ("protege", "abime", "vide", "sans_ocr", "illisible"):
        return "a_verifier"  # sans OCR, une photo de facture ne doit pas finir dans Photos
    if nature == "image" and (c is None or (c.date is None and c.montant is None)):
        if mots < int(reglages["classement"]["photo_mots_min"]):
            return "photos"
    if c is None or erreur or c.type == "autre" or c.confiance < float(reglages["classement"]["seuil_ia"]):
        return "a_verifier"
    return "classe"


def perso_emetteurs(reglages: dict[str, Any]) -> Path | None:
    from modules.trieur import config

    try:
        return config.dossier_donnees(reglages) / "emetteurs_perso.json"
    except Exception:
        return None
