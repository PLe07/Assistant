"""Les réglages et les chemins du tableau de bord.

- Données : `~/Library/Application Support/TableauDeBord/` (base SQLite en 600, réglages, registre, jeton).
- Journal : `~/Library/Logs/TableauDeBord/` (toujours caviardé).
- iPhone : `iCloud Drive/Tableau/Etat.html` (états et compteurs seulement).

`reglages.toml` est à toi : une valeur fausse est remplacée par sa valeur par défaut, avec un message qui dit
laquelle et pourquoi (`tableau doctor`). Tous les chemins partent de `TABLEAU_MAISON` (ton dossier personnel par
défaut) : les tests et le faux écosystème travaillent ainsi dans un bac à sable.
"""

from __future__ import annotations

import copy
import getpass
import os
import re
import secrets
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

NOM_SUPPORT = "TableauDeBord"
NOM_ICLOUD = "Tableau"
PORT_N8N = 5678
PORT_DEFAUT = 47615
PORTS_DE_REPLI = range(47616, 47640)

DEFAUTS: dict[str, Any] = {
    "installation": {"prefixe_label": ""},
    "serveur": {"port": PORT_DEFAUT},
    "intervalles": {
        "sante_s": 60,
        "decouverte_s": 600,
        "integrite_s": 1800,
        "tailles_s": 1800,
        "instantane_s": 900,
        "copie_base_s": 600,
    },
    "alertes": {
        "max_par_jour": 3,
        "silence_debut": 23,
        "silence_fin": 8,
        "rappel_heures": 24,
        "confirmation_s": 90,
        "resolution_s": 150,
        "reveil_grace_s": 600,
        "regroupement_s": 120,
    },
    "seuils": {
        "file_bloquee_min": 30,
        "pic_erreurs_facteur": 3.0,
        "pic_erreurs_min_par_heure": 10,
        "budget_attention_pct": 80,
        "budget_depasse_pct": 100,
        "donnees_max_mo": 500,
        "donnees_croissance_pct_semaine": 50,
        "boucle_relances": 3,
        "boucle_fenetre_min": 10,
        "cpu_eleve_pct": 60,
        "cpu_eleve_min": 10,
        "battement_facteur": 3,
        "copie_max_mo": 256,
    },
    "rapport": {"jour": 6, "heure": "20:00"},
    "energie": {"watts_par_coeur": 2.5, "watts_mac_moyen": 4.5, "heures_eveil_par_jour": 8},
    "credits": {"api_admin": False},
    "instantane": {"actif": True},
    "barre_menus": {"active": True},
}


def maison() -> Path:
    return Path(os.environ.get("TABLEAU_MAISON") or Path.home()).expanduser()


@dataclass(frozen=True)
class Chemins:
    maison: Path

    @property
    def support(self) -> Path:
        return self.maison / "Library" / "Application Support" / NOM_SUPPORT

    @property
    def logs(self) -> Path:
        return self.maison / "Library" / "Logs" / NOM_SUPPORT

    @property
    def base(self) -> Path:
        return self.support / "tableau.db"

    @property
    def reglages(self) -> Path:
        return self.support / "reglages.toml"

    @property
    def registre(self) -> Path:
        return self.support / "modules.toml"

    @property
    def jeton(self) -> Path:
        return self.support / "jeton"

    @property
    def etat_json(self) -> Path:
        return self.support / "etat.json"

    @property
    def copies(self) -> Path:
        """Le dossier temporaire où les bases des autres modules sont copiées avant d'être lues (§1.2)."""
        return self.support / "copies"

    @property
    def verrou(self) -> Path:
        return self.support / "demon.verrou"

    @property
    def rapports(self) -> Path:
        return self.support / "rapports"

    @property
    def icloud_drive(self) -> Path:
        surcharge = os.environ.get("TABLEAU_ICLOUD")
        if surcharge:
            return Path(surcharge)
        return self.maison / "Library" / "Mobile Documents" / "com~apple~CloudDocs"

    @property
    def icloud(self) -> Path:
        return self.icloud_drive / NOM_ICLOUD

    @property
    def launch_agents(self) -> Path:
        return self.maison / "Library" / "LaunchAgents"

    def preparer(self) -> None:
        """Nos dossiers, lisibles par toi seul."""
        for d in (self.support, self.logs, self.copies, self.rapports):
            d.mkdir(parents=True, exist_ok=True)
            os.chmod(d, 0o700)


def chemins() -> Chemins:
    return Chemins(maison())


@dataclass
class Reglages:
    valeurs: dict[str, Any]
    erreurs: list[str] = field(default_factory=list)

    def __getitem__(self, section: str) -> dict[str, Any]:
        return self.valeurs[section]

    def prefixe(self) -> str:
        brut = str(self.valeurs["installation"].get("prefixe_label") or "") or getpass.getuser()
        return re.sub(r"[^a-z0-9_-]", "", brut.lower()) or "moi"

    def label(self) -> str:
        return f"com.{self.prefixe()}.tableau"


