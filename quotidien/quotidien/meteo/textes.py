"""Les textes de la météo (§3) : naturels, variés, deux lignes au plus.

- Chaque situation (pluie au trajet, grand beau, froid, verglas…) a au moins 5 modèles de phrase ; chaque phrase
  d'appoint (tram, retour, bascule, nuit) aussi.
- Le modèle du jour tourne avec la date : deux jours qui se suivent n'emploient jamais le même modèle, donc jamais le
  même message 3 jours de suite (ni même 2). Le même jour, le texte reste stable.
- Le texte est rangé dans la base (`textes_meteo`), pour l'historique et `quotidien doctor`.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

from quotidien.db import Base
from quotidien.meteo.regles import Conseil
from quotidien.meteo.trajets import heure_lisible

LONGUEUR_LIGNE = 120

PRINCIPALES: dict[str, list[str]] = {
    "pluie_trajet": [
        "{e} {t}, pluie {quand} : {tenue}.",
        "{e} {t} et de la pluie {quand} : {tenue}.",
        "{e} Pluie {quand}, {t} : {tenue}.",
        "{e} {t}, ça mouille {quand} : {tenue}.",
        "{e} Il pleut {quand} ({t}) : {tenue}.",
        "{e} {t}, averses {quand} : {tenue}.",
    ],
    "pluie_journee": [
        "{e} {t}, sec pour tes trajets mais pluie {quand} : {tenue}.",
        "{e} {t}, quelques gouttes {quand} : {tenue}.",
        "{e} Pluie {quand}, {t} : {tenue}.",
        "{e} {t} avec de la pluie {quand} : {tenue}.",
        "{e} {t}, la pluie passe {quand} : {tenue}.",
    ],
    "orage": [
        "{e} Orages annoncés, {t} : {tenue}.",
        "{e} {t} et de l'orage dans l'air : {tenue}.",
        "{e} Temps orageux, {t} : {tenue}.",
        "{e} {t}, risque d'orage : {tenue}.",
        "{e} Ciel d'orage, {t} : {tenue}.",
    ],
    "neige": [
        "{e} Neige au programme, {t} : {tenue}.",
        "{e} {t} et de la neige : {tenue}.",
        "{e} Il neige, {t} : {tenue}.",
        "{e} {t}, flocons attendus : {tenue}.",
        "{e} De la neige à Bordeaux, {t} : {tenue}.",
    ],
    "verglas": [
        "{e} {t}, routes glissantes : {tenue}.",
        "{e} Risque de verglas, {t} : {tenue}.",
        "{e} {t} et sol gelé par endroits : {tenue}.",
        "{e} Gare au verglas, {t} : {tenue}.",
        "{e} {t}, ça peut glisser : {tenue}.",
    ],
    "vent": [
        "{e} {t}, grand vent : {tenue}.",
        "{e} Ça souffle fort, {t} : {tenue}.",
        "{e} {t} et des rafales : {tenue}.",
        "{e} Journée venteuse, {t} : {tenue}.",
        "{e} {t}, le vent forcit : {tenue}.",
    ],
    "brouillard": [
        "{e} {t}, brouillard : {tenue}.",
        "{e} Brume au départ, {t} : {tenue}.",
        "{e} {t}, visibilité réduite : {tenue}.",
        "{e} Brouillard sur Bordeaux, {t} : {tenue}.",
        "{e} {t} dans la brume : {tenue}.",
    ],
    "froid": [
        "{e} {t}, sec mais froid : {tenue}.",
        "{e} Froid ce matin, {t} : {tenue}.",
        "{e} {t}, ça pique : {tenue}.",
        "{e} {t} et un air glacial : {tenue}.",
        "{e} Couvre-toi, {t} : {tenue}.",
    ],
    "chaud": [
        "{e} {t}, il va faire chaud : {tenue}.",
        "{e} Chaleur au programme, {t} : {tenue}.",
        "{e} {t}, sec et chaud : {tenue}.",
        "{e} Journée chaude, {t} : {tenue}.",
        "{e} {t} : {tenue}, et pense à boire.",
    ],
    "beau": [
        "{e} {t}, sec : {tenue}.",
        "{e} Grand beau, {t} : {tenue}.",
        "{e} {t} et du soleil : {tenue}.",
        "{e} Ciel dégagé, {t} : {tenue}.",
        "{e} {t}, sec et lumineux : {tenue}.",
    ],
    "voile": [
        "{e} {t}, sec avec quelques nuages : {tenue}.",
        "{e} Éclaircies, {t} : {tenue}.",
        "{e} {t}, entre soleil et nuages : {tenue}.",
        "{e} Ciel partagé, {t} : {tenue}.",
        "{e} {t}, sec : {tenue}.",
    ],
    "gris": [
        "{e} {t}, gris mais sec : {tenue}.",
        "{e} Ciel couvert, {t} : {tenue}.",
        "{e} {t}, sec sous les nuages : {tenue}.",
        "{e} Temps gris, {t} : {tenue}.",
        "{e} {t}, couvert et sec : {tenue}.",
    ],
}

VELO_OK = ["Vélo OK.", "Vélo sans souci.", "Rien n'empêche le vélo.", "Le vélo, tranquille.", "Bonne route à vélo."]
TRAM = [
    "Prends plutôt le tram : {raisons}.",
    "Laisse le vélo, prends le tram : {raisons}.",
    "Tram conseillé : {raisons}.",
    "Aujourd'hui, c'est tram : {raisons}.",
    "Mieux vaut le tram : {raisons}.",
]
TRAM_JOURNEE = [
    "Si tu sors, privilégie le tram : {raisons}.",
    "Pour sortir, le tram plutôt que le vélo : {raisons}.",
    "Tram conseillé si tu bouges : {raisons}.",
    "Si tu dois te déplacer, prends le tram : {raisons}.",
    "Pas de vélo pour sortir, le tram plutôt : {raisons}.",
]
RETOUR_SEC = [
    "Retour au sec vers {h}.",
    "Le retour ({h}) sera sec.",
    "Au retour, vers {h}, plus de pluie.",
    "Sec pour rentrer vers {h}.",
    "Pas de pluie au retour ({h}).",
]
RETOUR_PLUIE = [
    "Pluie aussi au retour ({h}) : garde l'équipement.",
    "Ça remet ça au retour vers {h}.",
    "Retour vers {h} sous la pluie aussi.",
    "Le retour ({h}) sera mouillé aussi.",
    "Prévois la pluie pour rentrer vers {h}.",
]
RETOUR_SEUL_PLUIE = [
    "Sec à l'aller, pluie au retour vers {h} : {equipement} dans le sac.",
    "Départ au sec, mais pluie vers {h} : {equipement} dans le sac.",
    "Le retour ({h}) sera mouillé : glisse {equipement} dans le sac.",
    "Pluie prévue pour rentrer vers {h} : emporte {equipement}.",
    "Aller au sec, retour vers {h} sous la pluie : {equipement} dans le sac.",
]
BASCULE = [
    "Il fera {m} °C le matin et {a} °C l'après-midi : prends une couche que tu peux enlever.",
    "De {m} °C le matin à {a} °C l'après-midi : une couche à enlever.",
    "{m} °C au départ, {a} °C plus tard : habille-toi en couches.",
    "Ça monte de {m} °C à {a} °C : prévois de quoi te découvrir.",
    "Matin à {m} °C, après-midi à {a} °C : une couche facile à retirer.",
]
FRAICHEUR = [
    "Il ne fera plus que {r} °C au retour : garde une couche chaude.",
    "Retour plus frais ({r} °C) : ne laisse pas ta veste.",
    "Ça descend à {r} °C pour rentrer : couvre-toi au retour.",
    "{r} °C seulement au retour : prévois une couche de plus.",
    "Fraîcheur au retour ({r} °C) : garde de quoi te couvrir.",
]
NUIT = [
    "Il fera nuit {quand} : casque et éclairage.",
    "Nuit noire {quand} : éclairage allumé et casque.",
    "{Quand}, il fera nuit : éclairage et casque.",
    "Pense à l'éclairage et au casque : il fera nuit {quand}.",
    "Dans le noir {quand} : allume ton éclairage, casque sur la tête.",
]


def _indice(jour: date, cle: str, n: int) -> int:
    """Le modèle du jour : il tourne d'un cran chaque jour (deux jours qui se suivent diffèrent toujours)."""
    decalage = int(hashlib.sha256(cle.encode()).hexdigest()[:6], 16)
    return (jour.toordinal() + decalage) % n


