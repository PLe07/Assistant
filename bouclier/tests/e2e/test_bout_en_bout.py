"""Bout en bout sur un Mac imité (§9) : le démon fait tout ce qu'il doit (entrée iCloud, Gmail en lecture seule,
listes du jour, inventaire, fuites, fiche urgence, tableau de bord), sans jamais s'arrêter sur une erreur ; doctor
et l'installation."""

from __future__ import annotations

import datetime as dt
import json
import plistlib
import shutil
import threading
from collections.abc import Sequence
from pathlib import Path

import pytest

from bouclier import cli, config, daemon, db, doctor, installation, reseau, tableau_de_bord
from bouclier.arnaque import analyse
from bouclier.systeme import Resultat, Systeme
from tests.comptes.boite_simulee import FauxImap, Message, generer
from tests.fuites.test_fuites import FIXTURE

ARNAQUE = (
    b'From: "Colissimo" <suivi@colissimo-livraison.top>\r\nSubject: Votre colis est en attente\r\n'
    b"Date: Tue, 6 Oct 2026 10:00:00 +0200\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"
)
ARNAQUE_CORPS = "Payez 1,99 € de frais de livraison ici : https://colissimo-livraison.top/p".encode()
LEGITIME = (
    b'From: "Julie" <julie@example.org>\r\nSubject: Cine ce soir ?\r\nContent-Type: text/plain\r\n\r\n'
    b"On se retrouve a 20h devant le cinema ?"
)


class MacImite:
    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        self.secrets = secrets if secrets is not None else {"bouclier-gmail": "bon"}
        self.appels: list[list[str]] = []
        self.shortcuts = "Envoie au Mac\nArnaque ?\nEnvoyer sans traces\n"

    def executer(self, args: Sequence[str], entree: str | None, delai: float) -> Resultat:
        a = list(args)
        self.appels.append(a)
        if a[:2] == ["security", "find-generic-password"]:
            v = self.secrets.get(a[a.index("-s") + 1])
            return Resultat(0, v + "\n") if v else Resultat(44, "")
        if a[:2] == ["launchctl", "print"]:
            return Resultat(0, "state = running\n\tpid = 4242\n\tlast exit code = 0\n")
        if a[:2] == ["shortcuts", "list"]:
            return Resultat(0, self.shortcuts)
        return Resultat(0, "")


