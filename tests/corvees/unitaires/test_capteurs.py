"""Les capteurs, chacun avec son imitation de macOS ou ses vrais fichiers de test."""

import os
import sqlite3
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

from modules.corvees import config
from modules.corvees.capteurs import construire
from modules.corvees.capteurs.apps import Apps
from modules.corvees.capteurs.base import Capteur, MemoireVive
from modules.corvees.capteurs.fenetres import Fenetres
from modules.corvees.capteurs.fichiers import Brut, Fichiers, Reconstructeur, cache, temporaire
from modules.corvees.capteurs.inactivite import Inactivite
from modules.corvees.capteurs.navigateur import EPOQUE_CHROME, EPOQUE_SAFARI, Navigateur, bases
from modules.corvees.capteurs.pressepapiers import PressePapiers, sorte
from modules.corvees.capteurs.shell import CLE, Shell, demetafier, lire_historique

R, _ = config.charger({})


class FauxMac:
    """Un macOS imité : on lui dit quoi répondre."""

    def __init__(self):
        self.devant = ("Safari", "com.apple.Safari")
        self.secours = None
        self.ax = True
        self.titre = "Accueil"
        self.compteur = 1
        self.contenu = (1, ["public.utf8-plain-text"], b"bonjour")
        self.inactif = 0.0

    def appli_devant(self):
        return self.devant

    def appli_devant_secours(self):
        return self.secours

    def accessibilite(self):
        return self.ax

    def fenetre_devant(self):
        return (self.devant[0], self.titre) if self.devant and self.titre else None

    def compteur_presse_papiers(self):
        return self.compteur

    def presse_papiers(self):
        return self.contenu

    def inactivite(self):
        return self.inactif


def capteur(classe, natif=None, **kwargs):
    sortie = []
    c = classe(R, sortie.append, MemoireVive(), natif, **kwargs)
    c.demarrer()
    return c, sortie


# --- Base ---------------------------------------------------------------------------------------------------


def test_capteur_de_base():
    sortie = []
    c = Capteur(R, sortie.append)
    c.demarrer(), c.relever(0), c.arreter()
    c.emettre(1.0, "app", "app:X", appli="X")
    assert sortie[0].token == "app:X" and sortie[0].source == "capteur"
    c.degrader("souci")
    assert c.sante()["statut"] == "dégradé" and c.sante()["detail"] == "souci"


# --- C1 : l'appli au premier plan ----------------------------------------------------------------------------


def test_c1_un_evenement_par_changement_d_appli():
    mac = FauxMac()
    c, sortie = capteur(Apps, mac)
    c.relever(10)
    c.relever(12)
    mac.devant = ("Numbers", "com.apple.iWork.Numbers")
    c.relever(20)
    assert [e.token for e in sortie] == ["app:Safari", "app:Numbers"]
    assert sortie[1].attrs == {"appli": "Numbers", "bundle": "com.apple.iWork.Numbers", "duree_precedente": 10.0}
    assert c.courante == "Numbers" and c.statut == "ok"


def test_c1_secours_puis_rien():
    mac = FauxMac()
    mac.devant, mac.secours = None, ("Pages", "")
    c, sortie = capteur(Apps, mac)
    c.relever(1)
    assert sortie[0].token == "app:Pages" and c.statut == "dégradé" and "secours" in c.detail
    mac.secours = None
    c.relever(2)
    assert c.statut == "dégradé" and len(sortie) == 1


def test_c1_les_processus_du_systeme_ne_sont_pas_des_applis():
    """Vu sur le Mac : « WindowManager » (Stage Manager) apparaissait entre deux vraies applis."""
    mac = FauxMac()
    c, sortie = capteur(Apps, mac)
    c.relever(10)
    for systeme in ("WindowManager", "Dock", "Centre de contrôle"):
        mac.devant = (systeme, "")
        c.relever(12)
    mac.devant = ("Numbers", "com.apple.iWork.Numbers")
    c.relever(20)
    assert [e.token for e in sortie] == ["app:Safari", "app:Numbers"]
    assert sortie[1].attrs["duree_precedente"] == 10.0 and c.statut == "ok"


def test_c1_desactive_hors_mac():
    c, sortie = capteur(Apps, None)
    c.relever(1)
    assert c.statut == "désactivé" and sortie == []


# --- C2 : les titres de fenêtres -----------------------------------------------------------------------------


