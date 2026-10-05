"""Le faux Mac, juge principal (§9.2) : une racine « / » simulée, les sorties de chaque commande, des processus qui
vivent dans le temps (horloge simulée), et la vérité terrain de chaque élément planté.

    construction = construire(tmp_path)        # le faux Mac n° 1, fixe
    construction.mac                           # le Systeme à donner au scan et à la mesure
    construction.verite                        # (source, label) → Attendu

Les processus suivent un profil de charge par morceaux (cœurs utilisés à partir de tel instant après l'ouverture
de session) : « ps » donne le temps processeur cumulé exact, « top » l'énergie, « pmset » les assertions de veille.
"""

from __future__ import annotations

import plistlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modules.demarrage.systeme import Resultat
from tests.demarrage.faux_mac.systeme_faux import FauxMac
from tests.demarrage.outils import SIGNE_APPLE, signe_par

BOOT = 1_791_176_000.0  # lundi 5 octobre 2026, 06:53:20 à Paris
CONNEXION = BOOT + 52.0
UID = 501
MAISON = "/Users/utilisateur"
LA = f"{MAISON}/Library/LaunchAgents"
JOUR = 86400.0
COEURS = 8
T = "\t"


@dataclass
class Processus:
    pid: int
    comm: str
    profil: list[tuple[float, float]]  # (secondes après la connexion, cœurs utilisés à partir de là)
    ppid: int = 1
    uid: int = UID
    rss_mo: float = 20.0
    puissance: float = 0.0  # colonne POWER de top (impact énergétique)
    assertion: str | None = None  # PreventUserIdleSystemSleep, PreventSystemSleep…
    fin: float | None = None  # secondes après la connexion

    @property
    def debut(self) -> float:
        return self.profil[0][0]

    def vivant(self, t: float) -> bool:
        return self.debut <= t and (self.fin is None or t < self.fin)

    def coeurs(self, t: float) -> float:
        actuel = 0.0
        for depuis, c in self.profil:
            if t >= depuis:
                actuel = c
        return actuel

    def cumul(self, t: float) -> float:
        """Secondes de processeur consommées depuis son lancement jusqu'à t."""
        fin = min(t, self.fin) if self.fin is not None else t
        total = 0.0
        for i, (depuis, c) in enumerate(self.profil):
            jusqua = self.profil[i + 1][0] if i + 1 < len(self.profil) else fin
            total += c * max(0.0, min(jusqua, fin) - depuis)
        return total


@dataclass
class Attendu:
    verdict: str  # apple, utile, inutile, orphelin, inconnu
    action: str  # aucune, desactiver, quarantaine, instructions, verifier, reglages
    empeche_veille: bool = False
    lourd: bool = False  # un des 3 plus lourds
    notes: str = ""


@dataclass
class Plante:
    label: str
    source: str
    attendu: Attendu
    chemin_plist: str | None = None
    contenu: dict[str, Any] | bytes | None = None  # bytes : un plist cassé, tel quel
    binaire: bool = False
    programmes: list[str] = field(default_factory=list)  # fichiers à créer (ceux qui existent)
    signatures: dict[str, str] = field(default_factory=dict)  # chemin → sortie codesign (absent : non signé)
    app: tuple[str, str, str, float | None] | None = None  # (chemin, bundle id, nom, jours depuis l'usage)
    charge: bool = False
    pid: int | None = None
    relances: int | None = None
    dernier_code: int | None = None
    desactive: bool | None = None  # surcharge launchctl disable
    processus: list[Processus] = field(default_factory=list)


@dataclass
class Construction:
    mac: FauxMac
    plantes: list[Plante]
    processus: list[Processus]
    connexion: float = CONNEXION
    boot: float = BOOT
    apps_installees: list[tuple[str, str, str, float | None]] = field(default_factory=list)
    login_items: list[tuple[str, str]] = field(default_factory=list)  # (nom, chemin) vus par System Events

    @property
    def verite(self) -> dict[tuple[str, str], Attendu]:
        return {(p.source, p.label): p.attendu for p in self.plantes}

    def plante(self, label: str) -> Plante:
        return next(p for p in self.plantes if p.label == label)

    def a_l_instant(self, secondes_apres_connexion: float) -> None:
        self.mac.horloge = self.connexion + secondes_apres_connexion


# --- les sorties de commandes, calculées à l'instant présent --------------------------------------------------------


