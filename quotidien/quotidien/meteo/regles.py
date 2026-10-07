"""Le moteur de règles de la tenue (§3), 100 % local, piloté par `regles_tenue.toml`.

Il produit, pour un jour : les couches, les accessoires, l'équipement de pluie, le conseil de transport (« prends plutôt
le tram »), la bascule de la journée, et tout ce qu'il faut au texte (températures, heures de pluie, nuit, verglas).

Règles (les seuils viennent du fichier ; valeurs par défaut entre parenthèses) :
- **couches** : selon le ressenti le plus froid de tes trajets (à vélo : ressenti − 3 °C) ;
- **gants** sous 8 °C de ressenti à vélo (2 °C à pied), **bonnet** sous 3 °C, **tour de cou** sous 5 °C ;
- **lunettes de soleil** si l'UV atteint 3 à une heure de jour et sans pluie pendant que tu es dehors ;
- **casque et éclairage** si un trajet à vélo a lieu avant le lever ou après le coucher du soleil ;
- **pluie** : plus de 1 mm pendant un trajet → imper ou poncho + sur-pantalon à vélo ; parapluie seulement sans vélo
  (et jamais par grand vent) ;
- **tram** : rafales > 50 km/h, pluie > 4 mm/h, neige ou risque de verglas pendant un trajet (≤ 1 °C avec humidité,
  pluie verglaçante, ou pluie la veille et gel au petit matin) ;
- **bascule** : 8 °C ou plus entre le matin et l'après-midi → « prends une couche que tu peux enlever ».
"""

from __future__ import annotations

import copy
import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from quotidien import config
from quotidien.meteo.open_meteo import Heure, Prevision
from quotidien.meteo.trajets import Trajet, trajets_du_jour

# Codes météo WMO (documentation d'Open-Meteo)
CODES_BROUILLARD = frozenset({45, 48})
CODES_BRUINE = frozenset({51, 53, 55})
CODES_VERGLACANTS = frozenset({56, 57, 66, 67})
CODES_PLUIE = frozenset({61, 63, 65, 80, 81, 82}) | CODES_BRUINE | CODES_VERGLACANTS
CODES_NEIGE = frozenset({71, 73, 75, 77, 85, 86})
CODES_ORAGE = frozenset({95, 96, 99})
CODES_HUMIDES = CODES_BROUILLARD | CODES_PLUIE | CODES_NEIGE | CODES_ORAGE

DEFAUT_REGLES: dict[str, Any] = {
    "velo": {"correction_ressenti": 3},
    "couches": [
        {"a_partir_de": 22, "tenue": ["t-shirt"]},
        {"a_partir_de": 17, "tenue": ["t-shirt", "veste légère"]},
        {"a_partir_de": 12, "tenue": ["pull", "veste légère"]},
        {"a_partir_de": 5, "tenue": ["pull", "manteau"]},
        {"a_partir_de": -100, "tenue": ["pull", "doudoune"]},
    ],
    "accessoires": {
        "gants_velo_sous": 8,
        "gants_a_pied_sous": 2,
        "bonnet_sous": 3,
        "tour_de_cou_sous": 5,
        "lunettes_uv_des": 3,
    },
    "pluie": {"equipement_au_dessus_de_mm": 1.0, "petite_pluie_des_mm": 0.2},
    "tram": {
        "rafales_au_dessus_de": 50,
        "pluie_forte_au_dessus_de_mm_h": 4,
        "verglas_temperature_max": 1,
        "verglas_humidite_min": 90,
        "pluie_veille_min_mm": 0.5,
        "gel_matin_fin": 9,
    },
    "bascule": {"ecart_min": 8},
    "alerte_veille": {"ecart_temperature": 8, "rafales_tempete": 70, "pluie_min_mm": 1.0},
}
COUCHES_CONNUES = ("t-shirt", "pull", "veste légère", "manteau", "doudoune")