def test_c2_titres_normalises_avec_l_autorisation():
    mac = FauxMac()
    c, sortie = capteur(Fenetres, mac)
    mac.titre = "Budget 2026.numbers"
    c.relever(2)
    c.relever(3)
    mac.titre = "Budget 2027.numbers"  # même forme normalisée : rien de nouveau
    c.relever(4)
    assert [e.token for e in sortie] == ["fen:Safari:Budget *.numbers"]
    mac.titre = None
    c.relever(5)
    assert len(sortie) == 1


def test_c2_l_appli_et_son_titre_sont_lus_ensemble():
    """Vu sur le Mac : « fen:TextEdit:Calculatrice », le titre de la nouvelle appli avec le nom de l'ancienne. Le
    nom de l'appli et le titre de sa fenêtre viennent maintenant de la même question à macOS."""
    mac = FauxMac()
    c, sortie = capteur(Fenetres, mac)
    mac.devant, mac.titre = ("Calculatrice", "com.apple.calculator"), "Calculatrice"
    c.relever(1)
    mac.devant, mac.titre = ("WindowManager", ""), "Claude"  # un processus du système : pas une fenêtre d'appli
    c.relever(2)
    assert [e.token for e in sortie] == ["fen:Calculatrice:Calculatrice"]
    assert sortie[0].attrs == {"appli": "Calculatrice"}


def test_c2_sans_accessibilite_desactive():
    mac = FauxMac()
    mac.ax = False
    c, sortie = capteur(Fenetres, mac)
    assert c.statut == "désactivé" and "Accessibilité" in c.detail
    mac.ax = True
    mac.titre = None
    c.relever(1)  # pas de fenêtre au premier plan : rien
    assert c.statut == "ok" and sortie == []
    mac.ax = False
    c.relever(2)
    assert c.statut == "désactivé"
    assert capteur(Fenetres, None)[0].statut == "désactivé"
    c2, _ = capteur(Fenetres, None)
    c2.relever(1)


# --- L'inactivité --------------------------------------------------------------------------------------------


def test_inactivite_coupe_la_session_une_fois():
    mac = FauxMac()
    c, sortie = capteur(Inactivite, mac)
    mac.inactif = 30
    c.relever(1000)
    mac.inactif = 700
    c.relever(2000)
    c.relever(2005)
    assert [(e.ts, e.token) for e in sortie] == [(1300, "inactif")]
    mac.inactif = 1
    c.relever(2010)
    mac.inactif = 900
    c.relever(3000)
    assert len(sortie) == 2 and c.inactif_depuis == 900
    mac.inactif = None
    c.relever(3001)
    assert c.statut == "dégradé"
    hors_mac, _ = capteur(Inactivite, None)
    hors_mac.relever(1)
    assert hors_mac.statut == "désactivé" and hors_mac.inactif_depuis == 0


# --- C6 : le presse-papiers ----------------------------------------------------------------------------------


def test_c6_une_copie_puis_un_pont_vers_l_appli_suivante():
    mac = FauxMac()
    apps, _ = capteur(Apps, mac)
    apps.relever(1)
    c, sortie = capteur(PressePapiers, mac, apps=apps, empreinte=lambda b: "e" * 16)
    mac.compteur = 2
    c.relever(10)
    c.relever(11)  # toujours dans Safari : pas encore de pont
    mac.devant = ("Numbers", "")
    apps.relever(20)
    c.relever(20)
    assert [e.kind for e in sortie] == ["copie", "clip"]
    assert sortie[0].attrs == {"source": "Safari", "type": "texte", "longueur": 7, "empreinte": "e" * 16}
    assert sortie[1].token == "clip:Safari→Numbers" and sortie[1].attrs["destination"] == "Numbers"
    assert "bonjour" not in str([e.attrs for e in sortie])


def test_c6_mots_de_passe_ignores_et_ponts_trop_tardifs():
    mac = FauxMac()
    apps, _ = capteur(Apps, mac)
    apps.relever(1)
    c, sortie = capteur(PressePapiers, mac, apps=apps)
    mac.compteur, mac.contenu = 2, (2, ["public.utf8-plain-text", "org.nspasteboard.ConcealedType"], b"S3cret")
    c.relever(5)
    assert sortie == [] and c.attente is None
    mac.compteur, mac.contenu = 3, (3, ["public.url"], None)
    c.relever(10)
    assert sortie[-1].attrs["type"] == "url" and sortie[-1].attrs["longueur"] == 0
    c.relever(200)  # plus de 2 minutes sans changer d'appli : la copie n'est plus reliée
    mac.devant = ("Mail", "")
    apps.relever(201)
    c.relever(201)
    assert [e.kind for e in sortie] == ["copie"]
    mac.contenu = None
    mac.compteur = 4
    c.relever(202)
    mac.compteur = None
    c.relever(203)
    assert c.statut == "dégradé"
    hors_mac, _ = capteur(PressePapiers, None)
    hors_mac.relever(1)
    assert hors_mac.statut == "désactivé"