def _duree_ps(s: float) -> str:
    s = int(s)
    j, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if j:
        return f"{j:02d}-{h:02d}:{m:02d}:{s:02d}"
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _temps_ps(s: float) -> str:
    m, reste = divmod(s, 60)
    return f"{int(m)}:{reste:05.2f}"


def sortie_ps(c: Construction) -> str:
    t = c.mac.horloge - c.connexion
    lignes = []
    for p in c.processus:
        if not p.vivant(t):
            continue
        age = t - p.debut
        lignes.append(
            f"{p.pid:>5} {p.ppid:>5} {p.uid:>5} {p.coeurs(t) * 100:>5.1f} {int(p.rss_mo * 1024):>8} "
            f"{_duree_ps(age):>11} {_temps_ps(p.cumul(t)):>10} {p.comm}"
        )
    return "\n".join(lignes) + "\n"


def sortie_top(c: Construction) -> str:
    t = c.mac.horloge - c.connexion
    vivants = sorted((p for p in c.processus if p.vivant(t)), key=lambda p: p.puissance, reverse=True)[:25]
    entete = "Processes: 412 total, 2 running, 410 sleeping, 1999 threads\nPID    COMMAND          %CPU MEM    POWER\n"
    lignes = [
        f"{p.pid:<6} {Path(p.comm).name[:16]:<16} {p.coeurs(t) * 100:<4.1f} {int(p.rss_mo)}M{'':<3} {p.puissance:.1f}"
        for p in vivants
    ]
    premier = "\n".join(f"{p.pid:<6} {Path(p.comm).name[:16]:<16} 0.0  {int(p.rss_mo)}M    0.0" for p in vivants)
    return f"{entete}{premier}\n\n{entete}" + "\n".join(lignes) + "\n"


def sortie_pmset(c: Construction) -> str:
    t = c.mac.horloge - c.connexion
    lignes = ["Assertion status system-wide:", "   PreventUserIdleSystemSleep    1", "Listed by owning process:"]
    for i, p in enumerate(c.processus):
        if p.assertion and p.vivant(t):
            nom = Path(p.comm).name
            lignes.append(f'   pid {p.pid}({nom}): [0x0000{i:012x}] 00:10:00 {p.assertion} named: "{nom} travaille"')
    lignes.append("Kernel Assertions: 0x4=USB")
    return "\n".join(lignes) + "\n"


def sortie_launchctl_gui(c: Construction) -> str:
    services, desactives = [], []
    for p in c.plantes:
        if p.charge and p.source in ("agent_utilisateur", "agent_global", "agent_app", "ouverture_app", "apple"):
            code = "-" if p.dernier_code is None else str(p.dernier_code)
            services.append(f"{T}{T}{p.pid or 0:>8}      {code:<6} {p.label}")
        if p.desactive is not None:
            desactives.append(f'{T}{T}"{p.label}" => {"disabled" if p.desactive else "enabled"}')
    return (
        f"gui/{UID} = {{\n{T}type = gui\n{T}services = {{\n" + "\n".join(services) + f"\n{T}}}\n\n"
        f"{T}disabled services = {{\n" + "\n".join(desactives) + f"\n{T}}}\n}}\n"
    )


def sortie_launchctl_list(c: Construction) -> str:
    lignes = ["PID\tStatus\tLabel"]
    for p in c.plantes:
        if p.charge and p.source in ("agent_utilisateur", "agent_global", "agent_app", "ouverture_app", "apple"):
            lignes.append(f"{p.pid or '-'}\t{p.dernier_code or 0}\t{p.label}")
    lignes.append("9999\t0\tapplication.com.apple.Safari.1234.5678")
    return "\n".join(lignes) + "\n"


def sortie_print_service(p: Plante) -> str:
    code = f"{T}last exit code = {p.dernier_code}\n" if p.dernier_code is not None else ""
    return (
        f"gui/{UID}/{p.label} = {{\n{T}path = {p.chemin_plist}\n{T}program = {p.programmes[0] if p.programmes else ''}\n"
        f"{T}runs = {p.relances or 1}\n{code}}}\n"
    )


# --- la construction ----------------------------------------------------------------------------------------------


