"""Le 2e faux Mac (§9.2), tiré au hasard à partir d'une graine, construit APRÈS le réglage des règles : noms,
éditeurs, nombres d'éléments, sources, chemins (espaces, accents), consommations et dates d'usage changent à chaque
graine. Les règles ne peuvent donc pas avoir été taillées sur la vérité terrain du faux Mac n° 1.
"""

from __future__ import annotations

import random
from pathlib import Path

from tests.demarrage.faux_mac.construire import (
    LA,
    MAISON,
    Attendu,
    Construction,
    Plante,
    Processus,
    assembler,
)
from tests.demarrage.faux_mac.systeme_faux import FauxMac
from tests.demarrage.outils import signe_par

# Des noms inventés, qui ne ressemblent à aucune entrée de la base de connaissances.
MOTS = ["ecureuil", "murier", "zebre", "hetre", "ondine", "pivoine", "lagune", "brindille", "colibri", "falaise",
        "girolle", "houblon", "jonquille", "lilas", "mistral", "noisette", "orque", "pelican", "quetsche", "renard",
        "sureau", "tilleul", "verveine", "wapiti", "yourte", "zinnia", "airelle", "bruyere", "cerfeuil", "dune"]  # fmt: skip
JOLIS = ["Écureuil", "Mûrier Studio", "Zèbre & Cie", "Hêtre", "Ondine Pro", "Pivoine", "Lagune Café", "Brindille",
         "Colibri Été", "Falaise Noël"]  # fmt: skip


class Tirage:
    def __init__(self, graine: int):
        self.r = random.Random(graine)
        self.mots = list(MOTS)
        self.r.shuffle(self.mots)
        self.pid = 4000

    def mot(self) -> str:
        return self.mots.pop()

    def nouveau_pid(self) -> int:
        self.pid += self.r.randint(1, 40)
        return self.pid

    def entre(self, a: float, b: float) -> float:
        return self.r.uniform(a, b)

    def app(self) -> tuple[str, str, str]:
        mot = self.mot()
        nom = f"{self.r.choice(JOLIS)} {mot.capitalize()}"
        return f"/Applications/{nom}.app", f"fr.{mot}.app", nom