def charger_regles(chemin: Path | None = None) -> tuple[dict[str, Any], list[str]]:
    """Le fichier de règles : celui d'Application Support s'il existe, sinon celui du projet ; une valeur fausse
    garde sa valeur par défaut (avec un message)."""
    avert: list[str] = []
    if chemin is None:
        perso = config.dossier_support() / "regles_tenue.toml"
        chemin = perso if perso.is_file() else config.racine_projet() / "regles_tenue.toml"
    regles = copy.deepcopy(DEFAUT_REGLES)
    try:
        lu = tomllib.loads(chemin.read_text(encoding="utf-8")) if chemin.is_file() else {}
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as e:
        return regles, [f"{chemin.name} illisible ({e}) : règles par défaut"]
    for section, valeurs in DEFAUT_REGLES.items():
        if section == "couches":
            continue
        brut = lu.get(section, {})
        if not isinstance(brut, dict):
            avert.append(f"regles_tenue.toml [{section}] n'est pas une section : valeurs par défaut")
            continue
        for cle in valeurs:
            if cle in brut:
                v = brut[cle]
                if isinstance(v, int | float) and not isinstance(v, bool):
                    regles[section][cle] = float(v)
                else:
                    avert.append(f"regles_tenue.toml [{section}] {cle} = {v!r} n'est pas un nombre : défaut gardé")
    couches = lu.get("couches")
    if couches is not None:
        ok = (
            isinstance(couches, list)
            and couches
            and all(
                isinstance(c, dict)
                and isinstance(c.get("a_partir_de"), int | float)
                and isinstance(c.get("tenue"), list)
                and c["tenue"]
                and all(t in COUCHES_CONNUES for t in c["tenue"])
                for c in couches
            )
        )
        if ok:
            regles["couches"] = sorted(couches, key=lambda c: -float(c["a_partir_de"]))
            if float(regles["couches"][-1]["a_partir_de"]) > -60:
                regles["couches"].append(DEFAUT_REGLES["couches"][-1])
        else:
            avert.append("regles_tenue.toml [[couches]] mal rempli (couches permises : "
                         f"{', '.join(COUCHES_CONNUES)}) : couches par défaut")  # fmt: skip
    return regles, avert


@dataclass(frozen=True)
class PluieTrajet:
    trajet: Trajet
    mm: float  # attendus pendant le trajet (au prorata de l'heure)
    max_mm_h: float
    heures: tuple[datetime, ...]  # fins des heures pluvieuses qui touchent le trajet
    episode: tuple[datetime, datetime] | None = None  # l'épisode de pluie entier (début, fin) qui touche le trajet


@dataclass
class Conseil:
    jour: date
    cours: bool
    trajets: list[Trajet]
    velo: bool  # au moins un trajet prévu à vélo
    couches: list[str]
    accessoires: list[str]
    pluie_equipement: list[str]
    tram: bool
    raisons_tram: list[str]
    nuit: bool  # un trajet à vélo avant le lever ou après le coucher du soleil
    trajets_nuit: list[str]  # lesquels (« aller », « retour »)
    verglas: bool
    bascule: tuple[int, int] | None
    fraicheur_retour: tuple[int, int] | None
    ressenti_min: float  # corrigé du vélo
    temp_matin: float
    temp_max: float
    pluies: list[PluieTrajet]
    pluie_journee: tuple[datetime, datetime] | None  # première et dernière heure de pluie entre 7 h et 21 h
    rafales_max: float
    uv_max: float
    orage: bool
    neige: bool
    brouillard: bool
    situation: str
    emoji: str
    hors_ligne: bool = False
    age_prevision_h: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def velo_aujourdhui(self) -> bool:
        """Vélo prévu ET pas de tram conseillé : décide imper/poncho contre parapluie."""
        return self.velo and not self.tram


def _heures_trajet(prev: Prevision, t: Trajet) -> list[Heure]:
    """Les heures dont l'instant encadre le trajet (l'heure pleine d'avant jusqu'à l'heure pleine d'après)."""
    debut = t.debut.replace(minute=0, second=0, microsecond=0)
    fin = t.fin if t.fin.minute == 0 and t.fin.second == 0 else (t.fin + timedelta(hours=1))
    fin = fin.replace(minute=0, second=0, microsecond=0)
    return prev.entre(debut, fin)


def _de_jour(prev: Prevision, instant: datetime) -> bool:
    s = prev.soleil.get(instant.date())
    if s is None:
        return 7 <= instant.hour < 19
    return s.lever <= instant <= s.coucher


def _trajet_de_nuit(prev: Prevision, t: Trajet) -> bool:
    s = prev.soleil.get(t.debut.date())
    if s is None:
        return t.debut.hour < 7 or t.fin.hour >= 19
    return t.debut < s.lever or t.fin > s.coucher


def _humide(h: Heure, regles: dict[str, Any]) -> bool:
    return h.humidite >= regles["tram"]["verglas_humidite_min"] or h.pluie > 0 or h.code in CODES_HUMIDES


def risque_verglas(prev: Prevision, jour: date, heures: list[Heure], regles: dict[str, Any]) -> bool:
    r = regles["tram"]
    for h in heures:
        if h.code in CODES_VERGLACANTS:
            return True
        if h.temperature <= r["verglas_temperature_max"] and _humide(h, regles):
            return True
    zone = heures[0].instant.tzinfo if heures else None
    if zone is None:
        return False
    minuit = datetime.combine(jour, time(0, 0), tzinfo=zone)
    veille = sum(h.pluie * part for h, part in prev.couvrant(minuit - timedelta(days=1), minuit))
    matin = prev.entre(minuit, minuit + timedelta(hours=float(r["gel_matin_fin"])))
    gel_matin = bool(matin) and min(h.temperature for h in matin) < 0
    premier = min(h.instant for h in heures)
    return veille >= r["pluie_veille_min_mm"] and gel_matin and premier.hour < 12


