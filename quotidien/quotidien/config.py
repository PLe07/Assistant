"""Réglages et chemins de Quotidien.

Deux fichiers à toi, dans `~/Library/Application Support/Quotidien/` (créés par `install.sh` à partir des modèles) :
- `profil.toml` : tes goûts, ton budget, tes jours chargés, tes trajets (le « petit fichier » du README) ;
- `reglages.toml` : le reste (ville, heures du brief et des alertes, IA, listes de Rappels).

Un fichier absent, illisible ou mal rempli ne bloque jamais rien : la valeur fautive est remplacée par sa valeur par
défaut et un message clair dit laquelle et pourquoi (`quotidien doctor`, et une ligne dans le journal).
"""

from __future__ import annotations

import copy
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
ALLERGENES = (
    "gluten",
    "crustaces",
    "oeufs",
    "poissons",
    "arachides",
    "soja",
    "lait",
    "fruits_a_coque",
    "celeri",
    "moutarde",
    "sesame",
    "sulfites",
    "lupin",
    "mollusques",
)
NOMS_ALLERGENES = {
    "gluten": "gluten",
    "crustaces": "crustacés",
    "oeufs": "œufs",
    "poissons": "poissons",
    "arachides": "arachides",
    "soja": "soja",
    "lait": "lait",
    "fruits_a_coque": "fruits à coque",
    "celeri": "céleri",
    "moutarde": "moutarde",
    "sesame": "sésame",
    "sulfites": "sulfites",
    "lupin": "lupin",
    "mollusques": "mollusques",
}
REGIMES = ("omnivore", "sans_porc", "pescetarien", "vegetarien", "vegan")
EQUIPEMENTS = ("plaques", "four", "micro-ondes", "airfryer", "mixeur")
TONS = ("tendre", "drole", "sobre", "formel")
RELATIONS = ("famille", "couple", "ami_proche", "ami", "collegue", "professeur")

DEFAUT_PROFIL: dict[str, Any] = {
    "repas": {
        "regime": "omnivore",
        "allergies": [],
        "deteste": [],
        "aime": [],
        "cuisines_preferees": [],
        "portions": 1,
        "budget_semaine": 45.0,
        "equipement": ["plaques", "four", "micro-ondes"],
        "dejeuners": False,
        "jour_courses": "lundi",
        "placard": [
            "sel",
            "poivre",
            "huile_olive",
            "huile_neutre",
            "farine",
            "sucre",
            "pates",
            "riz",
            "vinaigre",
            "cumin",
            "curry",
            "paprika",
            "herbes_de_provence",
            "piment",
            "bouillon_cube",
            "moutarde",
            "sauce_soja",
            "ail",
        ],
    },
    "semaine": {
        "jours_charges": ["mercredi", "jeudi", "vendredi"],
        "jours_de_cours": ["mercredi", "jeudi", "vendredi"],
    },
    "trajets": {
        "depart": "08:00",
        "retour": "18:30",
        "duree_minutes": 30,
        "moyen": "velo",
    },
}

DEFAUT_REGLAGES: dict[str, Any] = {
    "lieu": {"ville": "Bordeaux", "latitude": 44.8378, "longitude": -0.5792, "fuseau": "Europe/Paris"},
    "horaires": {
        "brief": "07:15",
        "alerte_meteo_veille": "21:00",
        "menu_jour": "dimanche",
        "menu_heure": "17:00",
        "rappels_veille": "20:00",
        "anniversaire_veille": "19:30",
        "anniversaire_jour": "09:00",
        "anniversaire_cadeau": "10:00",
        "silence_debut": "23:00",
        "silence_fin": "07:00",
    },
    "meteo": {"cache_heures": 3},
    "ia": {
        "active": True,
        "modele": "claude-haiku-4-5",
        "budget_mensuel_usd": 2.0,
        "prix_entree_par_million": 1.0,
        "prix_sortie_par_million": 5.0,
        "delai_s": 40,
    },
    "rappels": {"active": True, "liste_courses": "Courses (menu)", "liste_anniversaires": "Anniversaires"},
    "anniversaires": {
        "contacts": True,
        "jours_avant_proches": 7,
        "date_29_fevrier": "28-02",
        "fetes": False,
        "dialogue": True,
    },
    "installation": {"prefixe_label": ""},
}


