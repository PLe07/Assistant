"""Le gardien d'intégrité (§4.5) : référence, écarts (ajouté, modifié, supprimé), fichiers vivants ignorés, commit git,
« C'était moi, nouvelle référence », commande `git diff` à lancer soi-même, FSEvents. Et il ne modifie rien."""

from __future__ import annotations

import hashlib
import os
import plistlib
import subprocess
import time
from pathlib import Path

import pytest

from tableau import systeme
from tableau.analyse import integrite
from tableau.analyse.integrite import Gardien, Surveillance
from tableau.db import Base
from tableau.module import DefModule


class Horloge:
    def __init__(self, t: float = 1_800_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _git(dossier: Path, *args: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t"}
    env["GIT_COMMITTER_EMAIL"] = "t@t"
    subprocess.run(["git", "-C", str(dossier), *args], check=True, capture_output=True, env=env)


def photo(racine: Path) -> dict[str, tuple[str, int]]:
    """(sha256, mtime_ns) de chaque fichier : la preuve qu'on n'a rien touché."""
    resultat = {}
    for chemin in sorted(racine.rglob("*")):
        if chemin.is_file() and not chemin.is_symlink():
            st = chemin.stat()
            resultat[str(chemin)] = (hashlib.sha256(chemin.read_bytes()).hexdigest(), st.st_mtime_ns)
    return resultat


@pytest.fixture
def monde(tmp_path: Path) -> tuple[Path, Path, DefModule, DefModule]:
    """Le dépôt de l'assistant (deux modules dedans), son plist et ses réglages Application Support."""
    maison = tmp_path / "maison_gardien"
    depot = maison / "Assistant"
    (depot / "modules" / "trieur").mkdir(parents=True)
    (depot / "modules" / "trieur" / "classer.py").write_text("SEUIL = 0.75\n")
    (depot / "modules" / "trieur" / "trieur.db").write_bytes(b"vivant")
    (depot / "modules" / "trieur" / "__pycache__").mkdir()
    (depot / "modules" / "trieur" / "__pycache__" / "classer.pyc").write_bytes(b"x")
    (depot / "modules" / "corvees").mkdir(parents=True)
    (depot / "modules" / "corvees" / "main.py").write_text("print(1)\n")
    (depot / "logs").mkdir()
    (depot / "logs" / "assistant.log").write_text("ligne\n")
    (depot / "main.py").write_text("print('assistant')\n")
    _git(depot, "init", "-q")
    _git(depot, "add", "-A")
    _git(depot, "commit", "-qm", "départ")
    agents = maison / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    with open(agents / "com.exemple.trieur.plist", "wb") as f:
        plistlib.dump({"Label": "com.exemple.trieur", "ProgramArguments": ["/bin/true"]}, f)
    support = maison / "Library" / "Application Support" / "Trieur"
    support.mkdir(parents=True)
    (support / "config.toml").write_text("[ia]\nplafond = 1.0\n")
    (support / "etat.json").write_text('{"vivant": 1}\n')
    (support / "caches").mkdir()
    (support / "caches" / "x.json").write_text("{}")
    trieur = DefModule(
        id="trieur",
        nom="Trieur",
        labels=["com.exemple.trieur"],
        dossier_projet="~/Assistant",
        dossier_donnees="~/Library/Application Support/Trieur",
        perimetre_code=["modules/trieur", "main.py"],
    )
    assistant = DefModule(
        id="assistant", nom="Assistant", dossier_projet="~/Assistant", perimetre_code=["."],
        perimetre_exclu=["modules/trieur"],
    )  # fmt: skip
    return maison, depot, trieur, assistant


def gardien(maison: Path, base: Base, horloge: Horloge) -> Gardien:
    return Gardien(base, maison, maison / "Library" / "LaunchAgents", horloge)


def test_reference_puis_aucun_ecart(tmp_path: Path, monde: tuple[Path, Path, DefModule, DefModule]) -> None:
    maison, depot, trieur, _ = monde
    base = Base(tmp_path / "t.db")
    h = Horloge()
    g = gardien(maison, base, h)
    noms = sorted(n for n, _ in g.fichiers(trieur))
    assert noms == ["main.py", "modules/trieur/classer.py", "plist:com.exemple.trieur", "reglages:config.toml"]
    r = g.controler(trieur)
    assert r.reference_prise and r.fichiers == 4
    etat = g.etat("trieur")
    assert etat is not None and etat["ecarts"] == [] and etat["head"] and not etat["commit_change"]
    h.t += 1800
    r = g.controler(trieur)
    assert not r.reference_prise and r.ecarts == [] and r.commit is None


def test_ajout_modification_suppression(tmp_path: Path, monde: tuple[Path, Path, DefModule, DefModule]) -> None:
    maison, depot, trieur, _ = monde
    base = Base(tmp_path / "t.db")
    h = Horloge()
    g = gardien(maison, base, h)
    g.controler(trieur)
    (depot / "modules" / "trieur" / "classer.py").write_text("SEUIL = 0.10\n")
    (depot / "modules" / "trieur" / "nouveau.py").write_text("x = 1\n")
    (depot / "main.py").unlink()
    (maison / "Library" / "Application Support" / "Trieur" / "config.toml").write_text("[ia]\nplafond = 50.0\n")
    # Les fichiers vivants ne comptent pas : base, journaux, caches, état.
    (depot / "modules" / "trieur" / "trieur.db").write_bytes(b"autre")
    (depot / "logs" / "assistant.log").write_text("autre ligne\n")
    (maison / "Library" / "Application Support" / "Trieur" / "etat.json").write_text('{"vivant": 2}\n')
    h.t += 1800
    r = g.controler(trieur)
    assert [(e.chemin, e.genre) for e in r.ecarts] == [
        ("main.py", "supprimé"),
        ("modules/trieur/classer.py", "modifié"),
        ("modules/trieur/nouveau.py", "ajouté"),
        ("reglages:config.toml", "modifié"),
    ]
    assert r.ecarts[1].quand is not None and r.ecarts[0].quand is None
    assert r.commit is not None and r.commit["sujet"] == "départ" and len(r.commit["commit"]) >= 7
    etat = g.etat("trieur")
    assert etat is not None and len(etat["ecarts"]) == 4
    # « C'était moi, nouvelle référence » : plus d'écart, et rien n'a été restauré.
    assert g.prendre_reference(trieur) == 4
    assert g.controler(trieur).ecarts == []
    assert (depot / "modules" / "trieur" / "classer.py").read_text() == "SEUIL = 0.10\n"
    assert not (depot / "main.py").exists()


def test_meme_taille_meme_date_relu_une_fois_par_jour(
    tmp_path: Path, monde: tuple[Path, Path, DefModule, DefModule]
) -> None:
    """Un contenu changé sans que taille ni date ne bougent : vu au contrôle complet quotidien."""
    maison, depot, trieur, _ = monde
    base = Base(tmp_path / "t.db")
    h = Horloge()
    g = gardien(maison, base, h)
    g.controler(trieur)
    h.t += 60
    assert g.controler(trieur).ecarts == []  # premier contrôle : complet, la journée commence
    fichier = depot / "modules" / "trieur" / "classer.py"
    st = fichier.stat()
    fichier.write_text("SEUIL = 0.99\n")  # même taille
    os.utime(fichier, ns=(st.st_atime_ns, st.st_mtime_ns))
    h.t += 1800
    assert g.controler(trieur).ecarts == []  # rapide : taille, date et numéro identiques
    h.t += integrite.JOUR
    assert [e.genre for e in g.controler(trieur).ecarts] == ["modifié"]
    assert [e.genre for e in g.controler(trieur, complet=True).ecarts] == ["modifié"]


def test_perimetres_exclus_et_notre_dossier(
    tmp_path: Path, monde: tuple[Path, Path, DefModule, DefModule], monkeypatch: pytest.MonkeyPatch
) -> None:
    maison, depot, _, assistant = monde
    notre = depot / "tableau-de-bord"
    notre.mkdir()
    (notre / "nous.py").write_text("x\n")
    (depot / "lien.py").symlink_to(depot / "main.py")
    monkeypatch.setattr(integrite, "RACINE_TABLEAU", notre.resolve())
    g = gardien(maison, Base(tmp_path / "t.db"), Horloge())
    noms = sorted(n for n, _ in g.fichiers(assistant))
    assert noms == ["main.py", "modules/corvees/main.py"]  # ni trieur (autre module), ni nous, ni lien, ni vivants
    monkeypatch.setattr(integrite, "FICHIERS_MAX", 1)
    assert len(list(g.fichiers(assistant))) == 1
    # Un fichier unique comme périmètre, un dossier de projet absent.
    seul = DefModule(id="s", nom="S", dossier_projet="~/Assistant", perimetre_code=["main.py"])
    assert [n for n, _ in g.fichiers(seul)] == ["main.py"]
    absent = DefModule(id="a", nom="A", dossier_projet="~/Nulle/Part", perimetre_code=["."])
    assert list(g.fichiers(absent)) == [] and g.controler(absent).fichiers == 0
    sans = DefModule(id="z", nom="Z")
    assert g.racine(sans) is None and g.commit(sans) is None
    assert g.commande_diff(sans) == "Pas de dossier de projet connu pour ce module."


def test_commit_qui_change_et_commande_diff(tmp_path: Path, monde: tuple[Path, Path, DefModule, DefModule]) -> None:
    maison, depot, trieur, _ = monde
    base = Base(tmp_path / "t.db")
    h = Horloge()
    g = gardien(maison, base, h)
    g.controler(trieur)
    (depot / "modules" / "trieur" / "classer.py").write_text("SEUIL = 0.5\n")
    _git(depot, "commit", "-qam", "seuil plus bas")
    h.t += 1800
    r = g.controler(trieur)
    assert r.commit is not None and r.commit["sujet"] == "seuil plus bas"
    etat = g.etat("trieur")
    assert etat is not None and etat["commit_change"]
    commande = g.commande_diff(trieur)
    assert commande == "cd ~/Assistant && git status && git diff -- 'modules/trieur' 'main.py'"
    sans_git = DefModule(id="p", nom="P", dossier_projet="~/Library/Application Support/Trieur", perimetre_code=["."])
    assert g.commande_diff(sans_git) == "cd ~/Library/Application Support/Trieur && ls -la"
    # git en échec ou muet : pas de commit, pas de plantage.
    muet = Gardien(base, maison, maison / "Library" / "LaunchAgents", h, lambda a: systeme.Resultat(1, "", "non"))
    assert muet.commit(trieur) is None and muet._head(trieur) is None
    # Un état illisible en base ne fait pas planter la page.
    base.executer("UPDATE integrite_etat SET ecarts = 'pas du json' WHERE module = 'trieur'")
    etat = g.etat("trieur")
    assert etat is not None and etat["ecarts"] == []
    assert g.etat("inconnu") is None


def test_le_gardien_ne_modifie_rien(tmp_path: Path, monde: tuple[Path, Path, DefModule, DefModule]) -> None:
    """Empreinte avant/après de tout le monde imité, `.git` compris : identique (git lancé sans verrou d'index)."""
    maison, depot, trieur, assistant = monde
    avant = photo(maison)
    g = gardien(maison, Base(tmp_path / "t.db"), Horloge())
    for defn in (trieur, assistant):
        g.controler(defn)
        g.controler(defn, complet=True)
        g.commit(defn)
        g.commande_diff(defn)
    assert photo(maison) == avant
    for args in systeme.JOURNAL:
        if args[1][0] == "git":
            assert "--no-optional-locks" in args[1]


def test_surveillance_fsevents(tmp_path: Path, monde: tuple[Path, Path, DefModule, DefModule]) -> None:
    maison, depot, trieur, assistant = monde
    h = Horloge()
    g = gardien(maison, Base(tmp_path / "t.db"), h)
    s = Surveillance(h)
    # Les marques, sans observateur : trieur seul pour son code, assistant seul pour le sien, rien pour le vivant.
    s._perimetres = [(d.id, *Surveillance.perimetre(g, d)) for d in (trieur, assistant)]
    s.noter(str((depot / "modules" / "trieur" / "classer.py").resolve()))
    s.noter(str((depot / "modules" / "corvees" / "main.py").resolve()))
    s.noter(str((depot / "logs" / "assistant.log").resolve()))
    s.noter(str((depot / "modules" / "trieur" / "trieur.db").resolve()))
    s.noter("/ailleurs/fichier.py")
    assert s.a_controler(delai_s=20) == []  # on attend que la sauvegarde soit finie
    h.t += 30
    assert s.a_controler(delai_s=20) == ["assistant", "trieur"]
    assert s.a_controler(delai_s=20) == []
    assert Surveillance.perimetre(g, DefModule(id="x", nom="X")) == ([], [])
    # Le vrai observateur (inotify ici, FSEvents sur le Mac) : une écriture marque le module.
    assert s.demarrer(g, [DefModule(id="vide", nom="V")]) == 0
    try:
        assert s.demarrer(g, [trieur, assistant]) == 1  # un seul dossier suivi : le dépôt couvre tout
        (depot / "modules" / "trieur" / "classer.py").write_text("SEUIL = 0.2\n")
        limite = time.monotonic() + 10
        while time.monotonic() < limite:
            h.t += 60
            if "trieur" in s.a_controler(delai_s=0):
                break
            time.sleep(0.1)
        else:
            pytest.fail("FSEvents n'a rien signalé en 10 s")
    finally:
        s.arreter()
    s.arreter()
