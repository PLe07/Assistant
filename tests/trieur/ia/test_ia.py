"""La couche IA avec un Claude imité : caviardage, documents sensibles, schéma et relance, pannes, budget."""

from __future__ import annotations

import random
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from core.cerveau import ClaudeIndisponible, Reponse
from modules.trieur import traitement
from modules.trieur.base import Base
from modules.trieur.classement import classer
from modules.trieur.extraction import Extraction
from modules.trieur.ia import CoucheIA, Refuse, construire, couche, est_sensible, noms_du_compte
from modules.trieur.ia.caviardage import caviarder, luhn
from tests.trieur.corpus.donnees import personne
from tests.trieur.outils import DEVIS_AMBIGU, FauxOCR, pdf

BON = {"type": "devis", "confiance": 0.92, "emetteur": "Plomberie Martin", "date": "2026-10-05", "montant": 528.0,
       "detail": "chauffe-eau"}  # fmt: skip


class Espion:
    """Joue Claude : rend les réponses prévues dans l'ordre et garde chaque message reçu."""

    def __init__(self, *reponses):
        self.reponses = list(reponses)
        self.messages: list[str] = []
        self.options: list[dict] = []

    def __call__(self, message, **options):
        self.messages.append(message)
        self.options.append(options)
        r = self.reponses.pop(0) if self.reponses else BON
        if isinstance(r, Exception):
            raise r
        return Reponse("", r, 900, 60)


@pytest.fixture
def base(tmp_path):
    b = Base(tmp_path / "t.db")
    yield b
    b.fermer()


def _el(base, nom="doc.pdf"):
    return base.element(base.ajouter(Path(f"/x/{nom}"), "cli"))


def test_caviardage_des_donnees_personnelles():
    p = personne(random.Random(7))
    texte = (f"{p.prenom} {p.nom}\n{p.adresse}\n{p.ville}\n{p.courriel} {p.telephone}\nIBAN : {p.iban}\n"
             f"Carte : {p.carte}\nN° de sécurité sociale : {p.nir}\nNuméro fiscal : 30 12 345 678 901\n"
             f"Titulaire : {p.prenom} {p.nom}\nTotal TTC 249,99 € le 03/10/2026")  # fmt: skip
    sortie = caviarder(texte)
    for secret in (p.courriel, p.telephone, p.iban, p.carte, p.nir, p.adresse, p.ville, p.nom, "30 12 345 678 901"):
        assert secret not in sortie, secret
    assert "249,99 €" in sortie and "03/10/2026" in sortie and "[carte]" in sortie and "[n° sécu]" in sortie
    assert caviarder("Camille Martin a payé", mots=["Camille Martin"]) == "[nom] a payé"
    assert len(caviarder("x" * 5000, longueur_max=3000)) == 3000
    assert luhn("4970101234567893") and not luhn("4970101234567890")
    assert caviarder("Nombre de parts : 1") == "Nombre de parts : 1"


def test_documents_sensibles_jamais_envoyes(reglages):
    sensibles = reglages["ia"]["types_sensibles"]
    assert est_sensible("ORDONNANCE\nParacétamol", classer("ORDONNANCE\nParacétamol 1 g", reglages), sensibles)
    assert est_sensible("x", None, sensibles) is None
    assert "sécurité sociale" in est_sensible("n° 1 85 05 78 006 084 36", None, sensibles)
    assert "indice" in est_sensible("Votre numéro fiscal", None, sensibles)
    c = classer(DEVIS_AMBIGU, reglages)
    assert est_sensible(DEVIS_AMBIGU, c, sensibles) is None


def test_reponse_valide_et_classement(reglages, base):
    espion = Espion(BON)
    ia = CoucheIA(reglages, base, demander=espion)
    local = classer(DEVIS_AMBIGU, reglages)
    assert local.confiance < 0.75
    c = ia.classer(Extraction("pdf", DEVIS_AMBIGU), local, _el(base))
    assert (c.type, c.source, c.emetteur, c.date, c.montant) == (
        "devis",
        "ia",
        "Plomberie Martin",
        date(2026, 10, 5),
        Decimal("528.00"),
    )
    assert espion.options[0]["modele"] == "rapide" and espion.options[0]["schema"]["required"]
    assert "PROPOSITION" in espion.messages[0] and "[adresse]" in espion.messages[0]
    assert "Plomberie" not in espion.messages[0]  # le nom au-dessus d'une adresse est masqué (une personne ?)
    assert 0 < ia.depense_du_mois() < 0.01


def test_relance_si_le_format_ne_colle_pas(reglages, base):
    mauvais = dict(BON, type="facture_inconnue")
    espion = Espion(mauvais, BON)
    ia = CoucheIA(reglages, base, demander=espion)
    assert ia.demander(DEVIS_AMBIGU, 1)["type"] == "devis" and len(espion.messages) == 2
    assert "ne respectait pas le format" in espion.messages[1]
    espion2 = Espion(mauvais, dict(BON, date="2026-02-30"))
    with pytest.raises(Refuse, match="hors format"):
        CoucheIA(reglages, base, demander=espion2).demander(DEVIS_AMBIGU, 1)
    assert CoucheIA.valider("pas un objet") == (None, ["pas d'objet JSON"])