def _ecrire_plist(mac: FauxMac, p: Plante) -> None:
    if p.chemin_plist is None or p.contenu is None:
        return
    if isinstance(p.contenu, bytes):
        mac.fichier(p.chemin_plist, p.contenu)
    else:
        mac.fichier(
            p.chemin_plist, plistlib.dumps(p.contenu, fmt=plistlib.FMT_BINARY if p.binaire else plistlib.FMT_XML)
        )


def _ecrire_app(mac: FauxMac, chemin: str, bundle_id: str, nom: str) -> str:
    executable = Path(chemin).name.removesuffix(".app")
    mac.fichier(
        f"{chemin}/Contents/Info.plist",
        plistlib.dumps({"CFBundleIdentifier": bundle_id, "CFBundleName": nom, "CFBundleExecutable": executable}),
    )
    mac.fichier(f"{chemin}/Contents/MacOS/{executable}", b"\xcf\xfa\xed\xfe")
    return f"{chemin}/Contents/MacOS/{executable}"


def assembler(mac: FauxMac, plantes: list[Plante], autres: list[Processus], apps: list[tuple[str, str, str, float | None]],
              login_items: list[tuple[str, str]] | None = None, systeme_lisible: bool = False) -> Construction:  # fmt: skip
    """Écrit tout sur le faux Mac et branche les réponses de commandes."""
    c = Construction(mac, plantes, [*autres, *(x for p in plantes for x in p.processus)], apps_installees=apps,
                     login_items=login_items or [])  # fmt: skip
    signatures: dict[str, str] = {}
    usages: dict[str, float | None] = {}
    for chemin, bundle_id, nom, jours in apps:
        exe = _ecrire_app(mac, chemin, bundle_id, nom)
        usages[chemin] = jours
        signatures.setdefault(exe, signe_par(f"Éditeur de {nom}", "EDITEUR001"))
    for p in plantes:
        _ecrire_plist(mac, p)
        for prog in p.programmes:
            mac.fichier(prog, b"\xcf\xfa\xed\xfe programme")
        signatures.update(p.signatures)
        if p.app:
            chemin, bundle_id, nom, jours = p.app
            exe = _ecrire_app(mac, chemin, bundle_id, nom)
            usages[chemin] = jours
            signatures.setdefault(exe, p.signatures.get(exe, signe_par(f"Éditeur de {nom}", "EDITEUR002")))

    def codesign(commande: list[str], m: FauxMac) -> Resultat:
        chemin = commande[-1]
        if not m.chemin(chemin).exists():
            return Resultat(1, "", f"{chemin}: No such file or directory\n")
        sortie = signatures.get(chemin)
        if sortie is None and chemin.startswith(("/System/", "/usr/", "/bin/", "/sbin/")):
            sortie = SIGNE_APPLE
        if sortie is None:
            return Resultat(1, "", f"{chemin}: code object is not signed at all\n")
        return Resultat(0, "", f"Executable={chemin}\n{sortie}")

    def mdls(commande: list[str], m: FauxMac) -> Resultat:
        jours = usages.get(commande[-1])
        if jours is None:
            return Resultat(0, "(null)")
        import time as _t

        quand = c.connexion - jours * JOUR
        return Resultat(0, _t.strftime("%Y-%m-%d %H:%M:%S +0000", _t.gmtime(quand)))

    mac.repondre_debut(["codesign"], codesign)
    mac.repondre_debut(["mdls"], mdls)
    mac.repondre(["launchctl", "print", f"gui/{UID}"], lambda cmd, m: Resultat(0, sortie_launchctl_gui(c)))
    mac.repondre(["launchctl", "list"], lambda cmd, m: Resultat(0, sortie_launchctl_list(c)))
    mac.repondre(
        ["launchctl", "print-disabled", f"gui/{UID}"], lambda cmd, m: Resultat(0, "disabled services = {\n}\n")
    )
    if systeme_lisible:
        mac.repondre(["launchctl", "print", "system"], "services = {\n}\n")
    else:
        mac.repondre(
            ["launchctl", "print", "system"], "", code=1, erreur="Could not print domain: Operation not permitted"
        )
    for p in plantes:
        if p.charge:
            mac.repondre(["launchctl", "print", f"gui/{UID}/{p.label}"], sortie_print_service(p))
    mac.repondre_debut(["ps"], lambda cmd, m: Resultat(0, sortie_ps(c)))
    mac.repondre_debut(["top"], lambda cmd, m: Resultat(0, sortie_top(c)))
    mac.repondre(["pmset", "-g", "assertions"], lambda cmd, m: Resultat(0, sortie_pmset(c)))
    mac.repondre(["sysctl", "-n", "kern.boottime"], f"{{ sec = {int(c.boot)}, usec = 0 }} Mon Oct  5 06:53:20 2026\n")
    mac.repondre(["sysctl", "-n", "hw.ncpu"], f"{COEURS}\n")
    mac.repondre(["uname", "-m"], "arm64\n")
    mac.repondre(["sw_vers", "-productVersion"], "26.0\n")
    return c


