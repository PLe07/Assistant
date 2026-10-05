"""Le simulateur de vie : N jours d'activité réaliste d'un étudiant, beaucoup de bruit, et des corvées plantées
qui servent de vérité terrain. Il produit exactement ce que les capteurs produiraient (mêmes tokens, mêmes
attributs), à partir de noms bruts (dates, numéros, secrets compris) passés par la vraie normalisation.

Le moteur de détection ne connaît rien de ce fichier : il doit retrouver les corvées seul.
"""

from __future__ import annotations

import hashlib
import random
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from modules.corvees import normalize as n
from modules.corvees.db import Evenement

PARIS = ZoneInfo("Europe/Paris")
MAISON = "/Users/etudiant"
DEBUT = date(2026, 9, 7)  # un lundi

# --- Le bruit ---------------------------------------------------------------------------------------------

APPS = {  # appli : poids (au premier plan)
    "Safari": 18,
    "Google Chrome": 9,
    "Mail": 7,
    "Finder": 8,
    "Notes": 5,
    "Microsoft Word": 5,
    "Microsoft Excel": 4,
    "Aperçu": 4,
    "Code": 5,
    "Terminal": 4,
    "Spotify": 3,
    "Discord": 3,
    "Slack": 2,
    "zoom.us": 2,
    "Calendrier": 2,
    "Rappels": 2,
    "Pages": 2,
    "Numbers": 2,
    "Keynote": 1,
    "Photos": 2,
    "Microsoft Teams": 2,
    "Notion": 2,
    "Musique": 1,
    "Réglages Système": 1,
    "Anki": 2,
    "Zotero": 1,
}
NAVIGATEURS = ("Safari", "Google Chrome")
SITES = [  # (adresse de base, chemins possibles)
    ("https://www.youtube.com", ["/watch?v={x}", "/results?search_query={m}", "/shorts/{x}"]),
    ("https://fr.wikipedia.org", ["/wiki/{M}"]),
    ("https://www.google.com", ["/search?q={m}"]),
    ("https://www.lemonde.fr", ["/{m}/article/{d}/{m}_{n}.html", "/"]),
    ("https://www.reddit.com", ["/r/{m}/comments/{x}"]),
    ("https://stackoverflow.com", ["/questions/{n}/{m}"]),
    ("https://github.com", ["/{m}/{m}", "/{m}"]),
    ("https://chatgpt.com", ["/c/{x}"]),
    ("https://claude.ai", ["/chat/{x}"]),
    ("https://www.leboncoin.fr", ["/ad/{m}/{n}"]),
    ("https://www.amazon.fr", ["/dp/{X}"]),
    ("https://www.netflix.com", ["/watch/{n}"]),
    ("https://www.twitch.tv", ["/{m}"]),
    ("https://www.instagram.com", ["/{m}/"]),
    ("https://x.com", ["/{m}/status/{n}"]),
    ("https://www.linkedin.com", ["/feed/", "/jobs/view/{n}"]),
    ("https://www.welcometothejungle.com", ["/fr/companies/{m}/jobs/{m}"]),
    ("https://fr.indeed.com", ["/viewjob?jk={x}"]),
    ("https://www.compta-online.com", ["/{m}-{m}-ao{n}"]),
    ("https://www.legifrance.gouv.fr", ["/codes/article_lc/LEGIARTI{n}"]),
    ("https://www.service-public.fr", ["/particuliers/vosdroits/F{n}"]),
    ("https://www.deepl.com", ["/translator"]),
    ("https://www.wordreference.com", ["/fren/{m}"]),
    ("https://open.spotify.com", ["/playlist/{x}"]),
    ("https://www.allocine.fr", ["/film/fichefilm_gen_cfilm={n}.html"]),
    ("https://www.marmiton.org", ["/recettes/recette_{m}_{n}.aspx"]),
    ("https://www.sncf-connect.com", ["/app/home/search"]),
    ("https://www.doctissimo.fr", ["/{m}"]),
    ("https://mail.google.com", ["/mail/u/0/#inbox"]),
    ("https://www.notion.so", ["/{M}-{x}"]),
    ("https://drive.google.com", ["/drive/my-drive"]),
    ("https://www.dcg-online.fr", ["/cours/{m}"]),
    ("https://www.economie.gouv.fr", ["/{m}"]),
    ("https://www.20minutes.fr", ["/{m}/{n}-{m}"]),
    ("https://www.francetvinfo.fr", ["/{m}/{m}.html"]),
] + [
    (f"https://www.{m}.fr", ["/", "/{m}"])
    for m in (
        "fnac",
        "decathlon",
        "ikea",
        "boulanger",
        "darty",
        "cdiscount",
        "vinted",
        "blablacar",
        "ouest-france",
        "lequipe",
        "jeuxvideo",
        "numerama",
        "frandroid",
        "lesechos",
        "capital",
        "challenges",
        "studyrama",
        "letudiant",
        "crous",
        "lafinancepourtous",
        "boursier",
        "mataf",
        "investir",
        "pap",
        "seloger",
        "airbnb",
        "booking",
        "tripadvisor",
    )
]
MOTS = """budget compta bilan exercice cours chapitre td partiel examen fiche resume note projet rapport memoire
stage alternance cv lettre candidature photo image scan document facture devis contrat bail quittance recette
voyage billet planning agenda reunion presentation diapo slide tableau graphique export import sauvegarde archive
livre article lecture revision correction sujet annale calcul fiscalite tva amortissement provision consolidation
audit controle gestion finance marche action obligation taux credit epargne placement immobilier
location achat""".split()
DOSSIERS = [
    "Documents/Cours",
    "Documents/Perso",
    "Documents/Stage",
    "Documents/Admin",
    "Desktop",
    "Documents",
    "Documents/Projets",
    "Pictures",
    "Documents/Lectures",
    "Documents/Archives",
]
EXTS = ["pdf", "docx", "xlsx", "png", "jpg", "zip", "pptx", "txt", "csv", "mp4"]
COMMANDES = [
    "ls",
    "ls -la",
    "cd ~/Projets",
    "cd ..",
    "git status",
    "git log --oneline",
    "git diff",
    "python3 test.py",
    "python3 -m http.server",
    "brew update",
    "brew upgrade",
    "open .",
    "clear",
    "pwd",
    "code .",
    "top",
    "pip install requests",
    "npm install",
    "npm start",
    "node index.js",
    "cat notes.txt",
    "mkdir essai",
    "cd ~/Documents",
    "history",
    "git branch",
    "git fetch",
    "python3 calcul.py",
    "du -sh *",
    "df -h",
    "whoami",
    "ping -c 3 google.com",
    "ssh serveur",
    "vim todo.md",
    "make",
    "jupyter notebook",
    "conda activate base",
]
TITRES = [
    "Sans titre",
    "Brouillon",
    "Fiche de révision {n}",
    "Chapitre {n} — {M}",
    "Budget {d}",
    "Cours {M}",
    "Réunion {M}",
    "Notes du {d}",
]