def test_pannes_passageres_et_definitives(reglages, base):
    attentes: list[float] = []
    espion = Espion(ClaudeIndisponible("surcharge (529)"), ClaudeIndisponible("trop de demandes (429)"), BON)
    ia = CoucheIA(reglages, base, demander=espion, dormir=attentes.append)
    assert ia.demander(DEVIS_AMBIGU, 1)["type"] == "devis" and attentes == [2, 4]
    espion = Espion(ClaudeIndisponible("Jeton Claude absent du .env"), BON)
    with pytest.raises(Refuse, match="Jeton"):
        CoucheIA(reglages, base, demander=espion, dormir=attentes.append).demander(DEVIS_AMBIGU, 1)
    assert len(espion.messages) == 1
    toujours = Espion(*[ClaudeIndisponible("surcharge")] * 3)
    with pytest.raises(Refuse):
        CoucheIA(reglages, base, demander=toujours, dormir=lambda s: None).demander(DEVIS_AMBIGU, 1)
    assert len(toujours.messages) == 3


def test_budget_et_desactivation(reglages, base):
    reglages["ia"]["budget_mensuel_usd"] = 0.0001
    espion = Espion(BON)
    with pytest.raises(Refuse, match="budget"):
        CoucheIA(reglages, base, demander=espion).demander(DEVIS_AMBIGU, 1)
    assert espion.messages == []
    reglages["ia"]["actif"] = False
    with pytest.raises(Refuse, match="désactivée"):
        CoucheIA(reglages, base, demander=espion).demander(DEVIS_AMBIGU, 1)
    assert couche(reglages, base) is None


def test_claude_dit_sensible_ou_rien(reglages, base):
    ia = CoucheIA(reglages, base, demander=Espion(dict(BON, type="sante")))
    assert ia.classer(Extraction("pdf", DEVIS_AMBIGU), classer(DEVIS_AMBIGU, reglages), _el(base)) is None
    assert ia.classer(Extraction("pdf", "  "), None, _el(base)) is None
    ia_panne = CoucheIA(reglages, base, demander=Espion(ClaudeIndisponible("Jeton absent")))
    assert ia_panne.classer(Extraction("pdf", DEVIS_AMBIGU), None, _el(base)) is None
    autre = construire(
        dict(BON, type="autre", emetteur="X", montant=None, date=None, detail=""), "rien", None, reglages, None
    )
    assert autre.emetteur is None and autre.date is None
    sans_date = construire(dict(BON, type="facture_achat"), "Total TTC 12,00 €", None, reglages, None)
    assert sans_date.date == date(2026, 10, 5) and sans_date.montant == Decimal("12.00")  # le texte d'abord


def test_dans_la_chaine(reglages, faux_mac):
    espion = Espion(BON)
    o = traitement.outils(reglages, systeme_=faux_mac, moteur=FauxOCR(), ia=None)
    o.ia = CoucheIA(reglages, o.base, demander=espion)
    boite = Path(reglages["chemins"]["icloud"]) / "BoiteMac"
    el = traitement.traiter(o, o.base.ajouter(pdf(boite / "a.pdf", DEVIS_AMBIGU), "boite"))
    assert el.etat == "classe" and el.par == "ia" and el.type == "devis" and "/Devis/2026/" in el.destination
    sante = pdf(boite / "b.pdf", "Cabinet du Dr Durand\nPatient : Camille\nConsultation 30,00 €\nLe 03/10/2026")
    el2 = traitement.traiter(o, o.base.ajouter(sante, "boite"))
    assert el2.etat == "a_verifier" and len(espion.messages) == 1  # jamais envoyé
    o.base.fermer()


def test_nom_du_compte(monkeypatch):
    import pwd

    class Faux:
        pw_gecos = "Camille Dupont,,,"

    monkeypatch.setattr(pwd, "getpwuid", lambda _: Faux())
    assert noms_du_compte() == ["Camille Dupont", "Camille", "Dupont"]
    Faux.pw_gecos = "root"
    assert noms_du_compte() == []
    monkeypatch.setattr(pwd, "getpwuid", lambda _: (_ for _ in ()).throw(KeyError("x")))
    assert noms_du_compte() == []


@pytest.mark.live
def test_vrai_claude_un_devis(reglages, base):
    """Un vrai appel (moins d'un centime) : python -m pytest -m live tests/trieur/ia/test_ia.py"""
    ia = CoucheIA(reglages, base)
    d = ia.demander(DEVIS_AMBIGU, None)
    assert d["type"] in ("devis", "facture_achat") and 0 <= d["confiance"] <= 1
    assert ia.depense_du_mois() < 0.01