# --- le faux Mac n° 1 : les cas du §9.2, fixes -------------------------------------------------------------------------

APPLE_AGENTS = [
    "com.apple.Finder", "com.apple.Dock.agent", "com.apple.notificationcenterui.agent", "com.apple.Spotlight",
    "com.apple.cloudd", "com.apple.bird", "com.apple.photoanalysisd", "com.apple.mediaanalysisd",
    "com.apple.knowledge-agent", "com.apple.siriknowledged", "com.apple.WindowManager.agent", "com.apple.coreservices.uiagent",
]  # fmt: skip
APPLE_DAEMONS = ["com.apple.metadata.mds", "com.apple.backupd", "com.apple.softwareupdated", "com.apple.mDNSResponder",
                 "com.apple.powerd", "com.apple.WindowServer"]  # fmt: skip


def _apple(mac: FauxMac) -> tuple[list[Plante], list[Processus]]:
    plantes: list[Plante] = []
    autres: list[Processus] = []
    for i, label in enumerate(APPLE_AGENTS):
        prog = f"/System/Library/CoreServices/{label.split('.')[-1]}.app/Contents/MacOS/{label.split('.')[-1]}"
        p = Plante(label, "apple", Attendu("apple", "aucune"), f"/System/Library/LaunchAgents/{label}.plist",
                   {"Label": label, "Program": prog, "RunAtLoad": True}, programmes=[prog], charge=True, pid=600 + i)  # fmt: skip
        p.processus.append(Processus(600 + i, prog, [(-1.0, 0.002)], rss_mo=60))
        plantes.append(p)
    for i, label in enumerate(APPLE_DAEMONS):
        prog = f"/usr/libexec/{label.split('.')[-1]}"
        plantes.append(Plante(label, "apple", Attendu("apple", "aucune"), f"/System/Library/LaunchDaemons/{label}.plist",
                              {"Label": label, "Program": prog, "RunAtLoad": True, "KeepAlive": True},
                              programmes=[prog]))  # fmt: skip
        autres.append(Processus(200 + i, prog, [(-50.0, 0.005)], uid=0, rss_mo=30))
    # Spotlight indexe fort à l'ouverture de session : lourd, mais Apple. Jamais d'action.
    autres.append(Processus(250, "/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/Metadata.framework/Versions/A/Support/mds_stores",
                            [(0.0, 1.2), (180.0, 0.01)], uid=0, rss_mo=300, puissance=25))  # fmt: skip
    autres += [
        Processus(1, "/sbin/launchd", [(-52.0, 0.002)], ppid=0, uid=0, rss_mo=14),
        Processus(0, "kernel_task", [(-52.0, 0.05)], ppid=0, uid=0, rss_mo=13),
        Processus(
            391,
            "/System/Library/CoreServices/loginwindow.app/Contents/MacOS/loginwindow",
            [(-30.0, 0.003)],
            uid=0,
            rss_mo=40,
        ),  # fmt: skip
    ]
    return plantes, autres