class Reseau:
    """Le réseau imité : listes de liens piégés, liste des fuites, pages officielles ; la liste blanche s'applique."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str, **_: object) -> reseau.Reponse:
        reseau.verifier_url(url)
        self.urls.append(url)
        if "openphish" in url:
            return reseau.Reponse(200, b"https://colissimo-livraison.top/p\n", url)
        if "urlhaus" in url:
            return reseau.Reponse(200, b"# urlhaus\nhttp://198.51.100.7/x\n", url)
        if "haveibeenpwned" in url:
            return reseau.Reponse(200, json.dumps(FIXTURE).encode(), url)
        raise reseau.ErreurReseau("page officielle injoignable dans ce test")


Environnement = tuple[config.Chemins, db.Base, Systeme, "MacImite", FauxImap, "Reseau", list[float]]


@pytest.fixture
def mac(maison: Path) -> Environnement:
    c = config.chemins()
    c.support.mkdir(parents=True)
    c.icloud_drive.mkdir(parents=True)
    c.config.write_text('[gmail]\nadresse = "camille@example.org"\n', encoding="utf-8")
    messages = generer()[0]
    faux = FauxImap(messages)
    imite = MacImite()
    t = [dt.datetime(2026, 10, 6, 14, 0).timestamp()]
    return c, db.ouvrir(c.base), Systeme(imite.executer, mac=True), imite, faux, Reseau(), t


def _demon(m: Environnement) -> daemon.Demon:
    c, base, systeme, _, faux, net, t = m

    def outils(reglages: dict[str, object]) -> analyse.Outils:
        return analyse.Outils(reglages, base)  # type: ignore[arg-type]

    composants = daemon.Composants(telecharger=net, fabrique_imap=lambda s: faux, outils=outils)
    return daemon.Demon(c, base, systeme, horloge=lambda: t[0], composants=composants)


def test_un_jour_de_demon(mac: Environnement) -> None:
    c, base, systeme, imite, faux, net, t = mac
    d = _demon(mac)
    echantillon = sorted(faux.messages)[:20]
    avant = {u: tuple(sorted(faux.messages[u].drapeaux)) for u in echantillon}

    premier = d.tour()
    assert premier.erreurs == []
    fait = " | ".join(premier.fait)
    assert "Gmail : 0 message(s)" in fait and "flux : OpenPhish OK, URLhaus OK" in fait
    assert "inventaire :" in fait and "fuites :" in fait and "fiche urgence générée" in fait
    assert c.tableau_de_bord.exists() and (c.sorties / "Fiche urgence.pdf").exists()
    assert {u.split("/")[2] for u in net.urls} == {
        "openphish.com",
        "urlhaus.abuse.ch",
        "haveibeenpwned.com",
        "www.masecurite.interieur.gouv.fr",
    } | {u.split("/")[2] for u in net.urls if reseau.est_officiel(u.split("/")[2])}

    # Un mail piégé et un vrai mail arrivent ; 5 minutes plus tard, le démon les lit (sans les marquer comme lus).
    faux.messages[900001] = Message(900001, ARNAQUE, corps=ARNAQUE_CORPS)
    faux.messages[900002] = Message(900002, LEGITIME, drapeaux={"\\Seen"})
    t[0] += 301
    deuxieme = d.tour()
    assert "Gmail : 2 message(s) analysé(s)" in deuxieme.fait
    notifications = [a for a in imite.appels if a[0] == "osascript" and any("display notification" in x for x in a)]
    assert len([n for n in notifications if "Colissimo" in " ".join(n)]) == 1  # l'arnaque, pas le vrai mail
    assert faux.violations == [] and faux.messages[900001].drapeaux == set()
    assert {u: tuple(sorted(faux.messages[u].drapeaux)) for u in echantillon} == avant
    assert not [f for f in deuxieme.fait if f.startswith(("flux", "inventaire", "fuites"))]  # pas deux fois par jour

    # L'iPhone dépose un SMS : réponse au tour suivant (taille stable).
    entree = c.icloud_raccourcis / "entree"
    entree.mkdir(parents=True)
    (entree / "arnaque-1.txt").write_text(ARNAQUE_CORPS.decode(), encoding="utf-8")
    d.tour()
    d.tour()
    assert (c.icloud_raccourcis / "reponses" / "arnaque-1.txt").read_text(encoding="utf-8").startswith("🔴")

    # Le lendemain, les listes sont retéléchargées ; la semaine suivante, l'inventaire est refait.
    t[0] += 86400
    assert any(f.startswith("flux") for f in d.tour().fait)
    t[0] += 7 * 86400
    assert any(f.startswith("inventaire") for f in d.tour().fait)
    assert base.lire_meta("demon_battement") == str(t[0])


def test_gmail_en_panne_delai_croissant(mac: Environnement) -> None:
    c, base, _, _, faux, _, t = mac
    faux.mot_de_passe = "révoqué"
    d = _demon(mac)
    d.tour()
    assert "refuse la connexion" in (base.lire_meta("gmail_erreur") or "")
    delais = []
    for _ in range(4):
        prochain = float(base.lire_meta("prochain:gmail") or 0)
        delais.append(round((prochain - t[0]) / 60))
        t[0] = prochain + 1
        d.tour()
    assert delais == [10, 20, 40, 60]
    faux.mot_de_passe = "bon"
    t[0] = float(base.lire_meta("prochain:gmail") or 0) + 1
    d.tour()
    assert base.lire_meta("gmail_erreur") == "" and base.lire_meta("gmail_echecs") == "0"


def test_une_brique_en_panne_n_arrete_pas_le_demon(mac: Environnement, monkeypatch: pytest.MonkeyPatch) -> None:
    c, base, _, _, _, _, t = mac
    d = _demon(mac)

    def panne(*a: object, **k: object) -> None:
        raise RuntimeError("panne imitée")

    monkeypatch.setattr(d, "_flux", panne)
    tour = d.tour()
    assert "flux : RuntimeError" in tour.erreurs and any(f.startswith("inventaire") for f in tour.fait)
    assert float(base.lire_meta("prochain:flux") or 0) == pytest.approx(t[0] + 3600)
    arret = threading.Event()
    assert d.lancer(arret, max_tours=2) == 2


def test_gmail_non_relie_et_config_abimee(maison: Path) -> None:
    c = config.chemins()
    c.support.mkdir(parents=True)
    c.config.write_text("[gmail\n", encoding="utf-8")
    base = db.ouvrir(c.base)
    d = daemon.Demon(
        c, base, Systeme(MacImite({}).executer, mac=True), composants=daemon.Composants(telecharger=Reseau())
    )
    tour = d.tour()
    assert "pas encore relié" in (base.lire_meta("gmail_erreur") or "") and "ne se lit pas" in (
        base.lire_meta("config_alerte") or ""
    )
    assert tour.erreurs == []


def test_doctor(mac: Environnement, capsys: pytest.CaptureFixture[str]) -> None:
    c, base, systeme, imite, _, _, t = mac
    lignes = {
        brique: (etat, texte)
        for etat, brique, texte in doctor.verifier(c, config.charger(c), base, systeme, maintenant=t[0])
    }
    assert lignes["démon"][0] == "⚠️"  # chargé mais pas de battement récent
    assert lignes["raccourcis"] == ("✅", "Arnaque ? et Envoyer sans traces présents")
    assert lignes["avis de l'IA"][0] == "⚠️" and "analyse locale seule" in lignes["avis de l'IA"][1]
    assert lignes["fiche urgence"][0] == "⚠️" and lignes["actions rapides"][0] == "⚠️"
    _demon(mac).tour()
    lignes = {
        brique: (etat, texte)
        for etat, brique, texte in doctor.verifier(c, config.charger(c), base, systeme, maintenant=t[0] + 5)
    }
    assert lignes["démon"][0] == "✅" and "pid 4242" in lignes["démon"][1]
    assert lignes["Gmail"][0] == "✅" and lignes["liste OpenPhish"][0] == "✅" and lignes["fiche urgence"][0] == "✅"
    assert lignes["liste des fuites"][0] == "✅" and lignes["inventaire"][0] == "✅"
    imite.shortcuts = "Envoie au Mac\n"
    lignes = {b: (e, x) for e, b, x in doctor.verifier(c, config.charger(c), base, systeme, maintenant=t[0])}
    assert "à ajouter sur l'iPhone" in lignes["raccourcis"][1]
    assert cli.main(["doctor"], systeme) in (0, 1) and "démon" in capsys.readouterr().out


def test_hygiene_numerique(mac: Environnement, capsys: pytest.CaptureFixture[str]) -> None:
    c, base, systeme, _, _, _, _ = mac
    score, actions = tableau_de_bord.hygiene(base)
    assert score < 100 and actions[0].startswith("Lance l'inventaire")
    _demon(mac).tour()
    score, actions = tableau_de_bord.hygiene(base)
    assert len(actions) == 3 and actions[0].startswith("Change le mot de passe de")
    html = tableau_de_bord.construire(base)
    assert "Hygiène numérique : <span" in html and f">{score}/100<" in html
    assert cli.main(["tableau", "--sans-ouvrir"], systeme) == 0 and f"{score}/100" in capsys.readouterr().out


def test_installation_relancable_et_prudente(maison: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    c = config.chemins()
    c.icloud_drive.mkdir(parents=True)
    reglages = config.charger()
    monkeypatch.setattr(installation.getpass, "getuser", lambda: "Camille.M")
    assert installation.label(reglages) == "com.camillem.bouclier"
    python, projet = Path("/p/.venv/bin/python"), Path("/p")
    for _ in range(2):  # relançable sans effet de bord
        b = installation.preparer(c, reglages, python, projet)
        assert b.refus == [] and any("agent de démarrage" in f for f in b.fait)
    agent = c.launch_agents / "com.camillem.bouclier.plist"
    with agent.open("rb") as f:
        p = plistlib.load(f)
    assert p["ProgramArguments"] == [str(python), "-m", "bouclier", "demon"] and p["KeepAlive"] and p["RunAtLoad"]
    assert p["ThrottleInterval"] == 30 and installation.agent_est_a_nous(agent)
    lanceur = installation.lanceur(c)
    assert installation.lanceur_est_a_nous(lanceur) and str(python) in lanceur.read_text(encoding="utf-8")
    assert (c.icloud / "entree").is_dir() and c.config.exists() and c.infos_urgence.exists()
    r = installation.raccourcis(c)
    assert any("non signé" in a for a in r.avertissements)  # pas de commande shortcuts ici
    b = installation.desinstaller(c, reglages)
    assert not agent.exists() and not lanceur.exists() and c.support.exists()
    assert installation.desinstaller(c, reglages).fait == []  # relançable
    installation.desinstaller(c, reglages, tout=True)
    assert not c.support.exists()


def test_installation_ne_touche_pas_ce_qui_n_est_pas_a_elle(maison: Path) -> None:
    c = config.chemins()
    reglages = config.charger()
    reglages["installation"]["prefixe_label"] = "camille"
    lanceur = installation.lanceur(c)
    lanceur.parent.mkdir(parents=True)
    lanceur.write_text("#!/bin/sh\necho autre outil\n", encoding="utf-8")
    agent = c.launch_agents / "com.camille.bouclier.plist"
    agent.parent.mkdir(parents=True)
    with agent.open("wb") as f:
        plistlib.dump({"Label": "com.camille.bouclier", "ProgramArguments": ["/usr/bin/autre"]}, f)
    b = installation.preparer(c, reglages, Path("/p/python"), Path("/p"))
    assert len(b.refus) == 2 and b.fait == []
    assert lanceur.read_text(encoding="utf-8") == "#!/bin/sh\necho autre outil\n"
    installation.desinstaller(c, reglages)
    assert lanceur.exists() and agent.exists()
    assert installation.etat_agent(Systeme(lambda a, e, d: Resultat(1, ""), mac=True), "x").charge is False
    assert installation.etat_agent(Systeme(lambda a, e, d: Resultat(0, ""), mac=False), "x").charge is False


def test_cli_installation(maison: Path, capsys: pytest.CaptureFixture[str]) -> None:
    systeme = Systeme(MacImite().executer, mac=False)
    assert cli.main(["installation", "label"], systeme) == 0 and capsys.readouterr().out.startswith("com.")
    assert cli.main(["installation", "preparer", "--python", "/p/python", "--projet", "/p"], systeme) == 0
    assert "agent de démarrage" in capsys.readouterr().out
    assert cli.main(["installation", "raccourcis"], systeme) == 0
    assert cli.main(["installation", "desinstaller"], systeme) == 0 and "agent retiré" in capsys.readouterr().out


def test_hygiene_double_authentification_et_score_parfait(maison: Path) -> None:
    from bouclier.comptes import inventaire

    c = config.chemins()
    base = db.ouvrir(c.base)
    inv = inventaire.Inventaire()
    obs = inventaire.observer(b"From: <no-reply@accounts.google.com>\r\nSubject: Nouvelle connexion\r\n\r\n")
    assert obs is not None
    inv.ajouter_mail(obs)
    inventaire.enregistrer(base, inv)
    base.ecrire_meta("inventaire_le", "1")
    score, actions = tableau_de_bord.hygiene(base)
    assert any(a.startswith("Active la double authentification") and "Google" in a for a in actions)
    base.ecrire_meta("fiche_generee_le", str(dt.datetime(2026, 10, 1).timestamp()))
    base.ecrire_meta("gmail_releve_le", "1")
    inventaire.poser_statut(base, "google", "supprime")
    score, actions = tableau_de_bord.hygiene(base, maintenant=dt.datetime(2026, 10, 6).timestamp())
    assert (score, actions) == (100, [])
    assert "Rien d'urgent" in tableau_de_bord.construire(base)


def test_un_long_inventaire_ne_retarde_pas_le_raccourci(mac: Environnement, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sur le Mac, les tâches lentes tournent dans un fil à part avec leur propre connexion à la base : un inventaire
    de plusieurs minutes ne retarde pas la réponse au raccourci « Arnaque ? »."""
    c, base, systeme, _, faux, net, t = mac
    c.config.write_text("[gmail]\nactive = false\n", encoding="utf-8")
    commence, libere = threading.Event(), threading.Event()
    fils: list[str] = []

    def inventaire_interminable(self: daemon.Demon, reglages: object, tour: daemon.Tour) -> None:
        fils.append(threading.current_thread().name)
        commence.set()
        libere.wait(20)
        self._planifier("inventaire", daemon.SEMAINE_S)

    monkeypatch.setattr(daemon.Demon, "_inventaire", inventaire_interminable)
    monkeypatch.setattr(daemon, "PAS_S", 0.05)
    arret = threading.Event()

    def tourner() -> None:  # comme sous launchd : la base de la boucle est ouverte dans son propre fil
        b = db.ouvrir(c.base)
        composants = daemon.Composants(net, lambda s: faux, lambda r: analyse.Outils(r, b))  # type: ignore[arg-type]
        daemon.Demon(c, b, systeme, horloge=lambda: t[0], composants=composants).lancer(arret)

    boucle = threading.Thread(target=tourner)
    boucle.start()
    try:
        assert commence.wait(10)
        entree = c.icloud / "entree"
        entree.mkdir(parents=True, exist_ok=True)
        (entree / "arnaque-2.txt").write_text(ARNAQUE_CORPS.decode(), encoding="utf-8")
        reponse = c.icloud / "reponses" / "arnaque-2.txt"
        for _ in range(200):
            if reponse.exists():
                break
            threading.Event().wait(0.05)
        assert reponse.exists() and not libere.is_set()  # répondu pendant que l'inventaire tourne encore
        assert fils == ["bouclier-taches"]
    finally:
        libere.set()
        arret.set()
        boucle.join(20)
    assert not boucle.is_alive()
    assert float(base.lire_meta("prochain:inventaire") or 0) > 0