def ident(chemin: str) -> str:
    """Ce que le capteur noterait d'un fichier : une empreinte de son chemin, jamais le chemin."""
    return hashlib.sha256(("sel" + chemin).encode()).hexdigest()[:16]


@dataclass
class Corvee:
    nom: str
    motifs: list[str]  # expressions trouvées dans les tokens d'un candidat qui la retrouve
    k: int  # combien de motifs différents doivent apparaître
    planter: Callable[[Journee], None]
    refusee: bool = False  # piège : refusée par l'utilisateur après la première analyse

    def retrouvee_par(self, candidat: dict) -> bool:
        tokens = " ".join(candidat["tokens"])
        return sum(1 for m in self.motifs if re.search(m, tokens)) >= self.k


@dataclass
class Monde:
    evenements: list[Evenement]
    corvees: list[Corvee]
    secrets: list[str]  # les faux secrets plantés, tels quels
    exclus: list[str]  # ce qui ne doit apparaître nulle part (applis et sites exclus)
    debut: float
    fin: float


# --- Une journée ------------------------------------------------------------------------------------------


@dataclass
class Journee:
    jour: date
    hasard: random.Random
    densite: float
    evts: list[Evenement] = field(default_factory=list)
    sessions: list[tuple[float, float]] = field(default_factory=list)
    bruit: list[Evenement] = field(default_factory=list)
    occupe: list[tuple[float, float]] = field(default_factory=list)

    def corvee(self, debut: float) -> None:
        """Une corvée commence : on la fait sans rien faire d'autre (sauf le parasite qu'elle prévoit)."""
        self.occupe.append((debut - 1, debut))

    def fin_corvee(self) -> None:
        if self.occupe:
            debut, _ = self.occupe[-1]
            fin = max([e.ts for e in self.evts if e.ts >= debut] + [debut])
            self.occupe[-1] = (debut, fin + 1)

    def assembler(self) -> list[Evenement]:
        libres = [e for e in self.bruit if not any(a <= e.ts <= b for a, b in self.occupe)]
        return libres + self.evts

    @property
    def semaine(self) -> bool:
        return self.jour.weekday() < 5

    def instant(self, heure: float, minutes_jitter: float = 0.0) -> float:
        h = heure + self.hasard.uniform(-minutes_jitter, minutes_jitter) / 60
        d = datetime(self.jour.year, self.jour.month, self.jour.day, tzinfo=PARIS) + timedelta(hours=h)
        return d.timestamp()

    def dans_une_session(self) -> float:
        """Un instant au hasard pendant une session de travail."""
        debut, fin = self.hasard.choice(self.sessions)
        return self.hasard.uniform(debut + 120, max(debut + 180, fin - 600))

    def ajouter(self, ts: float, capteur: str, kind: str, token: str, /, **attrs) -> None:
        self.evts.append(Evenement(ts, capteur, kind, token, attrs))

    # Les actions de base, construites comme les capteurs les construisent
    def app(self, ts: float, nom: str) -> None:
        self.ajouter(ts, "apps", "app", n.tok_app(nom), appli=nom)

    def url(self, ts: float, adresse: str) -> None:
        self.ajouter(ts, "navigateur", "url", n.tok_url(adresse), domaine=n.url_normalisee(adresse).split("/")[0])

    def creation(self, ts: float, dossier: str, nom: str) -> str:
        chemin = f"{MAISON}/{dossier}/{nom}"
        self.ajouter(
            ts, "fichiers", "fcreate", n.tok_creation(f"{MAISON}/{dossier}", nom, MAISON), fichier=ident(chemin)
        )
        return chemin

    def renommage(self, ts: float, dossier: str, avant: str, apres: str) -> str:
        de, vers = f"{MAISON}/{dossier}/{avant}", f"{MAISON}/{dossier}/{apres}"
        token = n.tok_renommage(f"{MAISON}/{dossier}", avant, apres, MAISON)
        self.ajouter(ts, "fichiers", "fren", token, avant=ident(de), fichier=ident(vers))
        return vers

    def deplacement(self, ts: float, de: str, vers: str, nom: str) -> str:
        source, cible = f"{MAISON}/{de}/{nom}", f"{MAISON}/{vers}/{nom}"
        token = n.tok_deplacement(f"{MAISON}/{de}", f"{MAISON}/{vers}", nom, MAISON)
        self.ajouter(ts, "fichiers", "fmove", token, avant=ident(source), fichier=ident(cible))
        return cible

    def conversion(self, ts: float, dossier: str, source: str, cible: str) -> None:
        token = n.tok_conversion(f"{MAISON}/{dossier}", source, cible, MAISON)
        self.ajouter(
            ts,
            "fichiers",
            "fconv",
            token,
            source=ident(f"{MAISON}/{dossier}/{source}"),
            fichier=ident(f"{MAISON}/{dossier}/{cible}"),
        )

    def commande(self, ts: float, ligne: str) -> None:
        self.ajouter(ts, "shell", "cmd", n.tok_commande(ligne.replace("~", MAISON), MAISON))

    def pont(self, ts: float, source: str, destination: str) -> None:
        self.ajouter(
            ts,
            "pressepapiers",
            "clip",
            n.tok_pont(source, destination),
            source=source,
            destination=destination,
            type="texte",
        )

    def fenetre(self, ts: float, appli: str, titre: str) -> None:
        self.ajouter(ts, "fenetres", "fen", n.tok_fenetre(appli, titre), appli=appli)