def test_sorte_de_contenu():
    assert sorte(["public.file-url", "public.url"]) == "fichier" and sorte(["public.png"]) == "image"
    assert sorte(["public.url"]) == "url" and sorte(["public.utf8-plain-text"]) == "texte"


# --- C4 : l'historique zsh ----------------------------------------------------------------------------------


def test_lecture_du_format_zsh():
    brut = (
        b": 1790000000:0;git pull\n"
        b": 1790000010:2;for f in *.pdf; do\\\n  echo $f\\\ndone\n"
        b"ls -la\n"
        b": 1790000020:0;echo c\xc5\x83\xb3ur\n"
        b"\n"
    )
    assert lire_historique(brut) == [
        (1790000000, "git pull"),
        (1790000010, "for f in *.pdf; do\n  echo $f\ndone"),
        (None, "ls -la"),
        (1790000020, "echo cœur"),
    ]
    assert demetafier(b"abc") == b"abc" and demetafier(b"\x83\xa9") == b"\x89"


def ecrire(chemin, texte, mode="ab"):
    with open(chemin, mode) as f:
        f.write(texte)


def test_c4_lecture_incrementale(tmp_path):
    historique = tmp_path / ".zsh_history"
    ecrire(historique, b": 1790000000:0;ancienne commande\n", "wb")
    r, _ = config.charger({"shell": {"historique": str(historique)}})
    sortie = []
    c = Shell(r, sortie.append, MemoireVive(), None, maison="/Users/moi")
    c.demarrer()
    c.relever(1790000100)  # premier passage : on part de la fin, l'ancien n'est pas lu
    assert sortie == [] and c.memoire.lire(CLE)["position"] == historique.stat().st_size
    ecrire(historique, b": 1790000200:0;cd /Users/moi/x && git pull\n: 1790000210:0;ls\n: 1790000220:0;en cou")
    c.relever(1790000300)
    assert [(e.ts, e.token) for e in sortie] == [(1790000200, "cmd:cd ~/x && git pull"), (1790000210, "cmd:ls")]
    ecrire(historique, b"rs\nsans horodatage\n")
    c.relever(1790000400)
    assert [e.token for e in sortie[2:]] == ["cmd:en cours", "cmd:sans horodatage"]
    assert sortie[-1].ts == 1790000400


def test_c4_deux_commandes_dans_la_meme_seconde(tmp_path):
    """zsh note l'heure à la seconde : une commande tapée dans la même seconde que la précédente (déjà lue) n'est
    pas perdue pour autant (trouvé par le test de bout en bout)."""
    historique = tmp_path / ".zsh_history"
    ecrire(historique, b"", "wb")
    r, _ = config.charger({"shell": {"historique": str(historique)}})
    sortie = []
    c = Shell(r, sortie.append, MemoireVive(), None)
    c.demarrer()
    c.relever(1790000000)
    ecrire(historique, b": 1790000000:0;a\n")  # dans la seconde même du premier passage
    c.relever(1790000000.5)
    ecrire(historique, b": 1790000000:0;b\n: 1790000000:0;b\n")  # deux fois la même, toujours la même seconde
    c.relever(1790000000.9)
    assert [e.token for e in sortie] == ["cmd:a", "cmd:b", "cmd:b"]


