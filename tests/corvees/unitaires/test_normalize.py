import pytest

from modules.corvees import normalize as n

MAISON = "/Users/moi"


@pytest.mark.parametrize(
    ("nom", "motif", "ext"),
    [
        ("Facture_2026-10-03.pdf", "Facture_*", "pdf"),
        ("Facture_2026-11-14.pdf", "Facture_*", "pdf"),
        ("Facture_2026-10-03 (1).pdf", "Facture_*", "pdf"),
        ("Facture_2026-10-03 copie.pdf", "Facture_*", "pdf"),
        ("IMG_4521.HEIC", "IMG_*", "heic"),
        ("IMG_20261003_143210.jpg", "IMG_*", "jpg"),
        ("Capture d’écran 2026-10-03 à 14.32.10.png", "Capture d’écran * à *", "png"),
        ("screen_12.png", "screen_*", "png"),
        ("rapport-9f86d081a2.docx", "rapport-*", "docx"),
        ("550e8400-e29b-41d4-a716-446655440000.json", "*", "json"),
        ("Releve_2026_10.pdf", "Releve_*", "pdf"),
        ("README", "README", ""),
        ("12.pdf", "*", "pdf"),
        ("archive.tar.gz", "archive.tar", "gz"),
        ("photo.jpeg_old_long_suffixe", "photo.jpeg_old_long_suffixe", ""),
    ],
)
def test_motif_des_noms_de_fichiers(nom, motif, ext):
    assert n.motif_nom(nom) == motif and n.extension(nom) == ext


def test_le_meme_rangement_donne_le_meme_token():
    a = n.tok_deplacement(f"{MAISON}/Downloads", f"{MAISON}/Documents/Factures", "Facture_2026-10-03.pdf", MAISON)
    b = n.tok_deplacement(f"{MAISON}/Downloads", f"{MAISON}/Documents/Factures", "Facture_2026-11-14.pdf", MAISON)
    assert a == b == "fmove:Downloads→Documents/Factures [pdf, Facture_*]"


def test_lieux_generalises():
    assert n.lieu(f"{MAISON}/Documents/Factures/2026", MAISON) == "Documents/Factures/*"
    assert n.lieu(f"{MAISON}/a/b/c/d/e/f", MAISON) == "a/b/c/d"
    assert n.lieu("/Volumes/Cle USB/2026", MAISON) == "/Volumes/Cle USB/*"
    assert n.lieu(MAISON, MAISON) == "~"
    assert n.lieu("~/Desktop") == "Desktop"


def test_autres_tokens_de_fichiers():
    assert n.tok_renommage(f"{MAISON}/Desktop", "Capture 2026-10-03.png", "screen_3.png", MAISON) == (
        "fren:Desktop [png, Capture *→screen_*]"
    )
    assert n.tok_creation(f"{MAISON}/Downloads", "Releve_2026_10.pdf", MAISON) == "fcreate:Downloads [pdf, Releve_*]"
    assert n.tok_conversion(f"{MAISON}/Downloads", "IMG_4521.HEIC", "IMG_4521.jpg", MAISON) == (
        "fconv:Downloads [heic→jpg, IMG_*]"
    )


@pytest.mark.parametrize(
    ("url", "attendu"),
    [
        ("https://mail.google.com/mail/u/0/#inbox", "mail.google.com/mail"),
        ("https://www.notion.so/Mon-espace-1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d", "notion.so"),
        ("https://calendar.google.com/calendar/u/0/r?tab=mc", "calendar.google.com/calendar"),
        ("https://moi:pass@www.site.fr:8443/page/12?x=1", "site.fr/page"),
        ("https://www.youtube.com/watch?v=abc", "youtube.com/watch"),
        ("https://exemple.fr/2026/10/article", "exemple.fr"),
        ("exemple.fr", "exemple.fr"),
    ],
)
def test_adresses_sans_parametres(url, attendu):
    assert n.url_normalisee(url) == attendu


def test_url_sur_deux_segments():
    assert n.url_normalisee("https://docs.google.com/document/d/1AbC/edit", segments=2) == "docs.google.com/document/d"
    assert n.tok_url("https://www.lemonde.fr/") == "url:lemonde.fr"


def test_commandes_normalisees():
    assert n.commande_normalisee("cd   /Users/moi/Projets/assistant &&  git pull", MAISON) == (
        "cd ~/Projets/assistant && git pull"
    )
    assert n.commande_normalisee("git checkout 9f86d081", MAISON) == "git checkout *"
    assert n.commande_normalisee("kill 48211", MAISON) == "kill *"
    assert n.commande_normalisee("python3 main.py", MAISON) == "python3 main.py"
    assert n.commande_normalisee("ls \\\n -la", MAISON) == "ls -la"
    assert n.tok_commande("git status", MAISON) == "cmd:git status"


def test_sous_commandes_avec_guillemets():
    assert n.sous_commandes("cd x && git pull ; make || echo 'a && b'") == ["cd x", "git pull", "make", "echo 'a && b'"]
    assert n.sous_commandes('git commit -m "x; y"') == ['git commit -m "x; y"']
    assert n.sous_commandes("ls ;; ") == ["ls"]


def test_autres_tokens():
    assert n.tok_app("Numbers") == "app:Numbers"
    assert n.tok_pont("Safari", "Numbers") == "clip:Safari→Numbers"
    assert n.tok_fenetre("Numbers", "Budget 2026.numbers") == "fen:Numbers:Budget *.numbers"