def _remplir(gabarit: str, h: random.Random, jour: date) -> str:
    return (
        gabarit.replace("{x}", "".join(h.choices("abcdefghijkmnopqrstuvwxyz0123456789", k=11)))
        .replace("{X}", "B0" + "".join(h.choices("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789", k=8)))
        .replace("{n}", str(h.randint(100, 99999)))
        .replace("{d}", jour.isoformat())
        .replace("{M}", h.choice(MOTS).capitalize())
        .replace("{m}", h.choice(MOTS))
    )


def _bruit(j: Journee, debut: float, fin: float, poids_sites: list[float]) -> None:
    """Une session de vie ordinaire : on passe d'une appli à l'autre, on navigue, on range, on tape des commandes."""
    plantes = j.evts
    j.evts = j.bruit
    try:
        _bruit_session(j, debut, fin, poids_sites)
    finally:
        j.evts = plantes


def _bruit_session(j: Journee, debut: float, fin: float, poids_sites: list[float]) -> None:
    h = j.hasard
    noms, poids = list(APPS), list(APPS.values())
    t, courante = debut, h.choices(noms, poids)[0]
    j.app(t, courante)
    pas_moyen = 40.0 / j.densite
    while True:
        t += h.expovariate(1 / pas_moyen) + 1
        if t >= fin:
            break
        r = h.random()
        if r < 0.38:  # changer d'appli
            suivante = h.choices(noms, poids)[0]
            if suivante != courante:
                courante = suivante
                j.app(t, courante)
        elif r < 0.68:  # naviguer
            if courante in NAVIGATEURS:
                base, chemins = h.choices(SITES, poids_sites)[0]
                j.url(t, base + _remplir(h.choice(chemins), h, j.jour))
        elif r < 0.74:  # une commande
            if courante == "Terminal":
                ligne = h.choice(COMMANDES)
                if h.random() < 0.08:
                    ligne = f"{ligne} && {h.choice(COMMANDES)}"
                j.commande(t, ligne)
        elif r < 0.748:  # un fichier téléchargé ou rangé
            nom = f"{h.choice(MOTS)}_{h.choice(MOTS)}_{h.randint(1, 999)}.{h.choice(EXTS)}"
            if h.random() < 0.5:
                j.creation(t, "Downloads", nom)
            else:
                j.deplacement(t, h.choice(["Downloads", "Desktop"]), h.choice(DOSSIERS), nom)
        elif r < 0.765:  # copier ici, aller coller ailleurs
            autre = h.choices(noms, poids)[0]
            if autre != courante:
                j.pont(t, courante, autre)
                courante = autre
                j.app(t + 2, courante)
        elif r < 0.81:  # le titre de la fenêtre change
            j.fenetre(t, courante, _remplir(h.choice(TITRES), h, j.jour))
        elif r < 0.812:  # un fichier renommé
            nom = f"{h.choice(MOTS)}{h.randint(1, 99)}.{h.choice(['docx', 'xlsx', 'png'])}"
            j.renommage(t, h.choice(DOSSIERS), nom, f"{h.choice(MOTS)}_{h.choice(MOTS)}.{nom.rsplit('.', 1)[1]}")
    j.ajouter(fin, "inactivite", "inactif", "inactif")