def test_c4_zsh_sauve_par_copie_rien_ne_se_perd(tmp_path):
    """zsh (option HIST_SAVE_BY_COPY, par défaut) écrit un nouveau fichier puis le renomme : le numéro du fichier
    change, mais le début est le même. Ce n'est pas une réécriture : on continue où on en était (trouvé avec un
    vrai zsh dans le test de bout en bout)."""
    historique = tmp_path / ".zsh_history"
    ecrire(historique, b": 1790000000:0;ancien\n", "wb")
    r, _ = config.charger({"shell": {"historique": str(historique)}})
    sortie = []
    c = Shell(r, sortie.append, MemoireVive(), None)
    c.demarrer()
    c.relever(1790000000)
    for commande in (b"a", b"b", b"a"):  # tout dans la même seconde, chaque fois par copie
        copie = tmp_path / ".zsh_history.new"
        copie.write_bytes(historique.read_bytes() + b": 1790000000:0;" + commande + b"\n")
        os.replace(copie, historique)
        c.relever(1790000000.5)
    # Un autre terminal, fermé plus tard, ajoute ses commandes plus anciennes : elles comptent aussi
    copie = tmp_path / ".zsh_history.new"
    copie.write_bytes(historique.read_bytes() + b": 1789999000:0;depuis l'autre terminal\n")
    os.replace(copie, historique)
    c.relever(1790000001)
    assert [e.token for e in sortie] == ["cmd:a", "cmd:b", "cmd:a", "cmd:depuis l'autre terminal"]


def test_c4_vraie_reecriture_dans_la_meme_seconde(tmp_path):
    """zsh raccourcit son historique (trop long) : tout est réécrit. Seul ce qui est nouveau est redonné, même ce
    qui a été tapé dans la même seconde que la dernière commande lue."""
    historique = tmp_path / ".zsh_history"
    ecrire(historique, b"", "wb")
    r, _ = config.charger({"shell": {"historique": str(historique)}})
    sortie = []
    c = Shell(r, sortie.append, MemoireVive(), None)
    c.demarrer()
    c.relever(1790000000)
    ecrire(historique, b": 1790000000:0;vieux\n: 1790000010:0;a\n")
    c.relever(1790000011)
    ecrire(historique, b": 1790000010:0;a\n: 1790000010:0;b\n: 1790000020:0;c\n", "wb")  # « vieux » est parti
    c.relever(1790000030)
    assert [e.token for e in sortie] == ["cmd:vieux", "cmd:a", "cmd:b", "cmd:c"]


def test_c4_fichier_reecrit_sans_redonner_l_ancien(tmp_path):
    historique = tmp_path / ".zsh_history"
    ecrire(historique, b": 1790000000:0;a\n: 1790000010:0;b\n", "wb")
    r, _ = config.charger({"shell": {"historique": str(historique)}})
    sortie = []
    c = Shell(r, sortie.append, MemoireVive(), None)
    c.demarrer()
    c.relever(1790000020)
    os.remove(historique)
    ecrire(historique, b": 1790000010:0;b\nvieux sans date\n: 1790000030:0;c\n", "wb")  # réécrit (plus court)
    c.relever(1790000040)
    assert [e.token for e in sortie] == ["cmd:c"]


def test_c4_historique_absent_ou_illisible(tmp_path):
    r, _ = config.charger({"shell": {"historique": str(tmp_path / "absent")}})
    c = Shell(r, [].append, MemoireVive(), None)
    c.demarrer()
    assert c.statut == "dégradé"
    c.relever(1)
    assert "pas (encore)" in c.detail
    historique = tmp_path / "h"
    ecrire(historique, b"x\n", "wb")
    r, _ = config.charger({"shell": {"historique": str(historique)}})
    c = Shell(r, [].append, MemoireVive(), None)
    c.memoire.ecrire(CLE, {"inode": historique.stat().st_ino, "position": 0, "dernier_ts": 0})
    with mock.patch("builtins.open", side_effect=PermissionError("verrouillé")):
        c.relever(5)
    assert c.statut == "dégradé" and "PermissionError" in c.detail
    with mock.patch("os.stat", side_effect=PermissionError("non")):
        c.relever(6)
    assert "illisible" in c.detail


# --- C5 : l'historique des navigateurs ----------------------------------------------------------------------


def base_chrome(chemin: Path):
    db = sqlite3.connect(chemin)
    db.executescript(
        "CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT);"
        "CREATE TABLE visits (id INTEGER PRIMARY KEY, url INTEGER, visit_time INTEGER, transition INTEGER);"
    )
    db.commit()
    return db


def visite_chrome(db, id_, url, quand, transition=0):
    db.execute("INSERT INTO urls (id, url) VALUES (?, ?)", (id_, url))
    db.execute(
        "INSERT INTO visits (id, url, visit_time, transition) VALUES (?, ?, ?, ?)",
        (id_, id_, int((quand + EPOQUE_CHROME) * 1e6), transition),
    )
    db.commit()


