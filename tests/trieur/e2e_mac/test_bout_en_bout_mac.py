"""§10 · Le bout en bout sur ton vrai Mac, dans un bac à sable, avec le vrai Vision, les vrais tags, alias et
Rappels (liste « Trieur-TEST »), et un vrai dossier iCloud « BoiteMac-TEST ».

    cd ~/Assistant && .venv/bin/python -m pytest tests/trieur/e2e_mac -q -s

Rien n'est écrit ailleurs que dans ~/TrieurSandbox, iCloud Drive/BoiteMac-TEST et la liste Trieur-TEST. Ces trois-là
ne doivent pas exister avant (sinon le test s'arrête sans rien toucher) ; ils sont supprimés à la fin, même en cas
d'échec, puis une vérification confirme qu'il ne reste rien. Aucune connexion réseau (Claude est coupé).
Ailleurs que sur macOS, ce test échoue franchement (il n'est jamais sauté).
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

from modules.trieur import config, daemon, traitement
from modules.trieur.classement import classer
from modules.trieur.extraction import extraire, ocr
from modules.trieur.garanties.coffre import LISTE_TEST

ICLOUD = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs"
BAC = Path.home() / "TrieurSandbox"
BOITE_TEST = ICLOUD / "BoiteMac-TEST"


def _osascript(script: str) -> str:
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=60)
    return r.stdout.strip() if r.returncode == 0 else f"ERREUR {r.stderr.strip()}"


def _liste_existe() -> bool:
    return _osascript(f'tell application "Reminders" to exists list "{LISTE_TEST}"') == "true"


def _empreinte(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_bout_en_bout_sur_le_mac() -> None:
    assert sys.platform == "darwin", "ce test ne tourne que sur le Mac (il n'est jamais sauté)"
    assert ICLOUD.is_dir(), "iCloud Drive n'est pas activé sur ce Mac"
    deja = [str(p) for p in (BAC, BOITE_TEST) if p.exists()] + (["liste Trieur-TEST"] if _liste_existe() else [])
    assert not deja, f"déjà présents (je n'y touche pas) : {deja}"
    rappels: list[str] = []
    try:
        _derouler(rappels)
    finally:
        from modules.trieur.systeme import Mac

        for identifiant in rappels:
            Mac().rappel_supprimer(LISTE_TEST, identifiant)
        if _liste_existe():
            _osascript(f'tell application "Reminders" to delete list "{LISTE_TEST}"')
        shutil.rmtree(BAC, ignore_errors=True)
        shutil.rmtree(BOITE_TEST, ignore_errors=True)
        restes = [str(p) for p in (BAC, BOITE_TEST) if p.exists()] + (["liste Trieur-TEST"] if _liste_existe() else [])
        print(f"\nNettoyage : {'rien ne reste' if not restes else restes}")
        assert not restes


def _derouler(rappels: list[str]) -> None:
    from modules.trieur import natif
    from modules.trieur.entrees import finder
    from modules.trieur.systeme import Mac
    from tests.trieur.corpus.generer import generer

    reglages = config.pour_le_bac_a_sable(BAC, {"chemins": {"icloud": str(ICLOUD), "boite": "BoiteMac-TEST"}})
    BOITE_TEST.mkdir()
    corpus = generer(BAC / "corpus")
    par_nom = corpus.par_fichier()

    # 1. Vision : les temps du §9 (sans cache).
    moteur = ocr.choisir()
    assert moteur is not None and moteur.nom == "vision", f"Vision indisponible : {moteur}"
    pdf_texte = next(v for v in corpus.verites if v.support == "pdf_texte" and v.type == "facture_achat")
    photo = next(v for v in corpus.verites if v.support == "photo_ticket")
    for v, budget in ((pdf_texte, 3.0), (photo, 8.0)):
        debut = time.perf_counter()
        e = extraire(corpus.dossier / v.fichier, moteur, BAC / "travail")
        c = classer(e.texte, reglages)
        duree = time.perf_counter() - debut
        print(f"{v.support} : {duree:.2f} s → {c.type} ({c.confiance:.2f}), attendu {v.type}")
        assert duree < budget

    # 2. HEIC par sips (l'iPhone envoie du HEIC).
    heic = BAC / "photo-test.heic"
    r = subprocess.run(["sips", "-s", "format", "heic", str(corpus.dossier / photo.fichier), "--out", str(heic)],
                       capture_output=True, text=True, timeout=60)  # fmt: skip
    assert r.returncode == 0 and heic.exists(), r.stderr

    # 3. La chaîne complète : la boîte iCloud et « À trier », le vrai Mac (tags, alias, Rappels), sans Claude.
    systeme = Mac()
    o = traitement.outils(reglages, systeme_=systeme, moteur=moteur, ia=None)
    d = daemon.Demon(reglages, outils=o)
    d.demarrer()
    choisis = [v for v in corpus.verites if v.support in ("pdf_texte", "scan_jpg", "photo_ticket")][:10]
    deposes: dict[Path, str] = {}
    for i, v in enumerate(choisis):
        cible = (BOITE_TEST if i % 2 == 0 else config.chemin(reglages, "a_trier")) / v.fichier
        shutil.copyfile(corpus.dossier / v.fichier, cible)
        deposes[cible] = _empreinte(cible)
    shutil.copyfile(heic, BOITE_TEST / heic.name)
    deposes[BOITE_TEST / heic.name] = _empreinte(heic)
    fin = time.time() + 180
    while time.time() < fin and len([e for e in o.base.derniers(100) if e.etat not in ("en_attente", "en_cours")]) \
            < len(deposes):  # fmt: skip
        d.tour()
        time.sleep(1)
    elements = o.base.derniers(100)
    for e in elements:
        print(
            f"  n°{e.id} {e.nom} → {e.etat} {e.type} {e.confiance} {Path(e.destination).name if e.destination else ''}"
        )
    assert len(elements) == len(deposes) and all(e.etat in ("classe", "a_verifier", "photos") for e in elements)
    justes = sum(1 for e in elements if e.nom in par_nom and e.type == par_nom[e.nom].type)
    print(f"types justes : {justes}/{len(choisis)}")
    assert justes >= len(choisis) - 1
    classe = next(e for e in elements if e.etat == "classe")
    tags = natif.lire_tags(Path(classe.destination))
    print(f"tags Finder : {tags}")
    assert tags
    fiches = o.coffre.fiches()
    for f in fiches:
        rappels.extend(f.rappels)
    print(f"garanties : {len(fiches)}, rappels dans {LISTE_TEST} : {len(rappels)}")
    if fiches:
        assert fiches[0].alias and Path(fiches[0].alias).exists()
        assert rappels and _liste_existe()
    assert (BOITE_TEST / "Mon coffre.html").exists()

    # 4. L'action rapide du Finder et les raccourcis : des plists valides (plutil), une signature.
    paquet = finder.installer(BAC / "Services", Path.cwd(), Path(sys.executable))
    for f in ("Info.plist", "document.wflow"):
        r = subprocess.run(["plutil", "-lint", str(paquet / "Contents" / f)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
    from modules.trieur import raccourcis

    brouillons = raccourcis.ecrire(BAC / "raccourcis")
    for b in brouillons:
        r = subprocess.run(["plutil", "-lint", str(b)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
    ok, erreur = raccourcis.signer(brouillons[0], BAC / "raccourcis" / "signe.shortcut")
    print(f"signature du raccourci : {'✅' if ok else '⚠️ ' + erreur}")

    # 5. Tout annuler : chaque fichier revient à sa place, identique.
    for e in elements:
        traitement.annuler(o, e.id)
    for chemin, empreinte in deposes.items():
        assert chemin.exists() and _empreinte(chemin) == empreinte, chemin.name
    assert o.coffre.fiches() == []
    d.arreter()