def _fusionner(defauts: dict[str, Any], perso: dict[str, Any], erreurs: list[str], chemin: str = "") -> dict[str, Any]:
    resultat = copy.deepcopy(defauts)
    for cle, valeur in perso.items():
        nom = f"{chemin}{cle}"
        if cle not in defauts:
            erreurs.append(f"« {nom} » n'existe pas : ignoré")
            continue
        attendu = defauts[cle]
        if isinstance(attendu, dict):
            if isinstance(valeur, dict):
                resultat[cle] = _fusionner(attendu, valeur, erreurs, f"{nom}.")
            else:
                erreurs.append(f"« {nom} » doit être une section : valeur par défaut gardée")
        elif isinstance(attendu, bool):
            if isinstance(valeur, bool):
                resultat[cle] = valeur
            else:
                erreurs.append(f"« {nom} » doit valoir true ou false : {attendu!r} gardé")
        elif isinstance(attendu, (int, float)):
            if isinstance(valeur, (int, float)) and not isinstance(valeur, bool) and valeur >= 0:
                resultat[cle] = type(attendu)(valeur) if isinstance(attendu, float) else valeur
            else:
                erreurs.append(f"« {nom} » doit être un nombre positif : {attendu!r} gardé")
        elif isinstance(attendu, str):
            if isinstance(valeur, str):
                resultat[cle] = valeur
            else:
                erreurs.append(f"« {nom} » doit être un texte : {attendu!r} gardé")
    return resultat


def _valider(v: dict[str, Any], erreurs: list[str]) -> None:
    port = v["serveur"]["port"]
    if not isinstance(port, int) or not 1024 <= port <= 65535 or port == PORT_N8N:
        erreurs.append(f"« serveur.port » = {port!r} impossible (1024 à 65535, jamais {PORT_N8N} : n8n) : "
                       f"{PORT_DEFAUT} gardé")  # fmt: skip
        v["serveur"]["port"] = PORT_DEFAUT
    for cle in ("silence_debut", "silence_fin"):
        if not 0 <= int(v["alertes"][cle]) <= 23:
            erreurs.append(f"« alertes.{cle} » doit être une heure de 0 à 23 : valeur par défaut gardée")
            v["alertes"][cle] = DEFAUTS["alertes"][cle]
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(v["rapport"]["heure"])):
        erreurs.append("« rapport.heure » doit s'écrire HH:MM : 20:00 gardé")
        v["rapport"]["heure"] = "20:00"
    if not 0 <= int(v["rapport"]["jour"]) <= 6:
        erreurs.append("« rapport.jour » va de 0 (lundi) à 6 (dimanche) : dimanche gardé")
        v["rapport"]["jour"] = 6
    if int(v["intervalles"]["sante_s"]) < 5:
        erreurs.append("« intervalles.sante_s » trop court (5 s au moins) : 60 gardé")
        v["intervalles"]["sante_s"] = 60


def charger(chemin: Path | None = None) -> Reglages:
    """Lit reglages.toml (absent : valeurs par défaut). Ne lève jamais : les erreurs sont dans `.erreurs`."""
    fichier = chemin or chemins().reglages
    erreurs: list[str] = []
    perso: dict[str, Any] = {}
    if fichier.exists():
        try:
            perso = tomllib.loads(fichier.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
            erreurs.append(f"reglages.toml illisible ({e.__class__.__name__}) : valeurs par défaut")
    valeurs = _fusionner(DEFAUTS, perso, erreurs)
    _valider(valeurs, erreurs)
    return Reglages(valeurs, erreurs)


def enregistrer_port(port: int, chemin: Path | None = None) -> None:
    """Retient le port choisi dans reglages.toml (le fichier reste à toi : seule la ligne du port change)."""
    fichier = chemin or chemins().reglages
    texte = fichier.read_text(encoding="utf-8") if fichier.exists() else ""
    ligne = f"port = {port}"
    if re.search(r"(?m)^\[serveur\]\s*$", texte):
        if re.search(r"(?ms)^\[serveur\]\s*$(?:(?!^\[).)*?^port\s*=", texte):
            texte = re.sub(r"(?ms)(^\[serveur\]\s*$(?:(?!^\[).)*?)^port\s*=.*?$", rf"\g<1>{ligne}", texte, count=1)
        else:
            texte = re.sub(r"(?m)^\[serveur\]\s*$", f"[serveur]\n{ligne}", texte, count=1)
    else:
        texte = texte.rstrip("\n") + ("\n\n" if texte.strip() else "") + f"[serveur]\n{ligne}\n"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    temporaire = fichier.with_suffix(".tmp")
    temporaire.write_text(texte, encoding="utf-8")
    os.chmod(temporaire, 0o600)
    temporaire.replace(fichier)


def jeton(c: Chemins | None = None) -> str:
    """Le jeton secret de la page locale (créé au premier besoin, lisible par toi seul)."""
    c = c or chemins()
    try:
        valeur = c.jeton.read_text(encoding="utf-8").strip()
        if len(valeur) >= 32:
            return valeur
    except OSError:
        pass
    valeur = secrets.token_urlsafe(32)
    c.jeton.parent.mkdir(parents=True, exist_ok=True)
    descripteur = os.open(c.jeton, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descripteur, "w", encoding="utf-8") as f:
        f.write(valeur + "\n")
    os.chmod(c.jeton, 0o600)
    return valeur