def test_c5_chrome_depuis_le_curseur(tmp_path):
    chemin = tmp_path / "History"
    db = base_chrome(chemin)
    visite_chrome(db, 1, "https://www.lemonde.fr/vieux", 1790000000)
    sortie = []
    c = Navigateur(R, sortie.append, MemoireVive(), None, chemins=[("chrome", "chromium", chemin)])
    c.demarrer()
    c.relever(1790000100)  # premier passage : le passé n'est pas lu
    assert sortie == []
    visite_chrome(db, 2, "https://mail.google.com/mail/u/0/?tab=x#inbox", 1790000200)
    visite_chrome(db, 3, "https://mail.google.com/mail/u/0/#sent", 1790000210)  # même page, aussitôt
    visite_chrome(db, 4, "chrome://settings", 1790000220)
    visite_chrome(db, 5, "https://pub.exemple.fr/cadre", 1790000230, transition=3)  # sous-cadre
    visite_chrome(db, 6, "https://www.notion.so/page", 1790000240, transition=8)  # rechargement
    visite_chrome(db, 7, "https://calendar.google.com/calendar/r", 1790000250)
    c.relever(1790000300)
    assert [(round(e.ts), e.token) for e in sortie] == [
        (1790000200, "url:mail.google.com/mail"),
        (1790000250, "url:calendar.google.com/calendar"),
    ]
    assert sortie[0].attrs == {"domaine": "mail.google.com", "navigateur": "chrome"}
    c.relever(1790000400)
    assert len(sortie) == 2 and c.statut == "ok" and c.sante()["navigateurs"] == ["chrome"]


def test_c5_safari(tmp_path):
    chemin = tmp_path / "History.db"
    db = sqlite3.connect(chemin)
    db.executescript(
        "CREATE TABLE history_items (id INTEGER PRIMARY KEY, url TEXT);"
        "CREATE TABLE history_visits (id INTEGER PRIMARY KEY, history_item INTEGER, visit_time REAL);"
    )
    sortie = []
    c = Navigateur(R, sortie.append, MemoireVive(), None, chemins=[("safari", "safari", chemin)])
    c.demarrer()
    c.relever(1)
    db.execute("INSERT INTO history_items VALUES (1, 'https://www.wikipedia.org/wiki/Bilan')")
    db.execute("INSERT INTO history_visits VALUES (1, 1, ?)", (1790000000 - EPOQUE_SAFARI,))
    db.commit()
    c.relever(2)
    assert [(e.ts, e.token) for e in sortie] == [(1790000000, "url:wikipedia.org/wiki")]


def test_c5_safari_sans_acces_complet_au_disque(tmp_path):
    chemin = tmp_path / "History.db"
    chemin.write_bytes(b"")
    c = Navigateur(R, [].append, MemoireVive(), None, chemins=[("safari", "safari", chemin)])
    c.demarrer()
    with mock.patch("shutil.copy2", side_effect=PermissionError("Operation not permitted")):
        c.relever(1)
    assert c.statut == "dégradé" and "Accès complet au disque" in c.detail
    chemin.write_bytes(b"pas une base")
    c.relever(2)
    assert "illisible" in c.detail


