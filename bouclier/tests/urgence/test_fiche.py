"""§11.5 : chaque numéro est dans sources.json (URL officielle et date) ; le PDF contient tous les numéros ; le HTML
n'a aucune ressource extérieure ; la carte A6 tient sur une page ; les champs vides n'apparaissent pas ; pas de
données de santé ; revérification en ligne et rappel des 6 mois."""

from __future__ import annotations

import datetime as dt
import io
import re
from collections.abc import Sequence
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from bouclier import cli, config, db, reseau
from bouclier.notifier import Notifieur
from bouclier.systeme import Resultat, Systeme
from bouclier.urgence import ecran_verrouille, fiche, infos, service, sources

JOUR = dt.date(2026, 10, 6)
MES_INFOS = """
nom = "Camille Martin"
[[contacts]]
nom = "Julie (sœur)"
telephone = "06 11 22 33 44"
[[contacts]]
nom = ""
telephone = ""
[operateur]
nom = "Free"
service_client = ""
[banque]
nom = "La Banque Postale"
numero_carte_perdue = "09 69 39 99 98"
[ecran_verrouille]
texte = ""
"""


def _texte_pdf(donnees: bytes) -> tuple[str, int]:
    lecteur = PdfReader(io.BytesIO(donnees))
    return "\n".join(p.extract_text() or "" for p in lecteur.pages), len(lecteur.pages)


def _compact(texte: str) -> str:
    return re.sub(r"(?<=\d)\s+(?=\d)", "", texte)


@pytest.fixture
def chemins(maison: Path) -> config.Chemins:
    c = config.chemins()
    c.support.mkdir(parents=True)
    c.icloud_drive.mkdir(parents=True)
    return c


def test_generer_tout(chemins: config.Chemins) -> None:
    chemins.infos_urgence.write_text(MES_INFOS, encoding="utf-8")
    base = db.ouvrir(chemins.base)
    s = service.generer(chemins, base, JOUR)
    registre = sources.charger()
    f = service.construire_fiche(chemins, JOUR)

    # Chaque numéro et site affiché est dans sources.json, avec des pages officielles et une date.
    for ligne in f.lignes():
        e = registre.element(ligne.id)
        assert e.sources and all(reseau.est_officiel(re.sub(r"^https://([^/]+)/.*$", r"\1", registre.sources[i].url))
                                 for i in e.sources)  # fmt: skip
    assert registre.verifie_le and {ligne.id for ligne in f.lignes()} >= {n.id for n in registre.numeros}

    # Le HTML : autonome, tous les numéros, pas les champs vides.
    page = s.html.read_text(encoding="utf-8")
    assert not re.search(r"<(script|img|link|iframe|object|embed|video|audio|source)\b", page, re.I)
    assert not re.search(r"\b(src|srcset)\s*=", page, re.I) and "@import" not in page and "url(" not in page
    for n in registre.numeros:
        assert n.numero in page, n.numero
    assert "Camille Martin" in page and "Julie (sœur)" in page and "09 69 39 99 98" in page
    assert "Mon opérateur" not in page  # numéro de l'opérateur vide : la ligne n'existe pas
    assert page.count("<tr>") == len(f.lignes()) + 2

    # Le PDF : tous les numéros, sans réseau.
    texte, _ = _texte_pdf(s.pdf.read_bytes())
    for n in registre.numeros:
        assert sources.chiffres(n.numero) in _compact(texte), n.numero
    assert "Julie" in texte and "Fiche médicale" in texte

    # La carte A6 : une seule page, au bon format, avec les numéros essentiels.
    carte, pages = _texte_pdf(s.carte.read_bytes())
    lecteur = PdfReader(io.BytesIO(s.carte.read_bytes()))
    assert pages == 1 and round(float(lecteur.pages[0].mediabox.width)) == 298
    for i in ("samu", "pompiers", "urgence-europe", "opposition", "antipoison-bordeaux"):
        assert sources.chiffres(registre.numero(i).numero) in _compact(carte), i
    assert "0611223344" in _compact(carte)

    # L'écran verrouillé et la copie iCloud.
    assert s.ecran is not None
    with Image.open(s.ecran) as img:
        assert img.size == ecran_verrouille.TAILLE
    assert s.icloud == chemins.icloud / "Fiche urgence.pdf" and s.icloud.read_bytes() == s.pdf.read_bytes()
    assert base.lire_meta("fiche_generee_le") and s.avertissements == []
    assert (s.pdf.stat().st_mode & 0o777) == 0o600


def test_sans_infos_et_sans_icloud(maison: Path) -> None:
    c = config.chemins()
    s = service.generer(c, None, JOUR)
    page = s.html.read_text(encoding="utf-8")
    assert "Mes contacts" not in page and s.ecran is None and s.icloud is None
    assert "iCloud Drive introuvable" in s.avertissements[0]


def test_pas_de_donnees_de_sante(chemins: config.Chemins) -> None:
    chemins.infos_urgence.write_text('nom = "Camille, allergique à la pénicilline"\n[ecran_verrouille]\n'
                                     'texte = "Groupe sanguin O+ ; appeler Julie"\n', encoding="utf-8")  # fmt: skip
    s = service.generer(chemins, None, JOUR)
    page = s.html.read_text(encoding="utf-8")
    assert "pénicilline" not in page and "O+" not in page and s.ecran is None
    assert any("pas de données de santé" in a for a in s.avertissements)
    assert infos.charger(chemins.infos_urgence).ecartes == ["nom", "écran verrouillé"]


