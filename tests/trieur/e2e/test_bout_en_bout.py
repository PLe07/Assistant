"""§10 · De bout en bout dans un bac à sable : tout le corpus déposé dans les vraies entrées, le démon tourne avec
l'OCR de la machine (en cache) et un Claude imité ; puis tout est annulé.

Vérifié :
- 0 fichier perdu : chaque document déposé est quelque part (rangé, photos, À vérifier, laissé en place) ;
- 0 écrasement : des fichiers placés d'avance aux noms que le Trieur va choisir sont intacts ;
- les types (mêmes seuils que le juge), les garanties, les rappels dans la liste de test, les pages ;
- annuler tout : chaque fichier revient à sa place d'origine, octet pour octet.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from core.cerveau import Reponse
from modules.trieur import config, daemon, traitement
from modules.trieur.ia import CoucheIA
from tests.trieur.corpus.juge import IDENTITE, moteur_des_tests
from tests.trieur.outils import FauxSysteme


def _empreinte(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


class Icloud(FauxSysteme):
    """Le fantôme iCloud est « téléchargé » : le vrai fichier apparaît à côté."""

    def __init__(self, sources: Path):
        super().__init__()
        self.sources = sources

    def telecharger_icloud(self, chemin: Path) -> bool:
        super().telecharger_icloud(chemin)
        vrai = self.sources / chemin.name
        if vrai.exists() and not chemin.exists():
            shutil.copyfile(vrai, chemin)
        return True


def test_tout_le_corpus_puis_tout_annuler(corpus1, reglages, tmp_path):
    reglages["identite"] = IDENTITE
    boite, a_trier = config.chemin(reglages, "boite"), config.chemin(reglages, "a_trier")
    systeme = Icloud(corpus1.dossier / ".sources")
    o = traitement.outils(reglages, systeme_=systeme, moteur=moteur_des_tests(), ia=None)
    claude: list[str] = []
    rien = {"type": "autre", "confiance": 0.2, "emetteur": None, "date": None, "montant": None, "detail": ""}
    o.ia = CoucheIA(reglages, o.base, demander=lambda m, **k: claude.append(m) or Reponse("", rien, 500, 30))
    d = daemon.Demon(reglages, outils=o)
    notifications: list[tuple[str, str]] = []
    d.notifieur.envoyer = lambda t, m: notifications.append((t, m))  # type: ignore[method-assign]
    d.demarrer()

    # Des fichiers déjà là, aux noms que le Trieur choisira : ils ne doivent jamais être écrasés.
    occupes = {
        o.classes / "Factures/2026/2026-01-14_Ikea_Facture_iPhone-17128Go_987,50€.pdf": b"deja la 1",
        o.classes / "Banque/LCL/2025/2025-06-30_LCL_Relevé.pdf": b"deja la 2",
    }
    for chemin, contenu in occupes.items():
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(contenu)

    # Le dépôt : les photos et un tiers des PDF par la boîte iCloud, le reste dans « À trier ».
    deposes: dict[Path, str] = {}
    for i, v in enumerate(corpus1.verites):
        source = corpus1.dossier / v.fichier
        if not source.exists():
            continue
        vers = boite if (v.support != "pdf_texte" or i % 3 == 0 or v.fichier.startswith(".")) else a_trier
        cible = vers / v.fichier
        shutil.copyfile(source, cible)
        if not v.fichier.endswith(".icloud"):
            deposes[cible] = _empreinte(cible)
    deposes[boite / "Facture-en-ligne.pdf"] = _empreinte(corpus1.dossier / ".sources" / "Facture-en-ligne.pdf")

    for _ in range(12):
        d.tour()
    d.notifieur.vider(forcer=True)
    elements = o.base.derniers(500)
    comptes = o.base.compter()

    # 0 perdu : chaque fichier déposé a été rangé quelque part, ou laissé exprès.
    restants = sorted(p.name for p in list(boite.iterdir()) + list(a_trier.iterdir())
                      if p.is_file() and not p.name.endswith(".html") and not p.name.startswith("."))  # fmt: skip
    assert restants == []
    destinations = [Path(e.destination) for e in elements if e.destination]
    assert all(p.exists() for p in destinations)
    assert sum(1 for e in elements if e.parent is None) == len(deposes)
    # 0 écrasement.
    assert all(chemin.read_bytes() == contenu for chemin, contenu in occupes.items())
    assert any(p.name.endswith("_987,50€-2.pdf") for p in destinations)
    # Ce qui a été fait, en gros : les mêmes résultats que le juge.
    assert comptes.get("classe", 0) >= 110 and comptes.get("photos", 0) == 2 and comptes.get("doublon", 0) == 1
    assert comptes.get("erreur", 0) == 0 and comptes.get("en_attente", 0) == 0
    assert len(o.coffre.fiches()) >= 32 and systeme.alias
    assert {liste for liste, *_ in systeme.rappels.values()} == {"Trieur-TEST"}  # jamais la vraie liste
    assert (boite / "Mon coffre.html").exists() and (boite / "Derniers classements.html").exists()
    assert notifications and len(notifications) < 20  # regroupées
    assert systeme.telecharges  # le fantôme a été demandé à iCloud

    # Tout annuler : chaque fichier revient à sa place, identique.
    for e in reversed(elements):
        if e.etat in ("classe", "a_verifier", "photos", "doublon") and o.base.actions(e.id):
            traitement.annuler(o, e.id)
    for chemin, empreinte in deposes.items():
        assert chemin.exists() and _empreinte(chemin) == empreinte, chemin.name
    assert o.coffre.fiches() == [] and systeme.rappels == {}
    assert all(chemin.read_bytes() == contenu for chemin, contenu in occupes.items())
    restes = [p for p in o.classes.rglob("*") if p.is_file() and p not in occupes]
    assert restes == [], restes[:5]
    d.arreter()