# --- Chemins ------------------------------------------------------------------------------------------------------


def maison() -> Path:
    """Ton dossier personnel (les tests en imitent un avec QUOTIDIEN_MAISON)."""
    return Path(os.environ.get("QUOTIDIEN_MAISON") or Path.home())


def dossier_support() -> Path:
    return maison() / "Library" / "Application Support" / "Quotidien"


def dossier_logs() -> Path:
    return maison() / "Library" / "Logs" / "Quotidien"


def icloud_drive() -> Path:
    return maison() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"


def dossier_icloud() -> Path:
    """`iCloud Drive/Quotidien/` : les pages, et l'entrée des raccourcis depuis l'app Fichiers."""
    return icloud_drive() / os.environ.get("QUOTIDIEN_DOSSIER_ICLOUD", "Quotidien")


def dossier_icloud_raccourcis() -> Path:
    """Un chemin relatif « Quotidien/… » dans un raccourci désigne le dossier iCloud de l'app Raccourcis (leçon du
    Trieur, D-12) : `iCloud Drive/Shortcuts/Quotidien/`. Le Mac surveille les deux."""
    return (
        maison()
        / "Library"
        / "Mobile Documents"
        / "iCloud~is~workflow~my~workflows"
        / "Documents"
        / os.environ.get("QUOTIDIEN_DOSSIER_ICLOUD", "Quotidien")
    )


def chemin_base() -> Path:
    return dossier_support() / "quotidien.db"


def racine_projet() -> Path:
    return Path(__file__).resolve().parent.parent


# --- Lecture et validation ------------------------------------------------------------------------------------------


@dataclass
class Reglages:
    profil: dict[str, Any]
    reglages: dict[str, Any]
    avertissements: list[str] = field(default_factory=list)

    def __getitem__(self, cle: str) -> dict[str, Any]:
        if cle in self.profil:
            return self.profil[cle]
        return self.reglages[cle]


def _fusion(defaut: dict[str, Any], lu: dict[str, Any]) -> dict[str, Any]:
    resultat = copy.deepcopy(defaut)
    for cle, valeur in lu.items():
        if isinstance(valeur, dict) and isinstance(resultat.get(cle), dict):
            resultat[cle] = _fusion(resultat[cle], valeur)
        else:
            resultat[cle] = valeur
    return resultat