def test_infos_abimees_et_modele(chemins: config.Chemins) -> None:
    assert infos.ecrire_modele_si_absent(chemins.infos_urgence)
    assert not infos.ecrire_modele_si_absent(chemins.infos_urgence)
    assert infos.charger(chemins.infos_urgence).vide  # le modèle commenté est vide
    assert "Fiche médicale" in chemins.infos_urgence.read_text(encoding="utf-8")
    chemins.infos_urgence.write_text("nom = ", encoding="utf-8")
    s = service.generer(chemins, None, JOUR)
    assert any("ne se lit pas" in a for a in s.avertissements)


class FauxSites:
    def __init__(self, absents: set[str] = frozenset(), en_panne: bool = False) -> None:  # type: ignore[assignment]
        self.absents, self.en_panne = absents, en_panne

    def __call__(self, url: str, **_: object) -> reseau.Reponse:
        reseau.verifier_url(url)
        if self.en_panne:
            raise reseau.ErreurReseau("injoignable")
        r = sources.charger()
        morceaux = []
        for e in r.elements():
            if e.id in self.absents or not any(r.sources[s].url == url for s in e.sources):
                continue
            morceaux.append(" ".join(e.mots) + " " + getattr(e, "numero", getattr(e, "adresse", "")))
        return reseau.Reponse(200, (" — ".join(morceaux)).encode(), url)


class Notes:
    def __init__(self) -> None:
        self.envoyees: list[str] = []

    def notifier(self, titre: str, texte: str, sous_titre: str = "") -> bool:
        self.envoyees.append(f"{titre} | {texte}")
        return True


def _notifieur(base: db.Base) -> tuple[Notifieur, Notes]:
    notes = Notes()
    t = dt.datetime(2026, 10, 6, 14, 0).timestamp()
    return Notifieur(base, notes, config.charger(), horloge=lambda: t), notes  # type: ignore[arg-type]


def test_reverification_en_ligne(chemins: config.Chemins) -> None:
    base = db.ouvrir(chemins.base)
    notifieur, notes = _notifieur(base)
    r = service.verifier(chemins, base, notifieur, FauxSites(), JOUR)
    assert r.reverif.absents == [] and r.nouveaux_absents == [] and notes.envoyees == []
    f = service.construire_fiche(chemins, JOUR)
    assert f.verification.en_ligne and "Numéros vérifiés le 06/10/2026" in fiche.mention_verification(f)
    r = service.verifier(chemins, base, notifieur, FauxSites({"pharmacie-garde"}), JOUR)
    assert r.nouveaux_absents == ["pharmacie-garde"] and "un numéro a changé" in notes.envoyees[0]
    assert "3237" not in (chemins.sorties / "Fiche urgence.html").read_text(encoding="utf-8")
    service.verifier(chemins, base, notifieur, FauxSites({"pharmacie-garde"}), JOUR)
    assert len(notes.envoyees) == 1  # une seule alerte pour le même changement
    r = service.verifier(chemins, base, notifieur, FauxSites(en_panne=True), JOUR)
    assert r.reverif.pages_lues == 0 and "pharmacie-garde" in fiche.lire_verification(
        service.fichier_verification(chemins), sources.charger()).absents  # fmt: skip


def test_rappel_tous_les_6_mois(chemins: config.Chemins) -> None:
    base = db.ouvrir(chemins.base)
    notifieur, notes = _notifieur(base)
    t = [1_800_000_000.0]
    assert not service.rappel(base, notifieur, lambda: t[0])  # le premier passage pose la date
    t[0] += 100 * 86400
    assert not service.rappel(base, notifieur, lambda: t[0])
    t[0] += 90 * 86400
    assert service.rappel(base, notifieur, lambda: t[0]) and "Relis ta fiche urgence" in notes.envoyees[0]
    assert not service.rappel(base, notifieur, lambda: t[0] + 86400)


def test_cli_urgence(chemins: config.Chemins, capsys: pytest.CaptureFixture[str]) -> None:
    ouverts: list[list[str]] = []

    def executer(args: Sequence[str], entree: str | None, delai: float) -> Resultat:
        ouverts.append(list(args))
        return Resultat(0, "")

    mac = Systeme(executer, mac=True)
    assert cli.main(["urgence", "editer"], mac) == 0
    assert chemins.infos_urgence.exists() and "Fichier créé et ouvert" in capsys.readouterr().out
    assert cli.main(["urgence"], mac) == 0
    sortie = capsys.readouterr().out
    assert "Fiche urgence prête" in sortie and "Copiée sur iCloud" in sortie
    assert cli.main(["urgence", "ouvrir"], mac) == 0
    assert any("Fiche urgence.html" in " ".join(a) for a in ouverts)
    assert cli.main(["urgence", "verifier"], mac) == 1  # réseau coupé pendant les tests
    assert "ne répondent pas" in capsys.readouterr().out