def _pluie_trajet(prev: Prevision, t: Trajet, petite: float) -> PluieTrajet:
    couvertes = prev.couvrant(t.debut, t.fin)
    mm = sum(h.pluie * part for h, part in couvertes)
    max_h = max((h.pluie for h, _ in couvertes), default=0.0)
    pluvieuses = tuple(h.instant for h, _ in couvertes if h.pluie >= petite)
    episode = None
    if pluvieuses:
        # L'épisode entier : les heures pluvieuses qui se suivent, avant et après le trajet.
        index = {h.instant: i for i, h in enumerate(prev.heures)}
        i = j = index[pluvieuses[0]]
        while i > 0 and prev.heures[i - 1].pluie >= petite:
            i -= 1
        j = index[pluvieuses[-1]]
        while j + 1 < len(prev.heures) and prev.heures[j + 1].pluie >= petite:
            j += 1
        episode = (prev.heures[i].instant - timedelta(hours=1), prev.heures[j].instant)
    return PluieTrajet(t, round(mm, 2), max_h, pluvieuses, episode)


def _couches(ressenti: float, regles: dict[str, Any]) -> list[str]:
    for palier in regles["couches"]:
        if ressenti >= float(palier["a_partir_de"]):
            return list(palier["tenue"])
    return list(regles["couches"][-1]["tenue"])