def _sessions(j: Journee) -> None:
    h = j.hasard
    if j.semaine:
        plages = [(8.2, 12.3), (13.4, 18.2), (20.3, 23.0)]
    else:
        plages = [(10.5, 12.5), (15.0, 18.0), (21.0, 23.5)]
    for i, (debut, fin) in enumerate(plages):
        if not j.semaine and i != 1 and h.random() < 0.3:  # le week-end, l'après-midi reste toujours
            continue
        a = j.instant(debut, 20)
        b = j.instant(fin, 20)
        # une pause au milieu, plus longue que 10 minutes : deux sessions
        milieu = h.uniform(a + 0.35 * (b - a), a + 0.65 * (b - a))
        j.sessions += [(a, milieu), (milieu + h.uniform(900, 2400), b)]


# --- Les corvées plantées (jeu A) -------------------------------------------------------------------------


def _parasite(j: Journee, t: float) -> float:
    """Parfois, une action sans rapport s'intercale au milieu d'une corvée."""
    if j.hasard.random() < 0.25:
        t += j.hasard.uniform(5, 30)
        j.url(t, "https://www.youtube.com/watch?v=" + "".join(j.hasard.choices("abcdefgh123", k=11)))
    return t


def _jours(*numeros: int) -> Callable[[Journee], bool]:
    return lambda j: j.jour.weekday() in numeros