def construire(racine: Path, systeme_lisible: bool = False) -> Construction:
    mac = FauxMac(racine)
    plantes, autres = _apple(mac)
    adobe = "/Applications/Adobe Creative Cloud/Adobe Creative Cloud.app"
    adobe_exe = f"{adobe}/Contents/MacOS/Creative Cloud"
    docker = "/Applications/Docker.app"
    sauvegarde = "/Applications/Sauvegarde Express.app"
    boucle = "/Applications/Radio Boucle.app"
    chrome = "/Applications/Google Chrome.app"
    keystone = f"{MAISON}/Library/Google/GoogleSoftwareUpdate/GoogleSoftwareUpdate.bundle/Contents/Resources/GoogleSoftwareUpdateAgent.app/Contents/MacOS/GoogleSoftwareUpdateAgent"
    notes = "/Applications/Notes Rapides.app"
    cafe = "/Applications/Éditeur Café.app"
    adobe_sig = signe_par("Adobe Inc.", "JQ525L2MZD")
    plantes += [
        # Lourd n° 1 : beaucoup de processeur à l'ouverture de session (S2, global : instructions seulement).
        Plante("com.adobe.AdobeCreativeCloud", "agent_global", Attendu("inutile", "instructions", lourd=True),
               "/Library/LaunchAgents/com.adobe.AdobeCreativeCloud.plist",
               {"Label": "com.adobe.AdobeCreativeCloud", "ProgramArguments": [adobe_exe, "--showwindow=false"],
                "RunAtLoad": True},
               programmes=[adobe_exe], signatures={adobe_exe: adobe_sig},
               app=(adobe, "com.adobe.acc.AdobeCreativeCloud", "Creative Cloud", 60),
               charge=True, pid=3001,
               processus=[Processus(3001, adobe_exe, [(2.0, 0.9), (240.0, 0.02)], rss_mo=380, puissance=15),
                          Processus(3002, f"{adobe}/Contents/Frameworks/Core Sync.app/Contents/MacOS/Core Sync",
                                    [(5.0, 0.3), (200.0, 0.0)], ppid=3001, rss_mo=60)]),
        # Lourd n° 2 : beaucoup de mémoire en continu (via un processus fils).
        Plante("com.docker.socket", "agent_utilisateur", Attendu("inutile", "desactiver", lourd=True),
               f"{LA}/com.docker.socket.plist",
               {"Label": "com.docker.socket", "Program": f"{docker}/Contents/MacOS/com.docker.backend", "RunAtLoad": True,
                "KeepAlive": {"SuccessfulExit": False}},
               signatures={f"{docker}/Contents/MacOS/com.docker.backend": signe_par("Docker Inc", "9BNSXJN65R")},
               programmes=[f"{docker}/Contents/MacOS/com.docker.backend"],
               app=(docker, "com.docker.docker", "Docker", 75), charge=True, pid=3101, relances=1, dernier_code=0,
               processus=[Processus(3101, f"{docker}/Contents/MacOS/com.docker.backend", [(3.0, 0.3), (120.0, 0.04)],
                                    rss_mo=150, puissance=8),
                          Processus(3102, f"{docker}/Contents/MacOS/com.docker.virtualization", [(10.0, 0.02)],
                                    ppid=3101, rss_mo=1500)]),
        # Lourd n° 3 : empêche la veille.
        Plante("com.sauvegarde.express.agent", "agent_utilisateur", Attendu("inutile", "desactiver", empeche_veille=True, lourd=True),
               f"{LA}/com.sauvegarde.express.agent.plist",
               {"Label": "com.sauvegarde.express.agent", "ProgramArguments": [f"{sauvegarde}/Contents/MacOS/agent"],
                "RunAtLoad": True},
               signatures={f"{sauvegarde}/Contents/MacOS/agent": signe_par("Sauvegarde Express SARL", "SAUVE00001")},
               programmes=[f"{sauvegarde}/Contents/MacOS/agent"],
               app=(sauvegarde, "fr.sauvegarde.express", "Sauvegarde Express", 50), charge=True, pid=3201,
               processus=[Processus(3201, f"{sauvegarde}/Contents/MacOS/agent", [(4.0, 0.05), (300.0, 0.01)],
                                    rss_mo=120, puissance=3, assertion="PreventUserIdleSystemSleep")]),
        # Redémarre en boucle (KeepAlive, sorties en erreur).
        Plante("com.radioboucle.helper", "agent_utilisateur", Attendu("inutile", "desactiver"),
               f"{LA}/com.radioboucle.helper.plist",
               {"Label": "com.radioboucle.helper", "ProgramArguments": [f"{boucle}/Contents/MacOS/helper"],
                "RunAtLoad": True, "KeepAlive": True},
               signatures={f"{boucle}/Contents/MacOS/helper": signe_par("Radio Boucle Ltd", "BOUCLE0001")},
               programmes=[f"{boucle}/Contents/MacOS/helper"], app=(boucle, "com.radioboucle", "Radio Boucle", 35),
               charge=True, pid=None, relances=412, dernier_code=1,
               processus=[Processus(3301, f"{boucle}/Contents/MacOS/helper", [(1.0, 0.03), (300.0, 0.005)], rss_mo=30,
                                    puissance=1)]),
        # Orphelin n° 1 : le programme n'existe plus (app désinstallée).
        Plante("com.exemple.desinstalle.agent", "agent_utilisateur", Attendu("orphelin", "quarantaine"),
               f"{LA}/com.exemple.desinstalle.agent.plist",
               {"Label": "com.exemple.desinstalle.agent", "Program": "/Applications/Désinstallé.app/Contents/MacOS/agent",
                "RunAtLoad": True}, charge=True, pid=None, dernier_code=78),
        # Orphelin n° 2 : le programme est là, mais l'app à laquelle il appartient a été désinstallée.
        Plante("com.spotify.webhelper", "agent_utilisateur", Attendu("orphelin", "quarantaine"),
               f"{LA}/com.spotify.webhelper.plist",
               {"Label": "com.spotify.webhelper", "Program": f"{MAISON}/Library/Application Support/Spotify/SpotifyWebHelper",
                "RunAtLoad": True, "AssociatedBundleIdentifiers": ["com.spotify.client"]},
               programmes=[f"{MAISON}/Library/Application Support/Spotify/SpotifyWebHelper"],
               signatures={f"{MAISON}/Library/Application Support/Spotify/SpotifyWebHelper": signe_par("Spotify AB", "2FNC3A47ZF")},
               charge=True, pid=3401,
               processus=[Processus(3401, f"{MAISON}/Library/Application Support/Spotify/SpotifyWebHelper", [(6.0, 0.002)],
                                    rss_mo=15)]),
        # Outil de mise à jour d'une app pas ouverte depuis 90 jours (plist binaire).
        Plante("com.google.keystone.agent", "agent_utilisateur", Attendu("inutile", "desactiver"),
               f"{LA}/com.google.keystone.agent.plist",
               {"Label": "com.google.keystone.agent", "ProgramArguments": [keystone, "-runMode", "ifneeded"],
                "RunAtLoad": True, "StartInterval": 3523},
               binaire=True, programmes=[keystone], signatures={keystone: signe_par("Google LLC", "EQHXZ8M8AV")},
               app=(chrome, "com.google.Chrome", "Google Chrome", 90), charge=True, pid=3501,
               processus=[Processus(3501, keystone, [(8.0, 0.02), (60.0, 0.0)], rss_mo=20, fin=600.0)]),
        # Utile et léger, à garder.
        Plante("com.notesrapides.agent", "agent_utilisateur", Attendu("utile", "desactiver"),
               f"{LA}/com.notesrapides.agent.plist",
               {"Label": "com.notesrapides.agent", "ProgramArguments": [f"{notes}/Contents/MacOS/raccourcis"], "RunAtLoad": True},
               programmes=[f"{notes}/Contents/MacOS/raccourcis"],
               signatures={f"{notes}/Contents/MacOS/raccourcis": signe_par("Notes Rapides SAS", "NOTES00001")},
               app=(notes, "fr.notesrapides", "Notes Rapides", 1), charge=True, pid=3601,
               processus=[Processus(3601, f"{notes}/Contents/MacOS/raccourcis", [(3.0, 0.004)], rss_mo=35, puissance=0.1)]),
        # Inconnu, non signé : à vérifier, jamais à supprimer.
        Plante("com.mystere.agent", "agent_utilisateur", Attendu("inconnu", "verifier"),
               f"{LA}/com.mystere.agent.plist",
               {"Label": "com.mystere.agent", "ProgramArguments": [f"{MAISON}/Library/Application Support/.mystere/agent"],
                "RunAtLoad": True, "KeepAlive": True},
               programmes=[f"{MAISON}/Library/Application Support/.mystere/agent"], charge=True, pid=3701,
               processus=[Processus(3701, f"{MAISON}/Library/Application Support/.mystere/agent", [(2.0, 0.001)], rss_mo=8)]),
        # Se fait passer pour Apple sans signature Apple : à vérifier.
        Plante("com.apple.mise-a-jour", "agent_utilisateur", Attendu("inconnu", "verifier"),
               f"{LA}/com.apple.mise-a-jour.plist",
               {"Label": "com.apple.mise-a-jour", "Program": f"{MAISON}/.local/maj", "RunAtLoad": True},
               programmes=[f"{MAISON}/.local/maj"], charge=True, pid=3702,
               processus=[Processus(3702, f"{MAISON}/.local/maj", [(2.0, 0.001)], rss_mo=6)]),
        # Plist corrompu : pas de plantage, à vérifier.
        Plante("com.exemple.casse", "agent_utilisateur", Attendu("inconnu", "verifier"),
               f"{LA}/com.exemple.casse.plist", b'<?xml version="1.0"?><plist version="1.0"><dict><key>Label</key>'),
        # Espaces et accents, désactivé par l'utilisateur (déjà inactif).
        Plante("com.exemple.Étiquette avec espaces", "agent_utilisateur", Attendu("utile", "aucune"),
               f"{LA}/com.exemple.accents.plist",
               {"Label": "com.exemple.Étiquette avec espaces", "ProgramArguments": [f"{cafe}/Contents/MacOS/Éditeur Café"],
                "RunAtLoad": True},
               signatures={f"{cafe}/Contents/MacOS/Éditeur Café": signe_par("Café Logiciels", "CAFE000001")},
               app=(cafe, "fr.cafe.editeur", "Éditeur Café", 3), desactive=True),
        # Doublon : le même label à deux endroits.
        Plante("com.exemple.doublon", "agent_utilisateur", Attendu("utile", "desactiver", notes="doublon"),
               f"{LA}/com.exemple.doublon.plist", {"Label": "com.exemple.doublon", "Program": f"{notes}/Contents/MacOS/raccourcis"},
               signatures={f"{notes}/Contents/MacOS/raccourcis": signe_par("Notes Rapides SAS", "NOTES00001")}),
        Plante("com.exemple.doublon", "agent_global", Attendu("utile", "instructions", notes="doublon"),
               "/Library/LaunchAgents/com.exemple.doublon.plist",
               {"Label": "com.exemple.doublon", "Program": f"{notes}/Contents/MacOS/raccourcis"}),
        # C'est moi.
        Plante("com.assistant.superviseur", "agent_utilisateur", Attendu("utile", "aucune", notes="c'est moi"),
               f"{LA}/com.assistant.superviseur.plist",
               {"Label": "com.assistant.superviseur",
                "ProgramArguments": [f"{MAISON}/Assistant/.venv/bin/python", f"{MAISON}/Assistant/superviseur.py"],
                "RunAtLoad": True, "KeepAlive": True},
               programmes=[f"{MAISON}/Assistant/.venv/bin/python"], charge=True, pid=3801,
               processus=[Processus(3801, f"{MAISON}/Assistant/.venv/bin/python", [(1.0, 0.002)], rss_mo=25)]),
        # Daemon global léger, signé : utile, instructions seulement.
        Plante("com.exemple.vpn.daemon", "daemon_global", Attendu("utile", "instructions"),
               "/Library/LaunchDaemons/com.exemple.vpn.daemon.plist",
               {"Label": "com.exemple.vpn.daemon", "Program": "/Library/PrivilegedHelperTools/com.exemple.vpn.daemon",
                "RunAtLoad": True, "KeepAlive": True},
               programmes=["/Library/PrivilegedHelperTools/com.exemple.vpn.daemon"],
               signatures={"/Library/PrivilegedHelperTools/com.exemple.vpn.daemon": signe_par("Exemple VPN SAS", "AB12CD34EF")}),
        # Embarqué dans une app mais jamais activé : rien à faire.
        Plante("us.zoom.ZoomDaemon", "daemon_app", Attendu("utile", "aucune", notes="inactif"),
               "/Applications/zoom.us.app/Contents/Library/LaunchDaemons/us.zoom.ZoomDaemon.plist",
               {"Label": "us.zoom.ZoomDaemon", "BundleProgram": "Contents/Library/LaunchServices/ZoomDaemon"},
               programmes=["/Applications/zoom.us.app/Contents/Library/LaunchServices/ZoomDaemon"],
               signatures={"/Applications/zoom.us.app/Contents/Library/LaunchServices/ZoomDaemon":
                           signe_par("Zoom Video Communications, Inc.", "BJ4HAAB9B3")},
               app=("/Applications/zoom.us.app", "us.zoom.xos", "zoom.us", 12)),
    ]  # fmt: skip
    return assembler(mac, plantes, autres, apps=[], systeme_lisible=systeme_lisible)