def construire_aleatoire(racine: Path, graine: int) -> Construction:
    t = Tirage(graine)
    mac = FauxMac(racine)
    plantes: list[Plante] = []
    autres: list[Processus] = []

    # Apple : entre 15 et 40 éléments, dont certains chargés et un Spotlight gourmand à l'ouverture.
    for i in range(t.r.randint(15, 40)):
        dossier = t.r.choice(["LaunchAgents", "LaunchDaemons"])
        label = f"com.apple.{t.r.choice(MOTS)}{i}"
        prog = f"/System/Library/CoreServices/{label}.app/Contents/MacOS/x"
        charge = dossier == "LaunchAgents" and t.r.random() < 0.5
        pid = t.nouveau_pid() if charge else None
        p = Plante(label, "apple", Attendu("apple", "aucune"), f"/System/Library/{dossier}/{label}.plist",
                   {"Label": label, "Program": prog, "RunAtLoad": True}, binaire=t.r.random() < 0.3,
                   programmes=[prog], charge=charge, pid=pid)  # fmt: skip
        if pid:
            p.processus.append(Processus(pid, prog, [(t.entre(-2, 5), t.entre(0, 0.01))], rss_mo=t.entre(10, 80)))
        plantes.append(p)
    autres.append(Processus(250, "/System/Library/Frameworks/CoreServices.framework/Support/mds_stores",
                            [(0.0, t.entre(0.8, 1.5)), (t.entre(100, 200), 0.01)], uid=0, rss_mo=300, puissance=20))  # fmt: skip

    def agent(role: str, attendu: Attendu, source: str = "agent_utilisateur", *, jours: float,
              profil: list[tuple[float, float]], rss: float, enfant_rss: float = 0.0, puissance: float = 0.0,
              assertion: str | None = None, garder: bool = False, relances: int | None = None,
              code: int | None = None, signe: bool = True, binaire: bool | None = None) -> Plante:  # fmt: skip
        chemin_app, bundle, nom = t.app()
        exe = f"{chemin_app}/Contents/MacOS/{role}"
        label = f"com.{bundle.split('.')[1]}.{role}"
        dossier = LA if source == "agent_utilisateur" else "/Library/LaunchAgents"
        contenu: dict = {"Label": label, "ProgramArguments": [exe], "RunAtLoad": True}
        if garder:
            contenu["KeepAlive"] = True
        pid = t.nouveau_pid()
        procs = [Processus(pid, exe, profil, rss_mo=rss, puissance=puissance, assertion=assertion)]
        if enfant_rss:
            procs.append(Processus(t.nouveau_pid(), f"{chemin_app}/Contents/MacOS/{role}-moteur", [(profil[0][0] + 3, 0.01)],
                                   ppid=pid, rss_mo=enfant_rss))  # fmt: skip
        editeur = nom.replace("&", "et")
        return Plante(label, source, attendu, f"{dossier}/{label}.plist", contenu,
                      binaire=t.r.random() < 0.4 if binaire is None else binaire, programmes=[exe],
                      signatures={exe: signe_par(editeur, f"{bundle.split('.')[1][:6].upper():0<10}")} if signe else {},
                      app=(chemin_app, bundle, nom, jours), charge=True, pid=None if relances else pid,
                      relances=relances, dernier_code=code, processus=procs)  # fmt: skip

    peu = lambda: t.entre(31, 200)  # noqa: E731 — une app pas ouverte depuis plus de 30 jours
    souvent = lambda: t.entre(0, 20)  # noqa: E731
    source_lourd = t.r.choice(["agent_utilisateur", "agent_global"])
    action_lourd = "desactiver" if source_lourd == "agent_utilisateur" else "instructions"
    debut = t.entre(1, 8)
    plantes += [
        agent("indexeur", Attendu("inutile", action_lourd, lourd=True), source_lourd, jours=peu(),
              profil=[(debut, t.entre(0.6, 1.0)), (debut + t.entre(200, 280), t.entre(0.005, 0.02))],
              rss=t.entre(200, 500), puissance=t.entre(8, 20)),
        agent("moteur", Attendu("inutile", "desactiver", lourd=True), jours=peu(),
              profil=[(debut, t.entre(0.1, 0.3)), (debut + 100, t.entre(0.03, 0.06))], rss=t.entre(80, 200),
              enfant_rss=t.entre(1200, 3000), puissance=t.entre(4, 10)),
        agent("eveil", Attendu("inutile", "desactiver", empeche_veille=True, lourd=True), jours=peu(),
              profil=[(debut, t.entre(0.03, 0.08)), (300.0, t.entre(0.005, 0.01))], rss=t.entre(50, 150),
              puissance=t.entre(1, 4), assertion=t.r.choice(["PreventUserIdleSystemSleep", "PreventSystemSleep"])),
        agent("relance", Attendu("inutile", "desactiver"), jours=peu(), garder=True, relances=t.r.randint(50, 1000),
              code=t.r.randint(1, 255), profil=[(debut, t.entre(0.02, 0.04)), (300.0, 0.005)], rss=t.entre(20, 40)),
    ]  # fmt: skip
    for _ in range(t.r.randint(1, 3)):  # utiles et légers
        plantes.append(agent("raccourcis", Attendu("utile", "desactiver"), jours=souvent(),
                             profil=[(debut, t.entre(0.001, 0.005))], rss=t.entre(10, 40)))  # fmt: skip
    for _ in range(t.r.randint(1, 2)):  # outils de mise à jour légers, quelle que soit l'utilisation de l'app
        plantes.append(agent(t.r.choice(["updater", "autoupdate", "Updater.agent", "softwareupdate"]),
                             Attendu("inutile", "desactiver"), jours=t.r.choice([peu(), souvent()]),
                             profil=[(debut, t.entre(0.005, 0.02)), (60.0, 0.0)], rss=t.entre(10, 30)))  # fmt: skip
    for _ in range(t.r.randint(1, 3)):  # orphelins : programme disparu
        mot = t.mot()
        label = f"com.{mot}.agent"
        plantes.append(Plante(label, "agent_utilisateur", Attendu("orphelin", "quarantaine"), f"{LA}/{label}.plist",
                              {"Label": label, "Program": f"/Applications/{t.r.choice(JOLIS)}.app/Contents/MacOS/{mot}",
                               "RunAtLoad": True}, binaire=t.r.random() < 0.5))  # fmt: skip
    for _ in range(t.r.randint(1, 2)):  # orphelins : l'app associée est désinstallée
        mot = t.mot()
        label, prog = f"com.{mot}.compagnon", f"{MAISON}/Library/Application Support/{mot.capitalize()} Été/compagnon"
        plantes.append(Plante(label, "agent_utilisateur", Attendu("orphelin", "quarantaine"), f"{LA}/{label}.plist",
                              {"Label": label, "Program": prog, "AssociatedBundleIdentifiers": [f"fr.{mot}.disparue"]},
                              programmes=[prog], signatures={prog: signe_par(f"{mot.capitalize()} SAS", "ORPHELIN01")}))  # fmt: skip
    for _ in range(t.r.randint(1, 3)):  # inconnus non signés : à vérifier, jamais à supprimer
        mot = t.mot()
        label, prog = f"com.{mot}.service", f"{MAISON}/Library/Application Support/.{mot}/service"
        pid = t.nouveau_pid()
        plantes.append(Plante(label, "agent_utilisateur", Attendu("inconnu", "verifier"), f"{LA}/{label}.plist",
                              {"Label": label, "ProgramArguments": [prog], "RunAtLoad": True, "KeepAlive": True},
                              programmes=[prog], charge=True, pid=pid,
                              processus=[Processus(pid, prog, [(debut, t.entre(0.001, 0.01))], rss_mo=t.entre(5, 30))]))  # fmt: skip
    # Cas tordus : plist corrompu, doublon S1/S2.
    mot = t.mot()
    plantes.append(Plante(f"com.{mot}.casse", "agent_utilisateur", Attendu("inconnu", "verifier"),
                          f"{LA}/com.{mot}.casse.plist", b"<?xml version='1.0'?><plist><dict><key>Lab"))  # fmt: skip
    chemin_app, bundle, nom = t.app()
    exe = f"{chemin_app}/Contents/MacOS/double"
    signature = {exe: signe_par(nom, "DOUBLON001")}
    for source, dossier, action in [
        ("agent_utilisateur", LA, "desactiver"),
        ("agent_global", "/Library/LaunchAgents", "instructions"),
    ]:
        plantes.append(Plante(f"com.{bundle.split('.')[1]}.double", source, Attendu("utile", action),
                              f"{dossier}/com.{bundle.split('.')[1]}.double.plist",
                              {"Label": f"com.{bundle.split('.')[1]}.double", "Program": exe}, programmes=[exe],
                              signatures=signature, app=(chemin_app, bundle, nom, souvent())))  # fmt: skip
    # Ouverture de session (System Events) : une app utilisée, une app disparue.
    chemin_app, bundle, nom = t.app()
    pid = t.nouveau_pid()
    plantes.append(Plante(bundle, "ouverture", Attendu("utile", "reglages"), app=(chemin_app, bundle, nom, souvent()),
                          processus=[Processus(pid, f"{chemin_app}/Contents/MacOS/{Path(chemin_app).stem}",
                                               [(debut + 5, t.entre(0.02, 0.1)), (70.0, 0.002)], rss_mo=t.entre(50, 200))]))  # fmt: skip
    disparue = f"{t.r.choice(JOLIS)} Partie"
    plantes.append(Plante(disparue, "ouverture", Attendu("orphelin", "reglages")))
    t.r.shuffle(plantes)
    return assembler(mac, plantes, autres, apps=[],
                     login_items=[(nom, chemin_app), (disparue, f"/Applications/{disparue}.app")])  # fmt: skip
