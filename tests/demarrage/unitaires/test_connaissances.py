import json
import re

import pytest

from modules.demarrage.analyse import connaissances as kb
from modules.demarrage.modele import Declencheurs, Fiche

DEMANDES = ["Google Updater", "Microsoft AutoUpdate", "Adobe Creative Cloud", "Zoom", "Teams", "Spotify", "Discord",
            "Steam", "Epic", "Dropbox", "OneDrive", "Google Drive", "iCloud", "Logi Options", "Docker", "Ollama",
            "Raycast", "Alfred", "NordVPN", "CleanMyMac", "Grammarly", "Notion", "Slack", "WhatsApp", "VS Code",
            "JetBrains Toolbox", "Homebrew", "Bitdefender", "Avast"]  # fmt: skip


def test_au_moins_60_entrees_completes_en_francais():
    entrees = kb.lire()
    assert len(entrees) >= 60
    for e in entrees:
        assert e.motifs and e.nom and e.role.endswith(".") and e.effet.endswith(".")
        assert e.impact in kb.IMPACTS and e.recommandation in kb.RECOMMANDATIONS and e.categorie
    noms = " ".join(e.nom for e in entrees)
    manquants = [d for d in DEMANDES if d.casefold() not in noms.casefold().replace("visual studio code", "vs code")]
    assert manquants == []
    brut = kb.FICHIER.read_text(encoding="utf-8")
    assert "sudo" not in brut.casefold()
    assert json.loads(brut)["version"] == 1


@pytest.mark.parametrize(
    ("label", "programme", "nom"),
    [
        ("com.google.keystone.agent", None, "Google Updater (Keystone)"),
        (
            "x",
            "/Users/u/Library/Google/GoogleSoftwareUpdate/GoogleSoftwareUpdate.bundle/x",
            "Google Updater (Keystone)",
        ),
        ("com.microsoft.OneDriveStandaloneUpdater", None, "Mise à jour de OneDrive"),
        ("com.microsoft.OneDrive.FinderSync", None, "OneDrive"),
        ("com.docker.vmnetd", None, "Docker (réseau et socket)"),
        ("com.docker.helper", None, "Docker Desktop"),
        ("homebrew.mxcl.postgresql@16", None, "Service Homebrew"),
        ("US.ZOOM.UPDATER.LOGIN.CHECK", None, "Mise à jour de Zoom"),
        ("com.assistant.superviseur", None, "L'Assistant (c'est moi)"),
    ],
)
def test_correspondance_par_motif(label, programme, nom):
    trouve = kb.trouver(Fiche(id="i", label=label, source="agent_utilisateur", programme=programme))
    assert trouve is not None and trouve.nom == nom


def test_par_l_app_ou_les_bundles():
    f = Fiche(id="i", label="inconnu", source="ouverture", app_parente="/Applications/Slack.app")
    assert kb.trouver(f).nom == "Slack"
    f = Fiche(id="i", label="inconnu", source="agent_utilisateur", bundles_associes=["com.spotify.client"])
    assert kb.trouver(f).nom == "Spotify"
    assert kb.trouver(Fiche(id="i", label="com.zebre.agent", source="agent_utilisateur")) is None


def test_ordre_du_plus_precis_au_plus_general():
    """Une entrée plus générale ne doit pas masquer une entrée plus précise placée après elle."""
    entrees = kb.lire()
    for i, precise in enumerate(entrees):
        for generale in entrees[:i]:
            for motif in precise.motifs:
                exemple = re.sub(r"\\(.)", r"\1", motif.pattern).replace("^", "").replace("$", "").replace(".*", "x")
                if any(m.search(exemple) for m in generale.motifs) and generale.nom != precise.nom:
                    pytest.fail(f"« {generale.nom} » masque « {precise.nom} » ({exemple})")


def test_description_generique_honnete():
    f = Fiche(id="i", label="com.x", source="agent_utilisateur", programme="/opt/x/agent",
              declencheurs=Declencheurs(au_chargement=True))  # fmt: skip
    texte = kb.description_generique(f)
    assert "éditeur inconnu" in texte and "« agent »" in texte and "on ne devine pas" in texte
    f.editeur = "Exemple SAS"
    assert kb.description_generique(f).startswith("Un élément de Exemple SAS")
    casse = Fiche(id="i", label="c", source="agent_utilisateur", erreurs=["plist corrompu"])
    assert "illisible (plist corrompu)" in kb.description_generique(casse)
    vide = Fiche(id="i", label="v", source="ouverture")
    assert "ne dit pas quel programme" in kb.description_generique(
        vide
    ) and "ouverture de session" in kb.description_generique(vide)