def _factures(j: Journee) -> None:
    if not _jours(0, 2, 4)(j):
        return
    t = j.dans_une_session()
    d = j.jour - timedelta(days=j.hasard.randint(0, 5))
    nom = f"Facture_{d.isoformat()}.pdf"
    j.creation(t, "Downloads", nom)
    j.deplacement(t + j.hasard.uniform(30, 240), "Downloads", "Documents/Factures", nom)


def _matin(j: Journee) -> None:
    if not j.semaine:
        return
    t = j.instant(8.55, 10)
    j.app(t, "Safari")
    j.url(t + 3, "https://mail.google.com/mail/u/0/#inbox")
    t = _parasite(j, t + j.hasard.uniform(40, 120))
    j.url(t, "https://calendar.google.com/calendar/u/0/r")
    j.url(
        t + j.hasard.uniform(20, 60),
        f"https://www.notion.so/Semaine-{j.hasard.randint(1, 52)}-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
    )


def _pont_tableur(j: Journee) -> None:
    if j.jour.weekday() == 6:
        return
    t = j.dans_une_session()
    j.app(t, "Safari")
    j.pont(t + j.hasard.uniform(5, 20), "Safari", "Numbers")
    j.app(t + j.hasard.uniform(21, 30), "Numbers")


def _commande_du_soir(j: Journee) -> None:
    t = j.instant(21.2, 30)
    j.app(t, "Terminal")
    j.commande(t + 5, "cd ~/Projets/assistant && git pull && python main.py")


def _captures(j: Journee) -> None:
    if not _jours(0, 1, 3, 4)(j):
        return
    t = j.dans_une_session()
    heure = datetime.fromtimestamp(t, PARIS)
    brut = f"Capture d’écran {heure:%Y-%m-%d} à {heure:%H.%M.%S}.png"
    j.creation(t, "Desktop", brut)
    t = _parasite(j, t + j.hasard.uniform(20, 90))
    nouveau = f"screen_{j.hasard.randint(1, 500)}.png"
    j.renommage(t, "Desktop", brut, nouveau)
    j.deplacement(t + j.hasard.uniform(10, 40), "Desktop", "Documents/Captures", nouveau)


def _lundi(j: Journee) -> None:
    if j.jour.weekday() != 0:
        return
    t = j.instant(9.3, 15)
    j.app(t, "Safari")
    for site in (
        "https://ent.univ-exemple.fr/accueil",
        "https://moodle.univ-exemple.fr/my/",
        "https://edt.univ-exemple.fr/planning",
        "https://bu.univ-exemple.fr/prets",
    ):
        t += j.hasard.uniform(20, 90)
        j.url(t, site)


def _export_pages(j: Journee) -> None:
    if not _jours(1, 3, 5)(j):
        return
    t = j.dans_une_session()
    j.app(t, "Pages")
    nom = f"Devoir_{j.hasard.choice(['DCG', 'Droit', 'Eco'])}_{j.jour:%d%m}.pdf"
    j.creation(t + j.hasard.uniform(30, 90), "Documents", nom)
    j.deplacement(t + j.hasard.uniform(100, 200), "Documents", "Documents/Rendus", nom)