def _choisir(modeles: list[str], jour: date, cle: str) -> str:
    return modeles[_indice(jour, cle, len(modeles))]


def degres(valeur: float) -> str:
    v = round(valeur)
    return f"{'−' if v < 0 else ''}{abs(v)} °C"


def _temperatures(c: Conseil) -> str:
    if round(c.temp_max) - round(c.temp_matin) >= 3:
        return f"{degres(c.temp_matin)} → {degres(c.temp_max)}"
    return degres(c.temp_matin)


def tenue(c: Conseil) -> str:
    """« imper ou poncho + sur-pantalon, pull + manteau, gants » : la pluie d'abord, puis les couches, puis le reste."""
    morceaux: list[str] = []
    if c.pluie_equipement:
        morceaux.append(" + ".join(c.pluie_equipement))
    morceaux.append(" + ".join(c.couches))
    autres = [a for a in c.accessoires if a not in ("casque", "éclairage")]
    if autres:
        lunettes = "lunettes" if "lunettes de soleil" in autres and len(autres) > 1 else "lunettes de soleil"
        autres = [lunettes if a == "lunettes de soleil" else a for a in autres]
        texte = ", ".join(autres)
        if "gants" in autres and c.velo_aujourdhui:
            texte = texte.replace("gants", "gants à vélo", 1)
        morceaux.append(texte)
    if not c.cours and "lunettes" in morceaux[-1]:
        morceaux[-1] += " si tu sors"
    return ", ".join(morceaux)