def test_verification_reelle_imitee(maison: Path) -> None:
    """`installation verifier` : kill puis relance, aller-retour iCloud, et chaque échec dit clairement."""
    c = config.chemins()
    c.icloud.mkdir(parents=True)
    reglages = config.charger()
    base = db.ouvrir(c.base)
    pids, temps, relance, repond = [100], [0.0], [True], [True]

    def executer(a: Sequence[str], e: str | None, d: float) -> Resultat:
        if a[:2] == ["launchctl", "print"]:
            return Resultat(0, f"state = running\n\tpid = {pids[-1]}\n") if pids[-1] else Resultat(113, "")
        if a[0] == "kill" and relance[0]:
            pids.append(pids[-1] + 1)
        return Resultat(0, "")

    def attendre(s: float) -> None:  # pendant l'attente, le « démon » répond à ce qui est déposé
        temps[0] += s
        for f in (c.icloud / "entree").glob("bouclier-verif-*") if repond[0] else []:
            reponse = c.icloud / "reponses" / f"{f.stem}.txt"
            reponse.parent.mkdir(exist_ok=True)
            lu = f.suffix == ".txt"
            reponse.write_text("⚪ Pas de signe d'arnaque détecté\n" if lu else "⚠️ Je n'ai pas pu lire ça\n")

    def verifier() -> installation.Bilan:
        systeme = Systeme(executer, mac=True)
        return installation.verifier_reel(c, reglages, base, systeme, attendre, lambda: temps[0])

    b = verifier()
    assert b.refus == [] and "kill 100 : relancé par launchd en 0 s (pid 101)" in b.fait
    assert any(f.startswith("texte déposé dans iCloud : réponse du démon") for f in b.fait)
    assert any(a.startswith("capture d'écran : reçu mais pas lu") for a in b.avertissements)
    assert list((c.icloud / "entree").iterdir()) == [] and list((c.icloud / "reponses").iterdir()) == []

    repond[0] = False
    b = verifier()
    assert any("pas de réponse en 60 s" in r for r in b.refus) and list((c.icloud / "entree").iterdir()) == []
    relance[0] = False
    assert "n'a pas relancé le démon en 90 s" in verifier().refus[0]
    pids.append(0)
    assert "n'est pas lancé par launchd" in verifier().refus[0]
    pids.append(200)
    relance[0] = True
    shutil.rmtree(c.icloud)
    assert "aller-retour du raccourci non vérifié" in verifier().avertissements[0]


