"""Le juge du §9.2 : mesurer un faux Mac comme le ferait le démon, analyser, et comparer à la vérité terrain."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modules.demarrage import scan
from modules.demarrage.analyse import Bilan, analyser
from modules.demarrage.db import Base
from modules.demarrage.mesure.echantillonneur import Echantillonneur
from tests.demarrage.faux_mac.construire import Construction


def diagnostiquer(faux: Construction, dossier: Path, reglages: dict[str, Any], croisiere_min: int = 30) -> Bilan:
    """Scan à la connexion, mode « ouverture de session » 5 min, puis croisière, puis analyse."""
    base = Base(dossier / "demarrage.db")
    try:
        faux.a_l_instant(0)
        inventaire = scan.scanner(faux.mac, reglages)
        base.enregistrer_scan(inventaire)
        ech = Echantillonneur(faux.mac, base, reglages, lambda: inventaire.fiches)
        ech.suivre_session(faux.boot, faux.connexion)
        e = reglages["echantillonnage"]
        debut = faux.mac.maintenant()
        while faux.mac.maintenant() < debut + croisiere_min * 60:
            ecoule = faux.mac.maintenant() - debut
            ech.prendre("croisiere", avec_energie=ecoule % e["energie_pas_s"] < e["croisiere_pas_s"])
            faux.mac.attendre(e["croisiere_pas_s"])
        return analyser(inventaire, base, reglages, faux.mac.maintenant())
    finally:
        base.fermer()


@dataclass
class Jugement:
    erreurs: list[str] = field(default_factory=list)
    lignes: list[tuple[str, str, str, str, float]] = field(
        default_factory=list
    )  # label, attendu, obtenu, action, impact

    @property
    def reussi(self) -> bool:
        return not self.erreurs


def juger(faux: Construction, bilan: Bilan) -> Jugement:
    j = Jugement()
    par_cle = {(e.fiche.source, e.fiche.label): e for e in bilan.elements}
    for (source, label), attendu in faux.verite.items():
        e = par_cle.get((source, label))
        if e is None:
            j.erreurs.append(f"{source}/{label} : pas trouvé")
            continue
        j.lignes.append((label, attendu.verdict, e.verdict.code, e.verdict.action, e.impact))
        if e.verdict.code != attendu.verdict:
            j.erreurs.append(f"{label} : verdict {e.verdict.code} ({e.verdict.raison}), attendu {attendu.verdict}")
        if e.verdict.action != attendu.action:
            j.erreurs.append(f"{label} : action {e.verdict.action}, attendue {attendu.action}")
        if ("empêche la veille" in e.drapeaux) != attendu.empeche_veille:
            j.erreurs.append(f"{label} : « empêche la veille » = {'empêche la veille' in e.drapeaux}")
    for e in bilan.elements:
        if e.verdict.code == "apple" and e.verdict.action != "aucune":
            j.erreurs.append(f"{e.fiche.label} : élément Apple avec une action ({e.verdict.action})")
        if e.fiche.est_apple and e.verdict.code != "apple":
            j.erreurs.append(f"{e.fiche.label} : élément Apple jugé {e.verdict.code}")
        if e.verdict.code == "inconnu" and e.verdict.action != "verifier":
            j.erreurs.append(f"{e.fiche.label} : inconnu avec l'action {e.verdict.action} (seulement « vérifier »)")
    lourds = {label for (_, label), a in faux.verite.items() if a.lourd}
    tete = {e.fiche.label for e in bilan.classement[: len(lourds)]}
    if lourds and tete != lourds:
        j.erreurs.append(f"en tête : {sorted(tete)}, attendus : {sorted(lourds)}")
    return j