def test_c5_profils_trouves_sur_le_mac(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    support = tmp_path / "Library" / "Application Support"
    for profil in ("Google/Chrome/Default", "Google/Chrome/Profile 2", "BraveSoftware/Brave-Browser/Default"):
        (support / profil).mkdir(parents=True)
        (support / profil / "History").write_bytes(b"")
    (tmp_path / "Library" / "Safari").mkdir(parents=True)
    (tmp_path / "Library" / "Safari" / "History.db").write_bytes(b"")
    trouvees = bases(["chrome", "brave", "arc", "safari", "inconnu"])
    assert [(n, s, p.parent.name) for n, s, p in trouvees] == [
        ("chrome", "chromium", "Default"),
        ("chrome", "chromium", "Profile 2"),
        ("brave", "chromium", "Default"),
        ("safari", "safari", "Safari"),
    ]
    c = Navigateur(R, [].append, MemoireVive(), None)
    c.demarrer()
    assert len(c.chemins) == 4
    monkeypatch.setenv("HOME", str(tmp_path / "vide"))
    vide = Navigateur(R, [].append, MemoireVive(), None)
    vide.demarrer()
    assert vide.statut == "désactivé"


# --- C3 : les fichiers ------------------------------------------------------------------------------------


@pytest.fixture
def maison(tmp_path):
    for d in ("Downloads", "Desktop", "Documents/Factures", "Documents/Perso", "Downloads/a/b/c/d/e"):
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


def reconstructeur(maison, exclu=lambda c: False):
    racines = [str(maison / d) for d in ("Downloads", "Desktop", "Documents")]
    return Reconstructeur(racines, 4, lambda c: "#" + os.path.basename(c), exclu, str(maison))


def test_c3_reconstitue_les_actions(maison):
    r = reconstructeur(maison)
    d, doc = str(maison / "Downloads"), str(maison / "Documents")
    (maison / "Downloads" / "IMG_12.heic").write_bytes(b"x")
    sortie = r.traiter(
        [
            Brut(1, "created", f"{d}/Facture_2026-10-03.pdf"),
            Brut(2, "moved", f"{d}/Facture_2026-10-03.pdf", f"{doc}/Factures/Facture_2026-10-03.pdf"),
            Brut(3, "moved", f"{d}/scan 1.pdf", f"{d}/Cours_1.pdf"),
            Brut(4, "created", f"{d}/IMG_12.jpg"),
            Brut(5, "moved", f"{d}/rapport.pdf.crdownload", f"{d}/rapport.pdf"),
            Brut(6, "created", f"{d}/.DS_Store"),
            Brut(7, "created", f"{d}/~$brouillon.docx"),
            Brut(8, "created", f"{d}/a/b/c/d/e/trop_profond.pdf"),
            Brut(9, "created", "/ailleurs/fichier.pdf"),
        ],
        maintenant=10,
    )
    assert [(t, s, tok) for t, s, tok, _ in sortie] == [
        (1, "fcreate", "fcreate:Downloads [pdf, Facture_*]"),
        (2, "fmove", "fmove:Downloads→Documents/Factures [pdf, Facture_*]"),
        (3, "fren", "fren:Downloads [pdf, scan *→Cours_*]"),
        (4, "fconv", "fconv:Downloads [heic→jpg, IMG_*]"),
        (5, "fcreate", "fcreate:Downloads [pdf, rapport]"),
    ]
    assert sortie[1][3] == {"avant": "#Facture_2026-10-03.pdf", "fichier": "#Facture_2026-10-03.pdf"}
    assert sortie[3][3] == {"source": "#IMG_12.heic", "fichier": "#IMG_12.jpg"}


def test_c3_supprime_puis_recree_ailleurs_c_est_un_deplacement(maison):
    r = reconstructeur(maison)
    d, b = str(maison / "Downloads"), str(maison / "Desktop")
    assert r.traiter([Brut(1, "deleted", f"{d}/x.zip")], maintenant=1.5) == []
    (s,) = r.traiter([Brut(2, "created", f"{b}/x.zip")], maintenant=2)
    assert s[1:3] == ("fmove", "fmove:Downloads→Desktop [zip, x]")
    # dans l'autre ordre (recréé là-bas avant d'être signalé supprimé ici) : toujours un déplacement
    assert r.traiter([Brut(5, "created", f"{b}/y.zip")], maintenant=5) == []
    (s,) = r.traiter([Brut(5.5, "deleted", f"{d}/y.zip")], maintenant=6)
    assert s[1:3] == ("fmove", "fmove:Downloads→Desktop [zip, y]")
    assert r.traiter([Brut(10, "deleted", f"{d}/Installeur_Zoom_5.dmg")], maintenant=10) == []
    (s,) = r.traiter([], maintenant=13)
    assert s[1:3] == ("fdel", "fdel:Downloads [dmg, Installeur_Zoom_*]")


def test_c3_dossiers_exclus_caches_et_vers_l_exterieur(maison):
    r = reconstructeur(maison, exclu=lambda c: "Perso" in c)
    doc = str(maison / "Documents")
    assert r.traiter([Brut(1, "created", f"{doc}/Perso/journal.txt")], 2) == []
    assert r.traiter([Brut(1, "moved", f"{doc}/Perso/a.txt", f"{doc}/a.txt")], 2) == []
    assert r.traiter([Brut(1, "created", f"{doc}/.git/HEAD")], 2) == []
    assert r.traiter([Brut(1, "moved", "/tmp/a.txt", "/tmp/b.txt")], 2) == []
    assert r.traiter([Brut(1, "moved", f"{doc}/a.txt", "")], 2) == []
    (s,) = r.traiter([Brut(1, "moved", f"{doc}/vieux.dmg", f"{maison}/.Trash/vieux.dmg")], 2)
    assert s[2] == "fmove:Documents→.Trash [dmg, vieux]"
    assert r.traiter([Brut(1, "moved", "/x/dl.crdownload", "/x/dl.pdf")], 2) == []
    assert temporaire("a.part") and temporaire("~$a.docx") and not temporaire("a.pdf")
    assert cache("/u/.git/x") and not cache("/u/.Trash/x")


def test_c3_dossier_disparu_entre_temps(maison):
    r = reconstructeur(maison)
    assert r.traiter([Brut(1, "created", str(maison / "Downloads" / "disparu" / "a.pdf"))], 2) == []  # attend 2 s
    (s,) = r.traiter([], 5)
    assert s[1] == "fcreate"


def attendre(condition, delai=5.0):
    fin = time.time() + delai
    while time.time() < fin and not condition():
        time.sleep(0.05)
    return condition()


def test_c3_vraie_surveillance_des_dossiers(maison):
    r, _ = config.charger({"fichiers": {"dossiers": [str(maison / "Downloads"), str(maison / "Documents")]}})
    sortie = []
    c = Fichiers(r, sortie.append, MemoireVive(), None, empreinte=lambda x: "e", maison=str(maison))
    c.demarrer()
    try:
        time.sleep(0.3)
        (maison / "Downloads" / "Facture_2026-10-03.pdf").write_bytes(b"%PDF")
        time.sleep(0.3)
        os.rename(
            maison / "Downloads" / "Facture_2026-10-03.pdf",
            maison / "Documents" / "Factures" / "Facture_2026-10-03.pdf",
        )
        assert attendre(lambda: (c.relever(time.time()), len(sortie) >= 2)[1], delai=8)
    finally:
        c.arreter()
        c.arreter()  # deux fois : sans erreur
    dans_l_ordre = sorted(sortie, key=lambda e: e.ts)  # chacun garde son instant ; l'analyse trie
    assert [e.kind for e in dans_l_ordre][:2] == ["fcreate", "fmove"]
    assert dans_l_ordre[1].token == "fmove:Downloads→Documents/Factures [pdf, Facture_*]"


def test_c3_sans_watchdog_on_compare_des_instantanes(maison):
    r, _ = config.charger({"fichiers": {"dossiers": [str(maison / "Downloads"), str(maison / "Documents")]}})
    sortie = []
    with mock.patch.dict(sys.modules, {"watchdog.observers": None}):
        c = Fichiers(r, sortie.append, MemoireVive(), None, empreinte=lambda x: "e", maison=str(maison))
        c.demarrer()
    assert c.statut == "dégradé" and "watchdog" in c.detail
    (maison / "Downloads" / "a.pdf").write_bytes(b"x")
    (maison / "Documents" / "vieux.txt").write_bytes(b"x")
    c.relever(time.time() + 61)
    os.rename(maison / "Downloads" / "a.pdf", maison / "Documents" / "a.pdf")
    os.remove(maison / "Documents" / "vieux.txt")
    c.relever(time.time() + 200)
    c.relever(time.time() + 300)
    sortes = [e.kind for e in sortie]
    assert sortes.count("fcreate") == 2 and "fmove" in sortes and "fdel" in sortes


def test_c3_aucun_dossier_surveille(tmp_path):
    r, _ = config.charger({"fichiers": {"dossiers": [str(tmp_path / "absent")]}})
    c = Fichiers(r, [].append, MemoireVive(), None)
    c.demarrer()
    assert c.statut == "désactivé"


# --- L'assemblage -----------------------------------------------------------------------------------------


def test_construire_respecte_les_reglages():
    tous = construire(R, [].append, MemoireVive(), None, lambda x: "", lambda c: False)
    assert [c.nom for c in tous] == [
        "apps",
        "fenetres",
        "fichiers",
        "shell",
        "navigateur",
        "pressepapiers",
        "inactivite",
    ]
    r, _ = config.charger({"capteurs": {"pressepapiers": False, "navigateur": False, "apps": False}})
    assert [c.nom for c in construire(r, [].append, MemoireVive(), None, None, None)] == [
        "fenetres",
        "fichiers",
        "shell",
        "inactivite",
    ]