def test_boucle_au_repos_econome(mac: Environnement) -> None:
    """Au repos (rien dans l'entrée iCloud), 100 tours de 3 s n'écrivent presque rien sur le disque : un battement
    toutes les 30 s ; les réglages ne sont relus que si config.toml change (le Nettoyeur surveille l'énergie)."""
    c, base, _, _, _, _, t = mac
    d = _demon(mac)
    d.tour_rapide()
    avant = base.cx.total_changes
    for _ in range(100):
        t[0] += 3
        d.tour_rapide()
    assert base.cx.total_changes - avant <= 10
    assert d.reglages()["gmail"]["adresse"] == "camille@example.org"
    c.config.write_text('[gmail]\nadresse = "autre@example.org"\nactive = false\n', encoding="utf-8")
    assert d.reglages()["gmail"]["active"] is False and d.taches_dues(d.reglages())[:1] != ["gmail"]
    c.config.write_text("[gmail\n", encoding="utf-8")
    assert d.reglages()["gmail"]["active"] is True and "ne se lit pas" in (base.lire_meta("config_alerte") or "")


def test_portes_pour_l_assistant(mac: Environnement, capsys: pytest.CaptureFixture[str]) -> None:
    """INTEGRATION.md : `etat.json` (écrit avec le tableau de bord) et `bouclier verifier --json`."""
    c, base, systeme, _, _, _, t = mac
    _demon(mac).tour()
    etat = json.loads((c.tableau_de_bord.with_name("etat.json")).read_text(encoding="utf-8"))
    assert set(etat) == {"mis_a_jour", "hygiene", "arnaques_7_jours", "comptes", "fuites", "fiche_urgence"}
    assert 0 <= etat["hygiene"]["score"] <= 100 and etat["fiche_urgence"] == "a_jour" and etat["fuites"] >= 1
    assert (c.tableau_de_bord.with_name("etat.json").stat().st_mode & 0o777) == 0o600
    capsys.readouterr()
    assert cli.main(["verifier", "--json", ARNAQUE_CORPS.decode()], systeme) == 0
    r = json.loads(capsys.readouterr().out.strip())
    assert r["niveau"] == "arnaque" and r["pastille"] == "🔴" and r["raisons"] and r["gestes"]