def _heic(j: Journee) -> None:
    if not _jours(0, 2, 5)(j):
        return
    t = j.dans_une_session()
    j.app(t, "Aperçu")
    for _ in range(j.hasard.randint(1, 3)):
        numero = j.hasard.randint(1000, 9999)
        t += j.hasard.uniform(15, 45)
        j.conversion(t, "Downloads", f"IMG_{numero}.HEIC", f"IMG_{numero}.jpg")


def _espace_de_travail(j: Journee) -> None:
    if not j.semaine:
        return
    t = j.instant(14.2, 15)
    for appli in ("Spotify", "Code", "Terminal"):
        j.app(t, appli)
        t += j.hasard.uniform(4, 15)


def _releve(j: Journee) -> None:
    if not _jours(1, 4)(j):
        return
    t = j.dans_une_session()
    mois = (j.jour.replace(day=1) - timedelta(days=1)).strftime("%Y_%m")
    brut = f"releve_{mois}_{j.hasard.randint(10000, 99999)}.pdf"
    j.creation(t, "Downloads", brut)
    j.app(t + 5, "Aperçu")
    t = _parasite(j, t + j.hasard.uniform(30, 120))
    propre = f"Releve_Compte_{mois}.pdf"
    j.renommage(t, "Downloads", brut, propre)
    j.deplacement(t + j.hasard.uniform(5, 30), "Downloads", "Documents/Releves", propre)


CORVEES_A = [
    ("factures rangées", [r"Documents/Factures"], 1, _factures),
    ("routine du matin Gmail → Agenda → Notion", [r"mail\.google", r"calendar\.google", r"notion\.so"], 2, _matin),
    ("copier Safari → coller Numbers", [r"clip:Safari→Numbers"], 1, _pont_tableur),
    ("git pull && python main.py", [r"git pull && python main\.py"], 1, _commande_du_soir),
    ("captures renommées puis rangées", [r"screen_\*"], 1, _captures),
    ("les 4 sites du lundi", [r"ent\.univ", r"moodle\.univ", r"edt\.univ", r"bu\.univ"], 2, _lundi),
    ("export Pages rangé", [r"Documents/Rendus"], 1, _export_pages),
    ("HEIC → JPG avec Aperçu", [r"heic→jpg"], 1, _heic),
    (
        "Spotify, Code, Terminal ouverts ensemble",
        [r"app:Spotify\b", r"app:Code\b", r"app:Terminal\b"],
        3,
        _espace_de_travail,
    ),
    ("relevé téléchargé, renommé, rangé", [r"Documents/Releves", r"Releve_Compte"], 1, _releve),
]

# --- Les corvées plantées (jeu B) : écrit APRÈS le réglage du moteur, pour prouver qu'il est générique ----------


def _exports_compta(j: Journee) -> None:
    if not _jours(1, 3, 5)(j):
        return
    t = j.dans_une_session()
    nom = f"Export_Compta_{j.jour:%Y%m%d}_{j.hasard.randint(1, 9)}.xlsx"
    j.creation(t, "Downloads", nom)
    j.deplacement(t + j.hasard.uniform(20, 300), "Downloads", "Documents/Compta", nom)


def _vendredi(j: Journee) -> None:
    if j.jour.weekday() != 4:
        return
    t = j.instant(17.0, 10)
    j.app(t, "Slack")
    t = _parasite(j, t + j.hasard.uniform(30, 90))
    j.app(t, "Google Chrome")
    j.url(t + 3, "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMn")
    j.app(t + j.hasard.uniform(60, 120), "Mail")


def _pont_presentation(j: Journee) -> None:
    if not j.semaine:
        return
    t = j.dans_une_session()
    j.app(t, "Microsoft Word")
    j.pont(t + j.hasard.uniform(5, 30), "Microsoft Word", "Keynote")
    j.app(t + 35, "Keynote")


def _deploiement(j: Journee) -> None:
    if not j.semaine:
        return
    t = j.dans_une_session()
    j.app(t, "Terminal")
    j.commande(t + 4, "npm run build && npm run deploy")


def _scans(j: Journee) -> None:
    if not _jours(0, 1, 3, 4)(j):
        return
    t = j.dans_une_session()
    numero = j.hasard.randint(1, 400)
    j.renommage(t, "Documents/Scans", f"Scan_{numero:04d}.pdf", f"Cours_{j.hasard.choice(MOTS)}_{numero}.pdf")