def conseiller(
    prev: Prevision, jour: date, profil: dict[str, Any], regles: dict[str, Any], maintenant: float | None = None
) -> Conseil | None:
    """Le conseil du jour, ou None si la prévision ne couvre pas tes trajets."""
    trajets = trajets_du_jour(jour, profil, prev.fuseau)
    par_trajet = {t.nom: _heures_trajet(prev, t) for t in trajets}
    if any(not hs for hs in par_trajet.values()):
        return None
    cours = trajets[0].nom != "journée"
    velo = any(t.velo for t in trajets)
    correction = float(regles["velo"]["correction_ressenti"])
    acc_r, pl_r, tr_r = regles["accessoires"], regles["pluie"], regles["tram"]
    petite = float(pl_r["petite_pluie_des_mm"])

    # Ressenti le plus froid de tes trajets (à vélo, l'air de la vitesse en plus).
    ressenti_min = min(min(h.ressenti for h in par_trajet[t.nom]) - (correction if t.velo else 0.0) for t in trajets)
    toutes = [h for hs in par_trajet.values() for h in hs]
    pluies = [_pluie_trajet(prev, t, petite) for t in trajets]

    # Transport
    raisons: list[str] = []
    rafales_max = max((h.rafales for t in trajets for h, _ in prev.couvrant(t.debut, t.fin)), default=0.0)
    rafales_max = max(rafales_max, max(h.rafales for h in toutes))
    if rafales_max > tr_r["rafales_au_dessus_de"]:
        raisons.append(f"rafales à {round(rafales_max)} km/h")
    forte = max((p.max_mm_h for p in pluies), default=0.0)
    if forte > tr_r["pluie_forte_au_dessus_de_mm_h"]:
        raisons.append(f"grosse pluie ({forte:.0f} mm/h)")
    neige = any(h.code in CODES_NEIGE for h in toutes)
    if neige:
        raisons.append("neige")
    verglas = risque_verglas(prev, jour, toutes, regles)
    if verglas:
        raisons.append("risque de verglas")
    tram = bool(raisons)

    # Couches et accessoires
    couches = _couches(ressenti_min, regles)
    accessoires: list[str] = []
    seuil_gants = acc_r["gants_velo_sous"] if velo else acc_r["gants_a_pied_sous"]
    if ressenti_min < seuil_gants:
        accessoires.append("gants")
    if ressenti_min < acc_r["bonnet_sous"]:
        accessoires.append("bonnet")
    if ressenti_min < acc_r["tour_de_cou_sous"]:
        accessoires.append("tour de cou")

    # Lunettes : une heure de jour, sans pluie, avec un UV suffisant, pendant que tu es dehors.
    fenetre = prev.entre(trajets[0].debut.replace(minute=0), trajets[-1].fin)
    soleil_utile = [
        h
        for h in fenetre
        if _de_jour(prev, h.instant)
        and h.pluie < petite
        and h.code not in CODES_PLUIE | CODES_NEIGE | CODES_ORAGE
        and h.uv >= acc_r["lunettes_uv_des"]
    ]
    uv_max = max((h.uv for h in fenetre), default=0.0)
    if soleil_utile:
        accessoires.append("lunettes de soleil")
    trajets_nuit = [t.nom for t in trajets if t.velo and _trajet_de_nuit(prev, t)]
    nuit = bool(trajets_nuit)
    if nuit:
        accessoires += ["casque", "éclairage"]

    # Pluie
    mouille = any(p.mm > pl_r["equipement_au_dessus_de_mm"] for p in pluies)
    equipement: list[str] = []
    if mouille:
        if velo and not tram:
            equipement = ["imper ou poncho", "sur-pantalon"]
        elif rafales_max > tr_r["rafales_au_dessus_de"]:
            equipement = ["imper à capuche"]  # trop de vent pour un parapluie
        else:
            equipement = ["parapluie"]

    # Bascule de la journée
    zone = trajets[0].debut.tzinfo
    debut_jour = datetime.combine(jour, time(0, 0), tzinfo=zone)
    matin = par_trajet[trajets[0].nom][0]
    temp_matin = min(h.temperature for h in par_trajet[trajets[0].nom])
    apres_midi = prev.entre(debut_jour + timedelta(hours=12), debut_jour + timedelta(hours=18))
    temp_max = max([h.temperature for h in apres_midi] + [h.temperature for h in toutes])
    bascule = None
    if temp_max - temp_matin >= regles["bascule"]["ecart_min"]:
        bascule = (round(temp_matin), round(temp_max))
    fraicheur = None
    if cours:
        temp_retour = min(h.temperature for h in par_trajet["retour"])
        if matin.temperature - temp_retour >= regles["bascule"]["ecart_min"]:
            fraicheur = (round(matin.temperature), round(temp_retour))

    # Pluie de la journée (pour dire « pluie entre 14h et 16h » même hors trajets)
    journee = prev.couvrant(debut_jour + timedelta(hours=7), debut_jour + timedelta(hours=21))
    pluvieuses = [h.instant for h, _ in journee if h.pluie >= petite]
    pluie_journee = (pluvieuses[0] - timedelta(hours=1), pluvieuses[-1]) if pluvieuses else None

    orage = any(h.code in CODES_ORAGE for h in fenetre + toutes)
    brouillard = any(h.code in CODES_BROUILLARD for h in toutes)
    pluie_trajet = mouille or any(p.mm >= petite for p in pluies)
    vent = rafales_max > tr_r["rafales_au_dessus_de"]
    situation, emoji = _situation(
        orage, neige, verglas, pluie_trajet, vent, pluie_journee is not None, brouillard, ressenti_min, temp_max,
        fenetre, prev,
    )  # fmt: skip
    if situation in ("orage", "neige") and "lunettes de soleil" in accessoires:
        accessoires.remove("lunettes de soleil")  # « Il neige… lunettes de soleil » : le message se contredirait
    conseil = Conseil(
        jour=jour,
        cours=cours,
        trajets=trajets,
        velo=velo,
        couches=couches,
        accessoires=accessoires,
        pluie_equipement=equipement,
        tram=tram,
        raisons_tram=raisons,
        nuit=nuit,
        trajets_nuit=trajets_nuit,
        verglas=verglas,
        bascule=bascule,
        fraicheur_retour=fraicheur,
        ressenti_min=ressenti_min,
        temp_matin=temp_matin,
        temp_max=temp_max,
        pluies=pluies,
        pluie_journee=pluie_journee,
        rafales_max=rafales_max,
        uv_max=uv_max,
        orage=orage,
        neige=neige,
        brouillard=brouillard,
        situation=situation,
        emoji=emoji,
        hors_ligne=prev.hors_ligne,
        age_prevision_h=prev.age_heures(maintenant) if maintenant is not None else 0.0,
    )
    return conseil


def _situation(
    orage: bool,
    neige: bool,
    verglas: bool,
    pluie_trajet: bool,
    vent: bool,
    pluie_journee: bool,
    brouillard: bool,
    ressenti_min: float,
    temp_max: float,
    fenetre: list[Heure],
    prev: Prevision,
) -> tuple[str, str]:
    """La situation qui domine (elle choisit l'emoji et les modèles de texte)."""
    if orage:
        return "orage", "⛈️"
    if neige:
        return "neige", "❄️"
    if verglas:
        return "verglas", "🧊"
    if pluie_trajet:
        return "pluie_trajet", "🌧️"
    if vent:
        return "vent", "💨"
    if pluie_journee:
        return "pluie_journee", "🌦️"
    if brouillard:
        return "brouillard", "🌫️"
    if ressenti_min < 5:
        return "froid", "🥶"
    if temp_max >= 27:
        return "chaud", "🥵"
    de_jour = [h for h in fenetre if _de_jour(prev, h.instant)]
    if de_jour and sum(h.code <= 1 for h in de_jour) >= len(de_jour) / 2:
        return "beau", "☀️"
    if de_jour and sum(h.code <= 2 for h in de_jour) >= len(de_jour) / 2:
        return "voile", "⛅"
    return "gris", "☁️"