def _lire_toml(chemin: Path, avertissements: list[str]) -> dict[str, Any]:
    if not chemin.is_file():
        return {}
    try:
        return tomllib.loads(chemin.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as e:
        avertissements.append(f"{chemin.name} est illisible ({e}) : toutes ses valeurs par défaut sont utilisées.")
        return {}


HEURE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def heure_valide(texte: Any) -> bool:
    return isinstance(texte, str) and HEURE.match(texte.strip()) is not None


def en_minutes(texte: str) -> int:
    m = HEURE.match(texte.strip())
    if not m:
        raise ValueError(f"heure invalide : {texte!r}")
    return int(m.group(1)) * 60 + int(m.group(2))


def normaliser_jour(texte: Any) -> str | None:
    if not isinstance(texte, str):
        return None
    t = texte.strip().lower().replace("é", "e").replace("è", "e")
    for j in JOURS:
        if t in (j, j[:3]):
            return j
    return None


class _Verif:
    """Remplace une valeur fautive par sa valeur par défaut, en le disant clairement."""

    def __init__(self, donnees: dict[str, Any], defaut: dict[str, Any], fichier: str, avert: list[str]) -> None:
        self.d, self.defaut, self.fichier, self.avert = donnees, defaut, fichier, avert

    def corriger(self, section: str, cle: str, pourquoi: str) -> None:
        valeur_defaut = copy.deepcopy(self.defaut[section][cle])
        self.avert.append(
            f"{self.fichier} [{section}] {cle} : {pourquoi} → valeur par défaut {valeur_defaut!r} utilisée."
        )
        self.d[section][cle] = valeur_defaut

    def section(self, section: str) -> None:
        if not isinstance(self.d.get(section), dict):
            self.avert.append(f"{self.fichier} : [{section}] n'est pas une section → valeurs par défaut utilisées.")
            self.d[section] = copy.deepcopy(self.defaut[section])

    def heure(self, section: str, cle: str) -> None:
        if not heure_valide(self.d[section][cle]):
            self.corriger(section, cle, f"« {self.d[section][cle]} » n'est pas une heure (HH:MM)")

    def nombre(self, section: str, cle: str, mini: float, maxi: float, entier: bool = False) -> None:
        v = self.d[section][cle]
        ok = isinstance(v, int | float) and not isinstance(v, bool) and mini <= v <= maxi
        if ok and entier and not float(v).is_integer():
            ok = False
        if not ok:
            self.corriger(section, cle, f"« {v} » doit être un nombre entre {mini:g} et {maxi:g}")
        elif entier:
            self.d[section][cle] = int(v)

    def booleen(self, section: str, cle: str) -> None:
        if not isinstance(self.d[section][cle], bool):
            self.corriger(section, cle, "doit valoir true ou false")

    def choix(self, section: str, cle: str, permis: tuple[str, ...]) -> None:
        v = self.d[section][cle]
        if not isinstance(v, str) or v.strip().lower() not in permis:
            self.corriger(section, cle, f"« {v} » n'est pas parmi {', '.join(permis)}")
        else:
            self.d[section][cle] = v.strip().lower()

    def texte(self, section: str, cle: str) -> None:
        if not isinstance(self.d[section][cle], str) or not self.d[section][cle].strip():
            self.corriger(section, cle, "doit être un texte non vide")

    def liste_textes(self, section: str, cle: str) -> list[str]:
        v = self.d[section][cle]
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            self.corriger(section, cle, 'doit être une liste de textes entre crochets, ex. ["a", "b"]')
        return [x.strip() for x in self.d[section][cle] if x.strip()]

    def jours(self, section: str, cle: str) -> None:
        brut = self.liste_textes(section, cle)
        jours = [normaliser_jour(j) for j in brut]
        if any(j is None for j in jours):
            self.corriger(section, cle, f"un des jours n'existe pas ({', '.join(brut)})")
        else:
            self.d[section][cle] = [j for j in JOURS if j in jours]


def _valider_profil(p: dict[str, Any], avert: list[str]) -> None:
    v = _Verif(p, DEFAUT_PROFIL, "profil.toml", avert)
    for s in DEFAUT_PROFIL:
        v.section(s)
    v.choix("repas", "regime", REGIMES)
    allergies = v.liste_textes("repas", "allergies")
    inconnues = [a for a in allergies if _cle(a) not in ALLERGENES]
    if inconnues:
        # Une allergie mal écrite ne doit JAMAIS être ignorée en silence : on garde celles qu'on reconnaît et on
        # signale les autres (le planificateur les traite comme des aliments détestés, contrainte dure).
        avert.append(
            f"profil.toml [repas] allergies : « {', '.join(inconnues)} » ne fait pas partie des 14 allergènes "
            f"({', '.join(ALLERGENES)}) → traité comme un aliment interdit."
        )
        p["repas"]["deteste"] = list(p["repas"].get("deteste") or []) + inconnues
    p["repas"]["allergies"] = [_cle(a) for a in allergies if _cle(a) in ALLERGENES]
    for cle in ("deteste", "aime", "cuisines_preferees", "placard"):
        p["repas"][cle] = v.liste_textes("repas", cle)
    v.nombre("repas", "portions", 1, 8, entier=True)
    v.nombre("repas", "budget_semaine", 5, 1000)
    equipement = [e.lower() for e in v.liste_textes("repas", "equipement")]
    if any(e not in EQUIPEMENTS for e in equipement):
        v.corriger("repas", "equipement", f"un équipement est inconnu (permis : {', '.join(EQUIPEMENTS)})")
    else:
        p["repas"]["equipement"] = equipement
    v.booleen("repas", "dejeuners")
    j = normaliser_jour(p["repas"]["jour_courses"])
    if j is None:
        v.corriger("repas", "jour_courses", f"« {p['repas']['jour_courses']} » n'est pas un jour")
    else:
        p["repas"]["jour_courses"] = j
    v.jours("semaine", "jours_charges")
    v.jours("semaine", "jours_de_cours")
    v.heure("trajets", "depart")
    v.heure("trajets", "retour")
    v.nombre("trajets", "duree_minutes", 5, 180, entier=True)
    v.choix("trajets", "moyen", ("velo", "tram", "marche"))
    if heure_valide(p["trajets"]["depart"]) and heure_valide(p["trajets"]["retour"]):
        if en_minutes(p["trajets"]["retour"]) <= en_minutes(p["trajets"]["depart"]):
            v.corriger("trajets", "retour", "le retour doit être après le départ")


def _valider_reglages(r: dict[str, Any], avert: list[str]) -> None:
    v = _Verif(r, DEFAUT_REGLAGES, "reglages.toml", avert)
    for s in DEFAUT_REGLAGES:
        v.section(s)
    v.texte("lieu", "ville")
    v.nombre("lieu", "latitude", -90, 90)
    v.nombre("lieu", "longitude", -180, 180)
    v.texte("lieu", "fuseau")
    for cle in DEFAUT_REGLAGES["horaires"]:
        if cle == "menu_jour":
            jour = normaliser_jour(r["horaires"][cle])
            if jour is None:
                v.corriger("horaires", cle, f"« {r['horaires'][cle]} » n'est pas un jour")
            else:
                r["horaires"][cle] = jour
        else:
            v.heure("horaires", cle)
    v.nombre("meteo", "cache_heures", 0.5, 24)
    v.booleen("ia", "active")
    v.texte("ia", "modele")
    v.nombre("ia", "budget_mensuel_usd", 0, 50)
    v.nombre("ia", "prix_entree_par_million", 0, 1000)
    v.nombre("ia", "prix_sortie_par_million", 0, 1000)
    v.nombre("ia", "delai_s", 5, 300)
    v.booleen("rappels", "active")
    v.texte("rappels", "liste_courses")
    v.texte("rappels", "liste_anniversaires")
    v.booleen("anniversaires", "contacts")
    v.nombre("anniversaires", "jours_avant_proches", 1, 30, entier=True)
    v.choix("anniversaires", "date_29_fevrier", ("28-02", "01-03"))
    v.booleen("anniversaires", "fetes")
    v.booleen("anniversaires", "dialogue")
    if not isinstance(r["installation"].get("prefixe_label"), str):
        v.corriger("installation", "prefixe_label", "doit être un texte")


def _cle(texte: str) -> str:
    """« Fruits à coque » → « fruits_a_coque » (minuscules, sans accents, espaces en _)."""
    t = texte.strip().lower()
    for a, b in (("à", "a"), ("â", "a"), ("é", "e"), ("è", "e"), ("ê", "e"), ("î", "i"), ("ô", "o"), ("û", "u"),
                 ("ù", "u"), ("ç", "c"), ("œ", "oe"), ("'", "_"), ("’", "_"), ("-", "_"), (" ", "_")):  # fmt: skip
        t = t.replace(a, b)
    return t


def charger(dossier: Path | None = None) -> Reglages:
    """Lit profil.toml et reglages.toml (dans `dossier`, par défaut Application Support/Quotidien)."""
    dossier = dossier or dossier_support()
    avertissements: list[str] = []
    profil = _fusion(DEFAUT_PROFIL, _lire_toml(dossier / "profil.toml", avertissements))
    reglages = _fusion(DEFAUT_REGLAGES, _lire_toml(dossier / "reglages.toml", avertissements))
    _valider_profil(profil, avertissements)
    _valider_reglages(reglages, avertissements)
    return Reglages(profil, reglages, avertissements)


def defauts() -> Reglages:
    return Reglages(copy.deepcopy(DEFAUT_PROFIL), copy.deepcopy(DEFAUT_REGLAGES), [])