def _matin_bureau(j: Journee) -> None:
    if not j.semaine:
        return
    t = j.instant(9.25, 10)
    j.app(t, "Microsoft Teams")
    t = _parasite(j, t + j.hasard.uniform(20, 60))
    j.app(t, "Google Chrome")
    j.url(t + 2, "https://outlook.office.com/mail/inbox")
    j.url(t + j.hasard.uniform(30, 90), "https://monecole.sharepoint.com/sites/promo")


def _lettres(j: Journee) -> None:
    if not _jours(0, 2, 4)(j):
        return
    t = j.dans_une_session()
    j.app(t, "Microsoft Word")
    nom = f"Lettre_motivation_{j.hasard.choice(['BNP', 'SG', 'CIC', 'LCL', 'KPMG'])}"
    j.conversion(t + j.hasard.uniform(30, 120), "Documents/Lettres", f"{nom}.docx", f"{nom}.pdf")


def _git_suite(j: Journee) -> None:
    if not j.semaine:
        return
    t = j.dans_une_session()
    j.app(t, "Terminal")
    j.commande(t + 3, "git add .")
    j.commande(t + j.hasard.uniform(8, 20), f'git commit -m "maj {j.jour:%d/%m}"')
    j.commande(t + j.hasard.uniform(25, 40), "git push")


def _installeurs(j: Journee) -> None:
    if not _jours(0, 2, 3, 5)(j):
        return
    t = j.dans_une_session()
    appli = j.hasard.choice(["Zoom", "Slack", "Chrome", "VLC", "Anki"])
    nom = f"Installeur_{appli}_{j.hasard.randint(1, 9)}.{j.hasard.randint(0, 99)}.dmg"
    j.creation(t, "Downloads", nom)
    j.deplacement(t + j.hasard.uniform(60, 600), "Downloads", ".Trash", nom)


def _soir(j: Journee) -> None:
    t = j.instant(18.5, 12)
    for appli in ("Calendrier", "Rappels", "Notes"):
        j.app(t, appli)
        t += j.hasard.uniform(5, 25)


CORVEES_B = [
    ("exports compta rangés", [r"Documents/Compta"], 1, _exports_compta),
    ("vendredi : Slack → Drive → Mail", [r"app:Slack", r"drive\.google", r"app:Mail"], 2, _vendredi),
    ("copier Word → coller Keynote", [r"clip:Microsoft Word→Keynote"], 1, _pont_presentation),
    ("npm run build && npm run deploy", [r"npm run build && npm run deploy"], 1, _deploiement),
    ("scans renommés en Cours_*", [r"Scan_\*→Cours_"], 1, _scans),
    ("matin : Teams → Outlook → SharePoint", [r"outlook\.office", r"sharepoint", r"Microsoft Teams"], 2, _matin_bureau),
    ("lettres Word → PDF", [r"docx→pdf"], 1, _lettres),
    ("git add, commit, push", [r"cmd:git add \.", r"cmd:git push"], 2, _git_suite),
    ("installeurs .dmg à la corbeille", [r"\.Trash"], 1, _installeurs),
    ("18h30 : Calendrier, Rappels, Notes", [r"app:Calendrier\b", r"app:Rappels\b", r"app:Notes\b"], 3, _soir),
]

# --- Les pièges ---------------------------------------------------------------------------------------------

SECRETS = [
    "S3cretMdp!42",
    "sk-ant-api03-FAUXfauxFAUX1234567890abcdef",
    "FR7630006000011234567890189",
    "prenom.nom@exemple-faux.fr",
    "hunter2-le-faux",
    "06 98 76 54 32",
    "ghp_fauxJetonGithub0123456789abcdef",
]


def _piege_spotify(j: Journee) -> None:
    """Fréquent mais déjà instantané : ouvrir Spotify seul chaque matin."""
    j.app(j.instant(10.1, 10), "Spotify")


