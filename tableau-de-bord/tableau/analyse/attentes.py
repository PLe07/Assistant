"""« A-t-il fait son travail ? » : chaque attente du registre, contrôlée sur la trace laissée par le module (§4.2).

- **Quotidienne** (« brief vers 7h15 », tolérance 20 min) : la dernière échéance passée est **tenue** si une trace
  existe depuis (jusqu'à 30 min d'avance comprises), **manquée** si la limite (échéance + tolérance) est passée sans
  trace. Si le Mac dormait à l'échéance ou pendant la tolérance, la limite est **reportée au réveil** (+ tolérance) :
  le module rattrape, sans fausse alerte. Une échéance d'avant la première fois qu'on a vu le module ne compte pas.
- **Périodique** (« relève Gmail toutes les 5 min », tolérance 15 min) : manquée si le **temps éveillé** depuis la
  dernière trace dépasse la plus grande de 3 périodes et de période + tolérance.
- Une attente éteinte chez le module (relève Gmail désactivée dans Bouclier) est « inactive ».
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from tableau import planif, textes
from tableau.db import Base
from tableau.module import Attente, DefModule, Observation

AVANCE_MAX_S = 30 * 60


@dataclass
class Verdict:
    attente: Attente
    statut: str  # tenue, manquee, en_attente, inactive
    echeance: float | None = None
    prochaine: float | None = None
    derniere_preuve: float | None = None
    detail: str = ""

    def en_dict(self) -> dict[str, Any]:
        return {
            "id": self.attente.id,
            "libelle": self.attente.libelle,
            "statut": self.statut,
            "echeance": self.echeance,
            "prochaine": self.prochaine,
            "derniere_preuve": self.derniere_preuve,
            "detail": self.detail,
        }


def reglee(a: Attente, obs: Observation) -> tuple[Attente, bool]:
    """L'attente du registre, ajustée par ce que le module dit de lui-même ; et si elle est active."""
    regle = obs.reglages_attentes.get(a.id, {})
    if regle.get("actif") is False:
        return a, False
    changements: dict[str, Any] = {}
    if isinstance(regle.get("heure"), str) and ":" in regle["heure"]:
        changements["heure"] = regle["heure"]
    if isinstance(regle.get("toutes_les_min"), int) and regle["toutes_les_min"] > 0:
        changements["toutes_les_min"] = regle["toutes_les_min"]
    return (replace(a, **changements) if changements else a), True


def _limite_avec_rattrapage(base: Base, echeance: float, tolerance_s: float) -> float:
    limite = echeance + tolerance_s
    for _debut, fin in planif.veilles(base, echeance - tolerance_s, limite):
        if fin > echeance - tolerance_s:
            limite = max(limite, fin + tolerance_s)
    return limite


def quotidienne(base: Base, a: Attente, preuve: float | None, maintenant: float, premier_vu: float) -> Verdict:
    assert a.heure is not None
    aujourdhui = planif.echeance_locale(maintenant, a.heure)
    echeance = aujourdhui if maintenant >= aujourdhui else planif.echeance_locale(maintenant, a.heure, -1)
    prochaine = planif.echeance_locale(maintenant, a.heure, 1 if maintenant >= aujourdhui else 0)
    tolerance_s = a.tolerance_min * 60
    tenue = preuve is not None and preuve >= echeance - AVANCE_MAX_S
    if tenue:
        return Verdict(a, "tenue", echeance, prochaine, preuve, f"fait {textes.quand(preuve or 0, maintenant)}")
    if echeance < premier_vu:
        return Verdict(a, "en_attente", echeance, prochaine, preuve, "pas encore observé à cette heure-là")
    limite = _limite_avec_rattrapage(base, echeance, tolerance_s)
    if maintenant <= limite:
        return Verdict(a, "en_attente", echeance, prochaine, preuve, f"attendu vers {textes.heure_texte(a.heure)}")
    return Verdict(a, "manquee", echeance, prochaine, preuve, f"pas fait (attendu vers {textes.heure_texte(a.heure)})")


def periodique(base: Base, a: Attente, preuve: float | None, maintenant: float, premier_vu: float) -> Verdict:
    assert a.toutes_les_min is not None
    periode = a.toutes_les_min * 60
    limite = max(3 * periode, periode + a.tolerance_min * 60)
    reference = preuve if preuve is not None else premier_vu
    eveille = planif.temps_eveille(base, reference, maintenant)
    prochaine = (preuve + periode) if preuve is not None else None
    if eveille <= limite:
        statut = "tenue" if preuve is not None else "en_attente"
        detail = f"dernier passage {textes.il_y_a(preuve, maintenant)}" if preuve else "pas encore vu"
        return Verdict(a, statut, None, prochaine, preuve, detail)
    detail = f"aucun passage depuis {textes.duree(eveille)}" if preuve else f"jamais vu en {textes.duree(eveille)}"
    return Verdict(a, "manquee", None, prochaine, preuve, detail)


def evaluer(base: Base, defn: DefModule, obs: Observation, maintenant: float) -> list[Verdict]:
    """Les verdicts de toutes les attentes d'un module installé et actif."""
    if not obs.installe or obs.actif is False:
        return []
    cle = f"premier_vu:{defn.id}"
    premier = base.lire_meta(cle)
    if premier is None:
        base.ecrire_meta(cle, str(maintenant))
        premier_vu = maintenant
    else:
        premier_vu = float(premier)
    verdicts: list[Verdict] = []
    for brute in defn.attentes:
        a, active = reglee(brute, obs)
        if not active:
            verdicts.append(Verdict(a, "inactive", detail="éteinte dans ses réglages"))
            continue
        preuve = obs.preuves.get(a.cle_preuve)
        if a.genre == "quotidienne" and a.heure:
            v = quotidienne(base, a, preuve, maintenant, premier_vu)
            if v.echeance is not None and v.statut in ("tenue", "manquee"):
                base.executer(
                    "INSERT INTO attentes (module, attente, echeance, statut, constate_le, detail) "
                    "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(module, attente, echeance) DO UPDATE SET "
                    "statut = excluded.statut, constate_le = excluded.constate_le, detail = excluded.detail",
                    (defn.id, a.id, v.echeance, v.statut, maintenant, v.detail),
                )
            verdicts.append(v)
        elif a.genre == "periodique" and a.toutes_les_min:
            verdicts.append(periodique(base, a, preuve, maintenant, premier_vu))
    return verdicts


def historique(base: Base, module: str, depuis: float) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in base.lignes(
            "SELECT attente, echeance, statut, detail FROM attentes "
            "WHERE module = ? AND echeance >= ? ORDER BY echeance",
            (module, depuis),
        )
    ]
