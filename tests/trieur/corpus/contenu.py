"""Le contenu de chaque type de document, avec plusieurs variantes, des pièges (date d'impression, date d'échéance,
période, opérations d'un relevé…) et la vérité terrain qui en découle.

Règles de la vérité terrain (les mêmes que celles annoncées au Trieur, D-xx) :
- date du document : la date d'achat, sinon la date de facture ou d'émission ; un relevé, la fin de la période ;
  un billet, le départ ; une réservation, l'arrivée ; un bulletin de paie, la date de paiement ;
- garantie : un bien durable d'au moins 30 € ; la note l'emporte, sinon la plus longue entre la mention du
  document et la garantie légale (24 mois neuf, 12 mois d'occasion chez un professionnel) ;
- rétractation (achat en ligne) : rappel 11 jours après la livraison, sinon après la commande.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from tests.trieur.corpus.donnees import (
    CONSOMMABLES,
    DURABLES,
    MOIS,
    OCCASIONS,
    Emetteur,
    Personne,
    Produit,
    personne,
)
from tests.trieur.corpus.modele import Doc, ajouter_mois, date_fr, euros, iso, montant_fr

DEBUT, FIN = date(2025, 1, 6), date(2026, 9, 28)


@dataclass
class Contexte:
    r: random.Random
    emetteurs: dict[str, list[Emetteur]]
    moi: Personne
    entreprise: dict[str, str] = field(default_factory=dict)  # ta micro-entreprise (config « identite »)

    def jour(self) -> date:
        return DEBUT + timedelta(days=self.r.randint(0, (FIN - DEBUT).days))

    def de(self, famille: str) -> Emetteur:
        return self.r.choice(self.emetteurs[famille])


Fabrique = Callable[[Contexte, str], tuple[Doc, dict[str, Any]]]


def _pied(e: Emetteur, r: random.Random) -> list[str]:
    morceaux = [e.adresse]
    if e.siret:
        morceaux.append(f"SIRET {e.siret} · TVA intracommunautaire {e.tva}" if r.random() < 0.8 else f"SIRET {e.siret}")
    morceaux.append(f"www.{e.domaine}" if not e.domaine.startswith("www") else e.domaine)
    return morceaux


def _garanties(produits: list[Produit], achat: date, mention_mois: int, note_mois: int | None) -> list[dict[str, str]]:
    sortie = []
    for p in produits:
        if not p.durable or p.prix < 30:
            continue
        occasion = "reconditionn" in p.libelle.lower() or "occasion" in p.libelle.lower()
        legale = 12 if occasion else 24
        if note_mois:
            mois, source = note_mois, "note"
        elif mention_mois > legale:
            mois, source = mention_mois, "facture"
        else:
            mois, source = legale, "légale"
        sortie.append({"produit": p.libelle, "fin": ajouter_mois(achat, mois).isoformat(), "source": source})
    return sortie


# --- achats ----------------------------------------------------------------------------------------------------


def facture_achat(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    en_ligne = variante in ("en_ligne", "occasion", "occasion_mention")
    if variante.startswith("occasion"):
        e = (c.emetteurs.get("reconditionne") or [x for x in c.emetteurs["ecommerce"] if x.nom == "Back Market"])[0]
    else:
        e = c.de("ecommerce") if en_ligne else c.de("commerce")
    achat = date(2024, 2, 29) if variante == "29fevrier" else c.jour()
    if variante.startswith("occasion"):
        produits = [r.choice(OCCASIONS)]
    elif variante == "consommables":
        produits = r.sample(CONSOMMABLES, r.randint(1, 3))
    elif variante == "mixte":
        produits = [r.choice(DURABLES), r.choice(CONSOMMABLES)]
    else:
        produits = [r.choice(DURABLES)] + (r.sample(CONSOMMABLES, 1) if r.random() < 0.3 else [])
    mention_mois, lignes_extra, mentions = 0, [], []
    if variante == "extension_3ans" or variante == "29fevrier":
        lignes_extra.append(("Extension de garantie 3 ans", 49.99))
        mention_mois = 36
    elif variante == "mention_2ans":
        mentions.append(
            r.choice(["Garantie 2 ans pièces et main-d'œuvre.", "Ce produit bénéficie d'une garantie de 2 ans."])
        )
        mention_mois = 24
    elif variante == "constructeur_12":
        mentions.append("Garantie constructeur 12 mois.")
        mention_mois = 12
    elif variante == "occasion_mention":
        mentions.append(f"Garantie {e.nom} : 24 mois.")
        mention_mois = 24
    elif variante == "occasion":
        mentions.append("Produit reconditionné. Garantie commerciale 12 mois.")
        mention_mois = 12
    quantites = [1 if p.durable else r.choice([1, 1, 2]) for p in produits]
    total = round(
        sum(p.prix * q for p, q in zip(produits, quantites, strict=True)) + sum(x for _, x in lignes_extra), 2
    )
    numero = f"{r.choice(['F', 'FA', 'INV', ''])}{achat.year}-{r.randint(10000, 99999)}"
    meta = [("Facture n°", numero)]
    retractation = None
    if en_ligne:
        commande = achat - timedelta(days=r.randint(1, 4))
        livraison = achat + timedelta(days=r.randint(1, 3))
        meta += [("Commande n°", f"{r.randint(100, 999)}-{r.randint(1000000, 9999999)}"),
                 ("Date de la commande", date_fr(commande, r)), ("Date de facture", date_fr(achat, r))]  # fmt: skip
        if r.random() < 0.75:
            meta.append(("Livrée le", date_fr(livraison, r)))
            retractation = livraison + timedelta(days=11)
        else:
            retractation = commande + timedelta(days=11)
    else:
        meta.insert(0, (r.choice(["Date d'achat", "Date", "Date de facture"]), date_fr(achat, r)))
        if r.random() < 0.4:
            meta.append(("Imprimé le", date_fr(achat + timedelta(days=r.randint(2, 40)), r)))
    tableau = [["Désignation", "Qté", "Prix unitaire", "Montant"]]
    for p, q in zip(produits, quantites, strict=True):
        tableau.append(
            [
                p.libelle,
                str(q),
                montant_fr(p.prix, r, ["espace", "colle"]),
                montant_fr(p.prix * q, r, ["espace", "colle"]),
            ]
        )
    for lib, prix in lignes_extra:
        tableau.append([lib, "1", montant_fr(prix, r, ["espace"]), montant_fr(prix, r, ["espace"])])
    tva = round(total - total / 1.2, 2)
    totaux = [("Total HT", montant_fr(total - tva, r, ["espace"])), ("TVA 20 %", montant_fr(tva, r, ["espace"])),
              (r.choice(["Total TTC", "Net à payer", "Montant TTC", "Total à payer"]), montant_fr(total, r))]  # fmt: skip
    paragraphes = mentions + [r.choice([f"Payé par carte bancaire **** {r.randint(1000, 9999)}",
                                        "Règlement : carte bancaire", "Paiement en ligne accepté"])]  # fmt: skip
    doc = Doc([e.entete] + ([e.adresse] if r.random() < 0.6 else []), r.choice(["FACTURE", "Facture", "Facture d'achat"]),
              meta, c.moi.lignes, tableau, totaux, paragraphes, _pied(e, r))  # fmt: skip
    verite = {"type": "facture_achat", "emetteur": e.nom, "date": iso(achat), "montant": euros(total),
              "garanties": _garanties(produits, achat, mention_mois, None), "retractation": iso(retractation)}  # fmt: skip
    return doc, verite


ARTICLES = ["LAIT DEMI-ECREME 1L", "PAIN DE MIE COMPLET", "PATES FUSILLI 500G", "YAOURT NATURE X8", "POMMES GALA",
            "CAFE MOULU 250G", "BEURRE DOUX 250G", "JUS D'ORANGE 1L", "EAU MINERALE 6X1.5L", "OEUFS X12",
            "TOMATES GRAPPE", "EMMENTAL RAPE 200G", "LESSIVE LIQUIDE", "PAPIER TOILETTE X12"]  # fmt: skip


def ticket_caisse(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    jour = c.jour()
    heure = f"{r.randint(8, 20):02d}:{r.randint(0, 59):02d}"
    garanties: list[dict[str, str]] = []
    if variante == "durable_magasin":
        e = r.choice(
            [x for x in c.emetteurs["commerce"] if x.nom in ("Fnac", "Darty", "Boulanger", "Decathlon")]
            or c.emetteurs["commerce"]
        )
        p = r.choice([x for x in DURABLES if x.prix < 700])
        lignes = [(p.libelle.upper()[:30], p.prix)]
        garanties = _garanties([p], jour, 0, None)
    else:
        e = c.de("supermarche")
        lignes = [(a, round(r.uniform(0.85, 9.9), 2)) for a in r.sample(ARTICLES, r.randint(5, 10))]
    total = round(sum(x for _, x in lignes), 2)
    tableau = [["ARTICLE", "", "", "EUR"]] + [[lib, "", "", f"{prix:.2f}".replace(".", ",")] for lib, prix in lignes]
    date_txt = r.choice([jour.strftime("%d/%m/%Y"), jour.strftime("%d/%m/%y"), jour.strftime("%d.%m.%Y")])
    meta = [("", f"{date_txt}  {heure}"), ("CAISSE", f"{r.randint(1, 12):02d}  TICKET {r.randint(1000, 9999)}")]
    totaux = [
        ("TOTAL", f"{total:.2f}".replace(".", ",") + r.choice([" EUR", " €", ""])),
        ("CB", f"{total:.2f}".replace(".", ",")),
    ]
    paragraphes = ["MERCI DE VOTRE VISITE", "A BIENTOT"]
    if variante == "durable_magasin":
        paragraphes.insert(0, "CONSERVEZ CE TICKET : PREUVE D'ACHAT")
    doc = Doc([e.entete, e.adresse.split("·")[-1].strip()], "TICKET DE CAISSE" if r.random() < 0.5 else "",
              meta, [], tableau, totaux, paragraphes, [f"SIRET {e.siret}"], ticket=True)  # fmt: skip
    return doc, {"type": "ticket_caisse", "emetteur": e.nom, "date": iso(jour), "montant": euros(total),
                 "garanties": garanties}  # fmt: skip


# --- factures de services ----------------------------------------------------------------------------------------


def facture_service(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    e = c.de("energie" if variante == "energie" else "telecom")
    jour = c.jour()
    total = round(r.uniform(19.99, 189.0), 2)
    debut = (jour.replace(day=1) - timedelta(days=1)).replace(day=1)
    fin = jour.replace(day=1) - timedelta(days=1)
    meta = [(r.choice(["Date de facture", "Facture du", "Émise le"]), date_fr(jour, r)),
            ("N° de facture", f"{r.randint(10**9, 10**10 - 1)}"), ("N° client", f"{r.randint(10**7, 10**8 - 1)}"),
            ("Période", f"du {date_fr(debut, r, ['num'])} au {date_fr(fin, r, ['num'])}")]  # fmt: skip
    if variante == "energie":
        meta.append(("Référence PDL", "".join(str(r.randint(0, 9)) for _ in range(14))))
        tableau = [["Libellé", "Quantité", "Montant TTC"], ["Abonnement", "1 mois", montant_fr(round(total * 0.3, 2), r, ["espace"])],
                   ["Consommation électricité", f"{r.randint(120, 600)} kWh", montant_fr(round(total * 0.6, 2), r, ["espace"])],
                   ["Taxes et contributions", "", montant_fr(round(total * 0.1, 2), r, ["espace"])]]  # fmt: skip
    else:
        offre = r.choice(["Forfait mobile 100 Go", "Box Fibre", "Freebox Pop", "Forfait 5G 130 Go"])
        tableau = [["Description", "Montant TTC"], [offre, montant_fr(total, r, ["espace"])]]
    totaux = [
        (
            r.choice(["Montant TTC à payer", "Total TTC", "Total de votre facture", "Montant total TTC"]),
            montant_fr(total, r),
        )
    ]
    prelevement = jour + timedelta(days=r.randint(8, 20))
    paragraphes = [f"Ce montant sera prélevé le {date_fr(prelevement, r, ['num'])} sur votre compte."]
    doc = Doc([e.entete, e.adresse], r.choice(["Votre facture", "FACTURE", f"Votre facture {e.nom}"]), meta,
              c.moi.lignes, tableau, totaux, paragraphes, _pied(e, r))  # fmt: skip
    return doc, {"type": "facture_service", "emetteur": e.nom, "date": iso(jour), "montant": euros(total)}


# --- banque, impôts, logement ----------------------------------------------------------------------------------


def releve_bancaire(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    e = c.de("banque")
    jour = c.jour()
    fin = jour.replace(day=1) - timedelta(days=1)
    debut = fin.replace(day=1)
    operations = [["Date", "Libellé", "Débit", "Crédit"]]
    solde = round(r.uniform(300, 4000), 2)
    for _ in range(r.randint(6, 14)):
        d = debut + timedelta(days=r.randint(0, (fin - debut).days))
        lib = r.choice(["CB CARREFOUR MARKET", "PRLV SEPA EDF", "VIR SALAIRE", "CB SNCF", "PRLV FREE MOBILE",
                        "CB AMAZON PAYMENTS", "RETRAIT DAB", "VIR LOYER"])  # fmt: skip
        montant = montant_fr(round(r.uniform(5, 900), 2), r, ["colle", "espace"]).replace("€", "").strip()
        operations.append(
            [d.strftime("%d/%m"), lib, montant, ""]
            if "VIR SALAIRE" not in lib
            else [d.strftime("%d/%m"), lib, "", montant]
        )
    meta = [("Période", f"du {date_fr(debut, r, ['num'])} au {date_fr(fin, r, ['num'])}"),
            ("Titulaire", f"{c.moi.prenom} {c.moi.nom}"), ("IBAN", c.moi.iban), ("BIC", "BNPAFRPPXXX")]  # fmt: skip
    totaux = [
        ("Ancien solde", montant_fr(solde, r, ["espace"])),
        ("Nouveau solde", montant_fr(round(solde + r.uniform(-300, 300), 2), r, ["espace"])),
    ]
    titre = r.choice(["RELEVÉ DE COMPTE", "Relevé de compte courant", "Extrait de compte"])
    doc = Doc([e.entete, e.adresse], titre, meta, c.moi.lignes, operations, totaux, [], _pied(e, r))
    return doc, {"type": "releve_bancaire", "emetteur": e.nom, "date": iso(fin), "montant": None, "banque": e.nom}


def avis_imposition(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    e = c.emetteurs["impots"][0]
    annee = r.choice([2025, 2026])
    recouvrement = date(annee, 7, r.choice([31, 31, 30])) if variante == "revenu" else date(annee, 8, 31)
    limite = recouvrement + timedelta(days=r.randint(40, 50))
    montant = float(r.randint(250, 3200))
    numero_fiscal = (
        f"{r.randint(10, 39)} {r.randint(10, 99)} {r.randint(100, 999)} {r.randint(100, 999)} {r.randint(100, 999)}"
    )
    if variante == "revenu":
        titre = f"AVIS D'IMPÔT {annee} SUR LES REVENUS DE L'ANNÉE {annee - 1}"
        meta = [("Numéro fiscal", numero_fiscal), ("Référence de l'avis", f"{annee % 100}{r.randint(10**10, 10**11 - 1)}"),
                ("Revenu fiscal de référence", f"{r.randint(18000, 60000)} €"),
                ("Date de mise en recouvrement", date_fr(recouvrement, r, ["num", "long"])),
                ("Date limite de paiement", date_fr(limite, r, ["num", "long"]))]  # fmt: skip
        totaux = [(r.choice(["Montant de votre impôt", "Reste à payer", "Montant à payer"]),
                   montant_fr(montant, r, ["espace", "colle"]).replace(",00", ""))]  # fmt: skip
    else:
        titre = f"AVIS DE TAXE FONCIÈRE {annee}"
        meta = [("Numéro fiscal", numero_fiscal), ("Date d'établissement", date_fr(recouvrement, r, ["num"])),
                ("Date limite de paiement", date_fr(limite, r, ["num"]))]  # fmt: skip
        totaux = [("Montant à payer", montant_fr(montant, r, ["espace"]))]
    paragraphes = ["Vous pouvez payer en ligne sur impots.gouv.fr, espace particulier."]
    doc = Doc(["RÉPUBLIQUE FRANÇAISE", e.entete, e.adresse], titre, meta, c.moi.lignes, [], totaux, paragraphes,
              ["impots.gouv.fr"])  # fmt: skip
    return doc, {"type": "avis_imposition", "emetteur": e.nom, "date": iso(recouvrement), "montant": euros(montant),
                 "sensible": True}  # fmt: skip


def quittance_loyer(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    jour = c.jour().replace(day=r.choice([1, 2, 5]))
    debut = (jour.replace(day=1) - timedelta(days=1)).replace(day=1)
    fin = jour.replace(day=1) - timedelta(days=1)
    if variante == "agence":
        e = c.emetteurs["immobilier"][0]
        bailleur, nom = [e.entete, e.adresse], e.nom
    else:
        nom = r.choice(["SCI Les Tilleuls", "Vincent Lambert", "SCI du Parc"])
        bailleur, nom = [nom, f"{r.randint(1, 60)} rue des Acacias · 69006 Lyon"], nom
    loyer, charges = float(r.choice([620, 750, 840, 910, 1050])), float(r.choice([40, 60, 80, 95]))
    meta = [("Période", f"du {date_fr(debut, r, ['num'])} au {date_fr(fin, r, ['num'])}"),
            ("Locataire", f"{c.moi.prenom} {c.moi.nom}"), ("Adresse du logement", c.moi.adresse)]  # fmt: skip
    totaux = [("Loyer", montant_fr(loyer, r, ["espace"])), ("Charges", montant_fr(charges, r, ["espace"])),
              (r.choice(["Total", "Total payé", "Montant total"]), montant_fr(loyer + charges, r))]  # fmt: skip
    paragraphes = [f"Je soussigné(e), bailleur, déclare avoir reçu la somme de {montant_fr(loyer + charges, r, ['espace'])} "
                   "au titre du loyer et des charges pour la période indiquée, et en donne quittance, sous réserve de "
                   "tous mes droits.", f"Fait à Lyon, le {date_fr(jour, r, ['num', 'long'])}"]  # fmt: skip
    doc = Doc(
        bailleur,
        r.choice(["QUITTANCE DE LOYER", "Quittance de loyer"]),
        meta,
        c.moi.lignes,
        [],
        totaux,
        paragraphes,
        [],
    )
    return doc, {"type": "quittance_loyer", "emetteur": nom, "date": iso(jour), "montant": euros(loyer + charges)}


def bail_contrat(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    jour = c.jour()
    if variante == "bail":
        e = c.emetteurs["immobilier"][0]
        titre = r.choice(["CONTRAT DE LOCATION", "BAIL D'HABITATION — LOCAUX VIDES", "Contrat de bail d'habitation"])
        paragraphes = ["Entre les soussignés : le bailleur, représenté par son mandataire, et le locataire désigné "
                       "ci-dessous, il a été convenu ce qui suit.", "Article 1 — Objet du contrat : location d'un logement "
                       "à usage de résidence principale.", "Article 4 — Durée : le présent bail est conclu pour une durée "
                       "de trois ans à compter de sa prise d'effet.", "Article 5 — Loyer : le loyer mensuel est fixé à "
                       f"{montant_fr(840, r, ['espace'])} charges comprises, payable d'avance.",
                       f"Fait à Lyon, le {date_fr(jour, r, ['long'])}, en deux exemplaires."]  # fmt: skip
        entete, nom = [e.entete, e.adresse], e.nom
    else:
        nom = r.choice(["Agence Web Horizon", "Studio Graphique Lune"])
        titre = r.choice(["CONTRAT DE PRESTATION DE SERVICES", "Contrat de prestation"])
        paragraphes = ["Entre les parties désignées ci-après, il est convenu ce qui suit.", "Article 1 — Objet : "
                       "le prestataire réalise pour le client les missions décrites en annexe.", "Article 3 — Durée : "
                       "le contrat prend effet à la date de signature pour une durée de douze mois.",
                       "Article 6 — Résiliation : chaque partie peut résilier le contrat par lettre recommandée.",
                       f"Fait à Paris, le {date_fr(jour, r, ['long', 'num'])}."]  # fmt: skip
        entete = [nom, f"{r.randint(1, 80)} rue de la Paix · 75002 Paris"]
    doc = Doc(entete, titre, [], [], [], [], paragraphes, ["Paraphe :            Signature :"])
    return doc, {"type": "bail_contrat", "emetteur": nom, "date": iso(jour), "montant": None}


# --- attestations, paie, assurances ----------------------------------------------------------------------------


def attestation(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    jour = c.jour()
    moi = f"{c.moi.prenom} {c.moi.nom}"
    if variante == "scolarite":
        nom = r.choice(["Université de Bordeaux", "Lycée Victor Hugo"])
        entete, titre = [nom, "Service de la scolarité"], "ATTESTATION DE SCOLARITÉ"
        corps = [f"Le responsable de la scolarité certifie que {moi} est régulièrement inscrit(e) pour l'année "
                 f"universitaire {jour.year}-{jour.year + 1}, en Licence 3 Gestion."]  # fmt: skip
    elif variante == "assurance":
        e = c.de("assurance")
        nom, entete, titre = e.nom, [e.entete, e.adresse], "ATTESTATION D'ASSURANCE HABITATION"
        corps = [f"{e.nom} atteste que {moi} est titulaire d'un contrat d'assurance multirisque habitation n° "
                 f"{r.randint(10**6, 10**7)} garantissant les risques locatifs du logement situé {c.moi.adresse}.",
                 "La présente attestation est valable du 01/01 au 31/12 de l'année en cours."]  # fmt: skip
    elif variante == "caf":
        e = c.emetteurs["social"][0]
        nom, entete, titre = e.nom, [e.entete, e.adresse], "ATTESTATION DE PAIEMENT"
        corps = [f"La Caisse d'allocations familiales certifie que {moi}, allocataire n° {r.randint(10**6, 10**7)}, "
                 "a perçu les prestations suivantes au cours des douze derniers mois : aide personnalisée au logement."]  # fmt: skip
    else:
        nom = r.choice(["Société Exemple SAS", "Boulangerie Fournil & Co"])
        entete, titre = (
            [nom, f"{r.randint(1, 90)} avenue Foch · 75116 Paris"],
            r.choice(["ATTESTATION EMPLOYEUR", "Attestation de travail"]),
        )
        corps = [f"Je soussigné, directeur des ressources humaines, atteste que {moi} est employé(e) au sein de notre "
                 f"société depuis le {date_fr(jour - timedelta(days=500), r, ['num'])} en contrat à durée "
                 "indéterminée, en qualité d'assistant(e) comptable."]  # fmt: skip
    corps.append(r.choice([f"Fait le {date_fr(jour, r, ['num', 'long'])}, pour servir et valoir ce que de droit.",
                           f"Délivrée le {date_fr(jour, r, ['num'])}.", f"Paris, le {date_fr(jour, r, ['long'])}"]))  # fmt: skip
    doc = Doc(entete, titre, [], c.moi.lignes, [], [], corps, [], lettre=r.random() < 0.5)
    return doc, {"type": "attestation", "emetteur": nom, "date": iso(jour), "montant": None}


def bulletin_paie(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    jour = c.jour()
    fin = jour.replace(day=1) - timedelta(days=1)
    paiement = fin
    nom = r.choice(["Société Exemple SAS", "Boulangerie Fournil & Co", "Cabinet Comptable Ariane"])
    brut = round(r.uniform(1900, 3600), 2)
    net = round(brut * 0.78, 2)
    meta = [("Période", f"du {date_fr(fin.replace(day=1), r, ['num'])} au {date_fr(fin, r, ['num'])}"),
            ("Date de paiement", date_fr(paiement, r, ["num"])), ("Salarié", f"{c.moi.prenom} {c.moi.nom}"),
            ("N° de sécurité sociale", c.moi.nir), ("Emploi", "Assistant(e) comptable")]  # fmt: skip
    tableau = [["Rubrique", "Base", "Taux", "Montant"], ["Salaire de base", "151,67", "", montant_fr(brut, r, ["espace"])],
               ["Sécurité sociale plafonnée", montant_fr(brut, r, ["espace"]), "6,90", montant_fr(brut * 0.069, r, ["espace"])],
               ["CSG déductible", montant_fr(brut * 0.9825, r, ["espace"]), "6,80", montant_fr(brut * 0.068, r, ["espace"])]]  # fmt: skip
    totaux = [("Salaire brut", montant_fr(brut, r, ["espace"])), ("Net à payer", montant_fr(net, r))]
    doc = Doc([nom, "SIRET 812 345 678 00021 · Code NAF 6920Z"], r.choice(["BULLETIN DE PAIE", "Bulletin de salaire"]),
              meta, [], tableau, totaux, ["Dans votre intérêt et pour vous aider à faire valoir vos droits, conservez ce "
                                          "bulletin de paie sans limitation de durée."], [])  # fmt: skip
    return doc, {
        "type": "bulletin_paie",
        "emetteur": nom,
        "date": iso(paiement),
        "montant": euros(net),
        "sensible": True,
    }


def assurance(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    e = c.de("assurance")
    jour = c.jour()
    cotisation = round(r.uniform(180, 900), 2)
    if variante == "echeance":
        titre = "AVIS D'ÉCHÉANCE"
        meta = [("Émis le", date_fr(jour, r)), ("Contrat", f"Auto n° {r.randint(10**6, 10**7)}"),
                ("Échéance au", date_fr(jour + timedelta(days=30), r, ["num"]))]  # fmt: skip
        totaux = [("Cotisation annuelle TTC", montant_fr(cotisation, r))]
        montant: float | None = cotisation
    else:
        titre = "CONDITIONS PARTICULIÈRES"
        meta = [("Date d'effet", date_fr(jour, r, ["num"])), ("Contrat", f"Habitation n° {r.randint(10**6, 10**7)}")]
        totaux, montant = [], None
    paragraphes = ["Votre contrat d'assurance couvre les garanties souscrites : responsabilité civile, dommages, "
                   "vol, bris de glace. Franchise selon les conditions générales.",
                   "Pour déclarer un sinistre, contactez votre conseiller."]  # fmt: skip
    doc = Doc([e.entete, e.adresse], titre, meta, c.moi.lignes, [], totaux, paragraphes, _pied(e, r))
    return doc, {"type": "assurance", "emetteur": e.nom, "date": iso(jour), "montant": euros(montant)}


# --- voyages ---------------------------------------------------------------------------------------------------

TRAJETS = [("Paris Gare de Lyon", "Lyon Part-Dieu"), ("Bordeaux Saint-Jean", "Paris Montparnasse"),
           ("Lille Europe", "Marseille Saint-Charles"), ("Nantes", "Rennes"), ("Paris CDG", "Nice Côte d'Azur")]  # fmt: skip


def billet_transport(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    e = c.de("transport")
    depart = c.jour()
    emis = depart - timedelta(days=r.randint(3, 40))
    de, a = r.choice(TRAJETS)
    prix = round(r.uniform(19, 189), 2)
    titre = {"SNCF": "E-BILLET", "Air France": "CARTE D'EMBARQUEMENT", "BlaBlaCar": "Confirmation de trajet",
             "easyJet": "CARTE D'EMBARQUEMENT", "FlixBus": "Votre billet de bus", "Ouigo": "Votre billet"}[e.nom]  # fmt: skip
    meta = [("Référence dossier", "".join(r.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(6))),
            ("Passager", f"{c.moi.prenom} {c.moi.nom}"), ("Trajet", f"{de} → {a}"),
            (r.choice(["Aller le", "Départ le", "Date du voyage"]), f"{date_fr(depart, r, ['num', 'long'])} à {r.randint(6, 21):02d}:{r.choice(['04', '12', '37', '50'])}"),
            ("Émis le", date_fr(emis, r, ["num"]))]  # fmt: skip
    totaux = [(r.choice(["Prix", "Montant payé", "Total"]), montant_fr(prix, r))]
    doc = Doc(
        [e.entete], titre, meta, [], [], totaux, ["Billet nominatif, non échangeable.", "Bon voyage !"], _pied(e, r)
    )
    return doc, {"type": "billet_transport", "emetteur": e.nom, "date": iso(depart), "montant": euros(prix)}


def reservation(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    e = c.de("hebergement")
    arrivee = c.jour()
    nuits = r.randint(1, 6)
    total = round(nuits * r.uniform(60, 180), 2)
    hotel = r.choice(
        ["Hôtel des Arts", "Résidence Les Mouettes", "Appartement lumineux centre-ville", "Ibis Styles Gare"]
    )
    meta = [("Numéro de confirmation", f"{r.randint(10**9, 10**10 - 1)}"), ("Établissement", hotel),
            ("Arrivée", date_fr(arrivee, r)), ("Départ", date_fr(arrivee + timedelta(days=nuits), r)),
            ("Réservé le", date_fr(arrivee - timedelta(days=r.randint(5, 60)), r, ["num"]))]  # fmt: skip
    totaux = [(r.choice(["Montant total", "Prix total", "Total payé"]), montant_fr(total, r))]
    doc = Doc([e.entete], r.choice(["Confirmation de réservation", "Votre réservation est confirmée"]), meta,
              [f"{c.moi.prenom} {c.moi.nom}"], [], totaux, ["Annulation gratuite jusqu'à 48 h avant l'arrivée."], _pied(e, r))  # fmt: skip
    return doc, {"type": "reservation", "emetteur": e.nom, "date": iso(arrivee), "montant": euros(total)}


# --- santé, identité (sensibles) -------------------------------------------------------------------------------


def sante(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    jour = c.jour()
    if variante == "ameli":
        e = next(x for x in c.emetteurs["sante"] if x.nom == "Ameli")
        titre, nom = "RELEVÉ DE REMBOURSEMENTS", e.nom
        meta = [("N° de sécurité sociale", c.moi.nir), ("Date du relevé", date_fr(jour, r, ["num"]))]
        tableau = [["Date des soins", "Prestation", "Montant payé", "Remboursé"],
                   [date_fr(jour - timedelta(days=9), r, ["num"]), "Consultation médecin généraliste", "30,00", "21,00"],
                   [date_fr(jour - timedelta(days=6), r, ["num"]), "Pharmacie", "18,40", "11,96"]]  # fmt: skip
        entete = [e.entete, e.adresse]
    elif variante == "mutuelle":
        e = r.choice([x for x in c.emetteurs["sante"] if x.nom != "Ameli"])
        titre, nom = "DÉCOMPTE DE REMBOURSEMENT", e.nom
        meta = [("Adhérent", f"{c.moi.prenom} {c.moi.nom}"), ("Date du décompte", date_fr(jour, r, ["num"]))]
        tableau = [
            ["Soins", "Dépense", "Part Sécurité sociale", "Part mutuelle"],
            ["Optique - verres", "320,00", "0,09", "200,00"],
        ]
        entete = [e.entete, e.adresse]
    else:
        nom = r.choice(["Dr Hélène Girard", "Dr Marc Fontaine"])
        titre = "ORDONNANCE"
        meta = [("Patient", f"{c.moi.prenom} {c.moi.nom}"), ("Le", date_fr(jour, r, ["num", "long"]))]
        tableau = []
        entete = [
            nom,
            "Médecin généraliste · Conventionné secteur 1",
            f"{r.randint(1, 50)} rue Pasteur · 33000 Bordeaux",
        ]
    paragraphes = ([] if tableau else ["Paracétamol 1 g : 1 comprimé 3 fois par jour pendant 5 jours.",
                                       "Ibuprofène 400 mg : si douleur, 1 comprimé au cours du repas."])  # fmt: skip
    doc = Doc(entete, titre, meta, c.moi.lignes, tableau, [], paragraphes, [])
    return doc, {"type": "sante", "emetteur": nom, "date": iso(jour), "montant": None, "sensible": True}


def identite(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    delivrance = c.jour()
    titre = {"cni": "CARTE NATIONALE D'IDENTITÉ", "passeport": "PASSEPORT", "permis": "PERMIS DE CONDUIRE"}[variante]
    meta = [("Nom", c.moi.nom.upper()), ("Prénoms", c.moi.prenom), ("Né(e) le", f"{r.randint(1, 28):02d}/{r.randint(1, 12):02d}/{r.randint(1975, 2004)}"),
            ("N° du document", f"{r.randint(10, 99)}{r.choice('ABCDEFGH')}{r.randint(10000, 99999)}"),
            ("Date de délivrance", date_fr(delivrance, r, ["num", "point"])),
            ("Date d'expiration", date_fr(ajouter_mois(delivrance, 120 if variante != "permis" else 180), r, ["num", "point"]))]  # fmt: skip
    doc = Doc(["RÉPUBLIQUE FRANÇAISE"], titre, meta, [], [], [], [], [])
    return doc, {
        "type": "identite",
        "emetteur": "République française",
        "date": iso(delivrance),
        "montant": None,
        "sensible": True,
    }


# --- micro-entreprise, garanties, courriers, autres ------------------------------------------------------------

ARTISANS = [("Plomberie Martin", "Remplacement chauffe-eau 200 L"), ("Électricité Dubois", "Mise aux normes tableau électrique"),
            ("Menuiserie Fontaine", "Pose de deux fenêtres PVC"), ("Peinture Rousseau & Fils", "Peinture salon 25 m²")]  # fmt: skip


def devis(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    jour = c.jour()
    nom, prestation = r.choice(ARTISANS)
    ht = round(r.uniform(400, 4800), 2)
    ttc = round(ht * 1.1, 2)
    meta = [("Devis n°", f"D-{jour.year}-{r.randint(10, 300):03d}"), (r.choice(["Date du devis", "Date", "Établi le"]), date_fr(jour, r)),
            ("Valable jusqu'au", date_fr(jour + timedelta(days=30), r, ["num"]))]  # fmt: skip
    tableau = [["Désignation", "Qté", "Prix HT"], [prestation, "1", montant_fr(ht * 0.7, r, ["espace"])],
               ["Main-d'œuvre", "1", montant_fr(ht * 0.3, r, ["espace"])]]  # fmt: skip
    totaux = [("Total HT", montant_fr(ht, r, ["espace"])), ("TVA 10 %", montant_fr(ttc - ht, r, ["espace"])),
              ("Total TTC", montant_fr(ttc, r))]  # fmt: skip
    paragraphes = ["Bon pour accord, date et signature du client :", "Devis gratuit. Acompte de 30 % à la commande."]
    doc = Doc([nom, f"{r.randint(1, 80)} rue des Artisans · 44000 Nantes", f"06 {r.randint(10, 99)} 12 34 56"],
              r.choice(["DEVIS", "Devis"]), meta, c.moi.lignes, tableau, totaux, paragraphes, [f"SIRET {r.randint(100, 999)} 456 789 00012"])  # fmt: skip
    return doc, {"type": "devis", "emetteur": nom, "date": iso(jour), "montant": euros(ttc)}


def facture_emise(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    jour = c.jour()
    client = r.choice(["Société Delta Conseil", "Mairie de Saint-Aubin", "Librairie Le Passage"])
    total = float(r.choice([180, 250, 450, 600, 1200]))
    meta = [("Facture n°", f"{jour.year}-{r.randint(1, 80):03d}"), ("Date", date_fr(jour, r)), ("Client", client)]
    tableau = [
        ["Prestation", "Qté", "Prix unitaire", "Total"],
        ["Création graphique", "1", montant_fr(total, r, ["espace"]), montant_fr(total, r, ["espace"])],
    ]
    totaux = [("Total", montant_fr(total, r))]
    paragraphes = ["TVA non applicable, art. 293 B du CGI.", "Paiement à 30 jours par virement."]
    doc = Doc([c.entreprise["nom"], "Micro-entrepreneur", f"SIRET {c.entreprise['siret']}"], "FACTURE", meta, [client],
              tableau, totaux, paragraphes, [])  # fmt: skip
    return doc, {"type": "facture_emise", "emetteur": c.entreprise["nom"], "date": iso(jour), "montant": euros(total)}


def garantie_notice(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    p = r.choice(DURABLES)
    if variante == "certificat":
        achat = c.jour()
        meta = [
            ("Produit", p.libelle),
            ("N° de série", f"SN{r.randint(10**8, 10**9)}"),
            ("Date d'achat", date_fr(achat, r, ["num"])),
        ]
        doc = Doc([p.marque.upper(), "Service consommateurs"], "CERTIFICAT DE GARANTIE", meta, [], [], [],
                  [f"Ce produit {p.marque} est garanti 2 ans à compter de la date d'achat, pièces et main-d'œuvre.",
                   "Conservez ce certificat avec votre preuve d'achat."], [])  # fmt: skip
        return doc, {"type": "garantie_notice", "emetteur": p.marque, "date": iso(achat), "montant": None}
    doc = Doc([p.marque.upper()], f"NOTICE D'UTILISATION — {p.libelle}", [], [], [], [],
              ["Consignes de sécurité : lisez attentivement cette notice avant la première utilisation.",
               "Mise en service : branchez l'appareil et appuyez sur le bouton marche.",
               "Entretien : nettoyez avec un chiffon sec. Garantie : voir conditions jointes."], [])  # fmt: skip
    return doc, {"type": "garantie_notice", "emetteur": p.marque, "date": None, "montant": None}


def courrier_admin(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    r = c.r
    jour = c.jour()
    if variante == "caf":
        e = c.emetteurs["social"][0]
        nom, entete = e.nom, [e.entete, e.adresse]
        objet = "Objet : réexamen de vos droits"
        corps = ["Madame, Monsieur,", "Suite à la mise à jour de votre situation, nous avons réexaminé vos droits. "
                 "Vous trouverez ci-dessous le détail de nos calculs.", "Nous vous prions d'agréer nos salutations distinguées."]  # fmt: skip
    else:
        nom = r.choice(["Mairie de Rezé", "Préfecture de la Gironde", "URSSAF Aquitaine"])
        entete = [nom, "Service des affaires générales"]
        objet = r.choice(["Objet : inscription sur les listes électorales", "Objet : demande de pièces complémentaires",
                          "Objet : votre dossier n° " + str(r.randint(10**5, 10**6))])  # fmt: skip
        corps = ["Madame, Monsieur,", "Nous accusons réception de votre demande. Afin de poursuivre l'instruction de "
                 "votre dossier, merci de nous transmettre les pièces listées ci-dessous.",
                 "Veuillez agréer, Madame, Monsieur, l'expression de nos salutations distinguées."]  # fmt: skip
    doc = Doc(entete, objet, [("", f"{r.choice(['Bordeaux', 'Nantes', 'Paris'])}, le {date_fr(jour, r, ['long', 'num'])}")],
              c.moi.lignes, [], [], corps, [], lettre=True)  # fmt: skip
    return doc, {"type": "courrier_admin", "emetteur": nom, "date": iso(jour), "montant": None}


def autre(c: Contexte, variante: str) -> tuple[Doc, dict[str, Any]]:
    sujets = {
        "recette": ("Recette : tarte aux pommes", ["Ingrédients : 4 pommes, une pâte brisée, 50 g de sucre, 30 g de beurre.",
                                                   "Préchauffer le four à 180 °C. Éplucher les pommes, les couper en lamelles.",
                                                   "Disposer sur la pâte, saupoudrer de sucre, cuire 35 minutes."]),
        "programme": ("Fête de quartier — programme", ["14 h : jeux pour enfants sur la place.", "16 h : concours de "
                                                       "pétanque.", "19 h : repas partagé, chacun apporte un plat."]),
        "liste": ("À faire ce week-end", ["Ranger le garage.", "Appeler grand-mère.", "Réparer la roue du vélo.",
                                          "Trier les vêtements d'hiver."]),
    }  # fmt: skip
    titre, lignes = sujets[variante]
    doc = Doc([], titre, [], [], [], [], lignes, [])
    return doc, {"type": "autre", "emetteur": None, "date": None, "montant": None}


FABRIQUES: dict[str, tuple[Fabrique, list[str]]] = {
    "facture_achat": (
        facture_achat,
        [
            "neuf",
            "mention_2ans",
            "extension_3ans",
            "constructeur_12",
            "occasion",
            "occasion_mention",
            "consommables",
            "mixte",
            "en_ligne",
            "29fevrier",
        ],
    ),
    "ticket_caisse": (ticket_caisse, ["courses", "durable_magasin"]),
    "facture_service": (facture_service, ["energie", "telecom"]),
    "releve_bancaire": (releve_bancaire, ["standard"]),
    "avis_imposition": (avis_imposition, ["revenu", "fonciere"]),
    "quittance_loyer": (quittance_loyer, ["agence", "particulier"]),
    "bail_contrat": (bail_contrat, ["bail", "prestation"]),
    "attestation": (attestation, ["scolarite", "assurance", "caf", "employeur"]),
    "bulletin_paie": (bulletin_paie, ["standard"]),
    "assurance": (assurance, ["echeance", "conditions"]),
    "billet_transport": (billet_transport, ["standard"]),
    "reservation": (reservation, ["standard"]),
    "sante": (sante, ["ameli", "mutuelle", "ordonnance"]),
    "identite": (identite, ["cni", "passeport", "permis"]),
    "devis": (devis, ["standard"]),
    "facture_emise": (facture_emise, ["standard"]),
    "garantie_notice": (garantie_notice, ["certificat", "notice"]),
    "courrier_admin": (courrier_admin, ["caf", "administration"]),
    "autre": (autre, ["recette", "programme", "liste"]),
}

__all__ = ["FABRIQUES", "Contexte", "MOIS", "personne"]