def _plage(debut: datetime, fin: datetime) -> str:
    if (fin - debut).total_seconds() <= 3600:
        return (
            f"vers {heure_lisible(debut)}" if debut.minute else f"entre {heure_lisible(debut)} et {heure_lisible(fin)}"
        )
    return f"entre {heure_lisible(debut)} et {heure_lisible(fin)}"


def _quand_pluie(c: Conseil) -> str:
    pluvieux = [p for p in c.pluies if p.heures]
    if c.cours and len(pluvieux) == 2:
        return "à l'aller et au retour"
    if pluvieux:
        p = pluvieux[0]
        if p.episode is not None:
            return _plage(*p.episode)
        return _plage(min(p.heures) - timedelta(hours=1), max(p.heures))
    if c.pluie_journee:
        return _plage(*c.pluie_journee)
    return "dans la journée"


def _retour(c: Conseil) -> str | None:
    if not c.cours or len(c.pluies) != 2:
        return None
    aller, retour = c.pluies
    h = heure_lisible(retour.trajet.debut)
    if aller.heures and not retour.heures:
        return _choisir(RETOUR_SEC, c.jour, "retour_sec").format(h=h)
    if aller.heures and retour.heures:
        return _choisir(RETOUR_PLUIE, c.jour, "retour_pluie").format(h=h)
    if retour.heures and retour.mm > 0:
        equipement = " + ".join(c.pluie_equipement) if c.pluie_equipement else "une veste de pluie"
        return _choisir(RETOUR_SEUL_PLUIE, c.jour, "retour_seul").format(h=h, equipement=equipement)
    return None


def _nuit(c: Conseil, trajets_nuit: list[str]) -> str:
    quand = {"aller": "à l'aller", "retour": "au retour"}
    texte = " comme ".join(quand.get(t, t) for t in trajets_nuit)
    modele = _choisir(NUIT, c.jour, "nuit")
    return modele.replace("{Quand}", texte[:1].upper() + texte[1:]).format(quand=texte)


def rediger(c: Conseil) -> str:
    """Le texte du jour, deux lignes au plus."""
    principale = _choisir(PRINCIPALES[c.situation], c.jour, c.situation).format(
        e=c.emoji, t=_temperatures(c), quand=_quand_pluie(c), tenue=tenue(c)
    )
    raisons = ", ".join(c.raisons_tram)
    # Par ordre d'importance : la sécurité (tram, nuit) passe toujours ; « Vélo OK » en dernier.
    importantes: list[str] = []
    if c.tram:
        importantes.append(_choisir(TRAM if c.cours else TRAM_JOURNEE, c.jour, "tram").format(raisons=raisons))
    if c.nuit:
        importantes.append(_nuit(c, c.trajets_nuit))
    extras: list[str] = []
    if c.bascule:
        extras.append(_choisir(BASCULE, c.jour, "bascule").format(m=c.bascule[0], a=c.bascule[1]))
    retour = _retour(c)
    if retour:
        extras.append(retour)
    if c.fraicheur_retour and not c.bascule:
        extras.append(_choisir(FRAICHEUR, c.jour, "fraicheur").format(r=c.fraicheur_retour[1]))
    velo_ok = _choisir(VELO_OK, c.jour, "velo_ok") if c.velo and not c.tram else ""
    hors_ligne = f" (prévision d'il y a {c.age_prevision_h:.0f} h, Mac hors ligne)" if c.hors_ligne else ""

    ligne1 = principale
    if velo_ok and len(ligne1) + 1 + len(velo_ok) <= LONGUEUR_LIGNE:
        ligne1, velo_ok = f"{ligne1} {velo_ok}", ""
    ligne2 = " ".join(importantes)  # toujours gardées, quelle que soit la longueur
    for phrase in [*extras, velo_ok]:
        if phrase and (not ligne2 or len(ligne2) + 1 + len(phrase) <= LONGUEUR_LIGNE):
            ligne2 = f"{ligne2} {phrase}".strip()
    if hors_ligne:
        if ligne2:
            ligne2 += hors_ligne
        else:
            ligne1 += hors_ligne
    return ligne1 if not ligne2 else f"{ligne1}\n{ligne2}"


def noter(base: Base, c: Conseil, texte: str) -> None:
    with base.transaction() as cx:
        cx.execute(
            "INSERT INTO textes_meteo(jour, situation, texte) VALUES (?, ?, ?) "
            "ON CONFLICT(jour) DO UPDATE SET situation = excluded.situation, texte = excluded.texte",
            (c.jour.isoformat(), c.situation, texte),
        )
