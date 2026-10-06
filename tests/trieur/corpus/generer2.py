"""Le 2e corpus (§10.1) : 60 documents écrits APRÈS le réglage des règles sur le corpus 1, pour mesurer honnêtement.

Ce qui change par rapport au corpus 1 :
- d'autres émetteurs (aucun de ceux du corpus 1, sauf l'Assurance Maladie et les impôts, qui sont uniques), dont
  quatre absents de la base du Trieur (un magasin local, une épicerie, un cabinet, un reconditionneur) ;
- d'autres mises en page : en colonnes (en-tête à droite), compacte (police à chasse fixe), à empattements ;
- d'autres titres (« Votre billet de bus ») ;
- une autre graine, donc d'autres dates, montants, produits et supports.
Les seuils sont 10 points plus bas (§10.1).
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from tests.trieur.corpus.contenu import FABRIQUES, Contexte
from tests.trieur.corpus.donnees import Emetteur, _e, personne
from tests.trieur.corpus.generer import ENTREPRISE, Corpus, _nom, _verite, dessiner
from tests.trieur.corpus.modele import Verite

PLAN_2: list[tuple[str, int, list[str]]] = [
    ("facture_achat", 12, ["pdf_texte", "pdf_texte", "scan_pdf", "pdf_texte", "scan_jpg", "pdf_texte"]),
    ("ticket_caisse", 6, ["photo_ticket", "pdf_texte", "photo_exif", "heic"]),
    ("facture_service", 5, ["pdf_texte", "scan_pdf", "pdf_texte"]),
    ("releve_bancaire", 3, ["pdf_texte", "scan_pdf", "pdf_texte"]),
    ("avis_imposition", 2, ["pdf_texte", "scan_jpg"]),
    ("quittance_loyer", 2, ["pdf_texte", "scan_jpg"]),
    ("bail_contrat", 2, ["pdf_texte"]),
    ("attestation", 3, ["pdf_texte", "scan_jpg", "pdf_texte"]),
    ("bulletin_paie", 2, ["pdf_texte", "scan_pdf"]),
    ("assurance", 3, ["pdf_texte"]),
    ("billet_transport", 3, ["pdf_texte", "heic", "pdf_texte"]),
    ("reservation", 2, ["pdf_texte"]),
    ("sante", 3, ["pdf_texte", "scan_jpg", "pdf_texte"]),
    ("identite", 2, ["scan_jpg", "photo_exif"]),
    ("devis", 2, ["pdf_texte", "scan_pdf"]),
    ("facture_emise", 2, ["pdf_texte"]),
    ("garantie_notice", 2, ["pdf_texte"]),
    ("courrier_admin", 2, ["pdf_texte", "scan_jpg"]),
    ("autre", 2, ["pdf_texte"]),
]
MISES_EN_PAGE_2 = ["colonnes", "compact", "serif"]


def emetteurs2(r: random.Random) -> dict[str, list[Emetteur]]:
    return {
        "commerce": [
            _e("Conforama", "CONFORAMA", "Conforama Bègles · 33130 Bègles", "conforama.fr", r),
            _e("Cultura", "cultura", "Cultura Rennes Cesson · 35510 Cesson-Sévigné", "cultura.com", r),
            _e("Intersport", "INTERSPORT", "Intersport Grenoble · 38000 Grenoble", "intersport.fr", r),
            _e(
                "Électroménager Durand",
                "Électroménager Durand",
                "8 place du Marché · 87000 Limoges",
                "electromenager-durand.fr",
                r,
                connu=False,
            ),  # fmt: skip
        ],
        "ecommerce": [
            _e("Rakuten", "Rakuten", "Rakuten France SAS · 92 rue Réaumur · 75002 Paris", "fr.shopping.rakuten.com", r),
            _e("LDLC", "LDLC.com", "LDLC · 2 rue des Érables · 69760 Limonest", "ldlc.com", r),
        ],
        "reconditionne": [
            _e(
                "Recyclo Phone",
                "RECYCLO PHONE",
                "Recyclo Phone · 14 rue du Port · 13002 Marseille",
                "recyclophone.example",
                r,
                connu=False,
            ),  # fmt: skip
        ],
        "supermarche": [
            _e("Auchan", "AUCHAN", "Auchan Hypermarché · 59650 Villeneuve-d'Ascq", "auchan.fr", r),
            _e("Lidl", "LIDL", "Lidl · 67000 Strasbourg", "lidl.fr", r),
            _e("Super U", "SUPER U", "Super U · 29200 Brest", "magasins-u.com", r),
            _e(
                "Épicerie Bio du Marché",
                "EPICERIE BIO DU MARCHE",
                "3 rue des Halles · 64100 Bayonne",
                "epicerie-bio.example",
                r,
                connu=False,
            ),  # fmt: skip
        ],
        "energie": [
            _e("Ekwateur", "ekWateur", "ekWateur · 75010 Paris", "ekwateur.fr", r),
            _e("Veolia", "VEOLIA EAU", "Veolia Eau · Service clients · 75008 Paris", "eau.veolia.fr", r),
        ],
        "telecom": [
            _e("Sosh", "sosh", "Sosh · Service clients · 33734 Bordeaux Cedex 9", "sosh.fr", r),
            _e(
                "La Poste Mobile",
                "La Poste Mobile",
                "La Poste Telecom · 92130 Issy-les-Moulineaux",
                "lapostemobile.fr",
                r,
            ),  # fmt: skip
        ],
        "banque": [
            _e(
                "Caisse d'Épargne",
                "CAISSE D'EPARGNE",
                "Caisse d'Épargne Grand Est · 67000 Strasbourg",
                "caisse-epargne.fr",
                r,
            ),  # fmt: skip
            _e("Crédit Mutuel", "Crédit Mutuel", "Crédit Mutuel de Bretagne · 29000 Quimper", "creditmutuel.fr", r),
            _e("BoursoBank", "BoursoBank", "BoursoBank · 92100 Boulogne-Billancourt", "boursobank.com", r),
        ],
        "impots": [
            _e(
                "Impôts",
                "DIRECTION GÉNÉRALE DES FINANCES PUBLIQUES",
                "Service des impôts des particuliers",
                "impots.gouv.fr",
                r,
            )
        ],  # fmt: skip
        "social": [_e("URSSAF", "Urssaf", "Urssaf Bretagne · 35000 Rennes", "urssaf.fr", r)],
        "sante": [
            _e("Ameli", "l'Assurance Maladie", "CPAM d'Ille-et-Vilaine · 35024 Rennes Cedex 9", "ameli.fr", r),
            _e("Malakoff Humanis", "Malakoff Humanis", "Malakoff Humanis · 75009 Paris", "malakoffhumanis.com", r),
            _e("Alan", "alan", "Alan SA · 75010 Paris", "alan.com", r),
        ],
        "assurance": [
            _e("MAAF", "MAAF Assurances", "MAAF · 79036 Niort Cedex 9", "maaf.fr", r),
            _e("Matmut", "MATMUT", "Matmut · 76030 Rouen Cedex 1", "matmut.fr", r),
            _e("Groupama", "Groupama", "Groupama Centre Manche · 76000 Rouen", "groupama.fr", r),
        ],
        "transport": [
            _e("easyJet", "easyJet", "easyJet Airline Company · Luton", "easyjet.com", r),
            _e("FlixBus", "FlixBus", "FlixBus France SARL · 75008 Paris", "flixbus.fr", r),
        ],
        "hebergement": [
            _e("Abritel", "Abritel", "Abritel · Vrbo · 92130 Issy-les-Moulineaux", "abritel.fr", r),
            _e("Accor", "ALL - Accor Live Limitless", "Accor SA · 92130 Issy-les-Moulineaux", "all.accor.com", r),
        ],
        "immobilier": [_e("Nexity", "NEXITY", "Nexity Lamy · 33000 Bordeaux", "nexity.fr", r)],
    }


def generer(dossier: Path, graine: int = 20270114) -> Corpus:
    dossier.mkdir(parents=True, exist_ok=True)
    travail = dossier / ".sources"
    travail.mkdir(exist_ok=True)
    r = random.Random(graine)
    c = Contexte(r, emetteurs2(random.Random(graine + 1)), personne(r), ENTREPRISE)
    verites: list[Verite] = []
    n = 200
    for type_, nombre, supports in PLAN_2:
        fabrique, variantes = FABRIQUES[type_]
        for i in range(nombre):
            n += 1
            support = supports[i % len(supports)]
            doc, valeurs = fabrique(c, variantes[(i + 1) % len(variantes)])
            nom = _nom(r, n, support)
            chemin = dossier / nom
            reel = dessiner(doc, support, chemin, r, MISES_EN_PAGE_2[n % len(MISES_EN_PAGE_2)], travail)
            if reel != support:
                nom = chemin.with_suffix(".jpg").name
            verites.append(_verite(nom, reel, valeurs, "corpus2"))
    (dossier / "verite.json").write_text(json.dumps([v.vers_dict() for v in verites], ensure_ascii=False, indent=1),
                                         encoding="utf-8")  # fmt: skip
    return Corpus(dossier, verites)