def _piege_refusee(j: Journee) -> None:
    """Une vraie corvée… que l'utilisateur refusera : elle ne doit jamais revenir."""
    if not j.semaine:
        return
    t = j.dans_une_session()
    j.app(t, "Mail")
    j.pont(t + j.hasard.uniform(5, 20), "Mail", "Microsoft Excel")
    j.app(t + 25, "Microsoft Excel")


def _piege_exclus(j: Journee) -> None:
    """Activité dans des applis et sites exclus : ne doit apparaître nulle part."""
    t = j.dans_une_session()
    j.app(t, "1Password 7")
    j.pont(t + 5, "1Password 7", "Safari")
    j.app(t + 8, "Safari")
    j.url(t + 15, "https://www.boursorama.com/espace-client/comptes")
    j.url(t + 40, "https://cfspart.impots.gouv.fr/monprofil-webapp/")
    j.app(t + 60, "Messages")
    j.fenetre(t + 61, "Messages", "Conversation avec Maman")


def _piege_secrets(j: Journee) -> None:
    """De faux secrets là où les gens les mettent vraiment (pas toujours les mêmes, pas dans le même ordre)."""
    h = j.hasard
    t = j.dans_une_session()
    actions = [
        lambda t: (j.app(t, "Terminal"), j.commande(t + 3, f"mysql -u root -p'{SECRETS[0]}' compta")),
        lambda t: j.commande(t, f"export ANTHROPIC_API_KEY={SECRETS[1]}"),
        lambda t: j.commande(t, f"git clone https://{SECRETS[6]}@github.com/moi/projet.git"),
        lambda t: j.commande(t, f"PASSWORD={SECRETS[4]} ./deploy.sh"),
        lambda t: j.creation(t, "Downloads", f"RIB_{SECRETS[2]}.pdf"),
        lambda t: j.fenetre(t, "Mail", f"Réponse à {SECRETS[3]}"),
        lambda t: j.fenetre(t, "Notes", f"Rappeler {SECRETS[5]}"),
        lambda t: j.url(t, f"https://www.service-public.fr/demarche?email={SECRETS[3]}&token=abc{h.randint(1, 9)}"),
    ]
    for action in h.sample(actions, h.randint(2, 4)):
        t += h.uniform(30, 600)
        action(t)


# --- Le monde -----------------------------------------------------------------------------------------------


def generer(graine: int, jours: int = 28, densite: float = 1.0, corvees=None, pieges: bool = True) -> Monde:
    hasard = random.Random(graine)
    poids_sites = [1 / (i + 1) ** 0.8 for i in range(len(SITES))]
    hasard.shuffle(poids_sites)
    plantees = [Corvee(nom, motifs, k, f) for nom, motifs, k, f in (corvees or CORVEES_A)]
    if pieges:
        plantees.append(
            Corvee("copier Mail → Excel (refusée)", [r"clip:Mail→Microsoft Excel"], 1, _piege_refusee, True)
        )
    evenements: list[Evenement] = []
    for i in range(jours):
        j = Journee(DEBUT + timedelta(days=i), random.Random(hasard.random()), densite)
        _sessions(j)
        for a, b in j.sessions:
            _bruit(j, a, b, poids_sites)
        actions = [c.planter for c in plantees]
        if pieges:
            actions.append(_piege_spotify)
            if j.hasard.random() < 0.5:
                actions.append(_piege_exclus)
            if j.hasard.random() < 0.3:
                actions.append(_piege_secrets)
        for action in actions:
            avant = len(j.evts)
            action(j)
            if len(j.evts) > avant:
                debut = min(e.ts for e in j.evts[avant:])
                fin = max(e.ts for e in j.evts[avant:])
                j.occupe.append((debut - 1, fin + 1))
        evenements += j.assembler()
    evenements.sort(key=lambda e: e.ts)
    debut = datetime(DEBUT.year, DEBUT.month, DEBUT.day, tzinfo=PARIS).timestamp()
    fin = debut + jours * 86400
    exclus = ["1Password", "boursorama", "impots.gouv", "Messages", "Maman"]
    return Monde(evenements, plantees, SECRETS, exclus, debut, fin)
