"""La réponse affichée (iPhone, notification, Terminal), en français simple, au format du §3.4 :

    🔴 Arnaque très probable — faux message « Colissimo »
    • Le lien mène à « colissimo-suivi-frais.top », pas au site officiel de Colissimo (laposte.fr).
    • Il te demande de payer 1,99 € pour un colis : La Poste et les transporteurs ne font jamais ça par SMS ou par mail.
    • Ce site a été créé il y a 3 jours.
    👉 Ne clique pas. Signale le SMS au 33700. Supprime-le.

Les gestes viennent uniquement de `reflexes.json` (sources officielles dans `urgence/sources.json`), jamais de l'IA.
Bouclier ne dit jamais « sûr » : au mieux « Pas de signe d'arnaque détecté », toujours avec « vérifie par un autre
canal en cas de doute ».
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from bouclier.arnaque.familles import FAMILLES
from bouclier.arnaque.signaux import Niveau
from bouclier.arnaque.veto import Verdict

CHEMIN_REFLEXES = Path(__file__).with_name("reflexes.json")

TITRES = {
    Niveau.ARNAQUE: "Arnaque très probable",
    Niveau.TRES_SUSPECT: "Très suspect",
    Niveau.PRUDENCE: "Prudence",
    Niveau.AUCUN_SIGNE: "Pas de signe d'arnaque détecté",
}
AUTRE_CANAL = "Vérifie par un autre canal en cas de doute (l'appli ou le site officiels, un numéro que tu connais)."
PAUSE_BUDGET = "Analyse avancée en pause : le budget du mois est atteint (analyse locale seule)."
_NOMS_FAMILLES = {f.id: f.nom for f in FAMILLES} | {"proche": "faux proche en détresse"}


@lru_cache(maxsize=1)
def reflexes() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(CHEMIN_REFLEXES.read_text(encoding="utf-8"))
    return data


def geste(ident: str, long: bool = False) -> str:
    g = reflexes()["gestes"][ident]
    return str(g["long" if long else "court"])


def reflexes_de_base() -> list[str]:
    """Les 5 réflexes embarqués dans le raccourci iPhone (affichés si le Mac ne répond pas)."""
    return [geste(i, long=True) for i in reflexes()["base"]]


def gestes(verdict: Verdict) -> list[str]:
    """Les identifiants des gestes à conseiller, du plus urgent au moins urgent."""
    if verdict.niveau == Niveau.AUCUN_SIGNE:
        return []
    locale = verdict.locale
    codes = {s.code for s in locale.signaux}
    canal = locale.message.canal
    choix: list[str] = []
    if verdict.niveau == Niveau.PRUDENCE:
        choix += ["pas_de_clic", "verifier_soi_meme"]
    else:
        if locale.famille == "proche":
            choix.append("appeler_proche")
        if locale.famille == "sextorsion":
            choix.append("ne_pas_payer")
        choix.append("pas_de_clic")
        if "demande:code" in codes or "demande:validation" in codes:
            choix.append("pas_de_code")
        if locale.famille == "banque" or "telephone:appel" in codes or "telephone:surtaxe" in codes:
            choix.append("rappeler_banque")
        choix.append("signaler_mail" if canal == "mail" else "signaler_sms")
        choix.append("supprimer")
    return choix


def a_demande_de_l_argent(verdict: Verdict) -> bool:
    codes = {s.code for s in verdict.locale.signaux}
    argent = ("demande:paiement", "demande:carte", "demande:rib", "demande:code", "demande:validation",
              "demande:virement", "demande:coupons", "demande:coursier")  # fmt: skip
    return verdict.niveau.value >= Niveau.TRES_SUSPECT.value and any(c in codes for c in argent)


def titre(verdict: Verdict) -> str:
    base = f"{verdict.niveau.pastille} {TITRES[verdict.niveau]}"
    if verdict.niveau.value < Niveau.TRES_SUSPECT.value:
        return base
    marque = verdict.locale.marque
    if marque is not None:
        return f"{base} — faux message « {marque.nom} »"
    if verdict.locale.famille in _NOMS_FAMILLES:
        return f"{base} — {_NOMS_FAMILLES[verdict.locale.famille]}"
    return base


@dataclass
class Reponse:
    titre: str
    raisons: list[str]
    gestes: list[str]
    complement: list[str]

    def texte(self) -> str:
        lignes = [self.titre, *(f"• {r}" for r in self.raisons)]
        if self.gestes:
            lignes.append("👉 " + " ".join(self.gestes))
        lignes += self.complement
        return "\n".join(lignes)

    def notification(self) -> tuple[str, str]:
        """(titre, texte) : le verdict, la première raison et le premier geste."""
        corps = " ".join(
            p for p in (self.raisons[0] if self.raisons else "", self.gestes[0] if self.gestes else "") if p
        )
        return self.titre, corps


def construire(verdict: Verdict) -> Reponse:
    raisons = list(verdict.raisons)
    if verdict.niveau == Niveau.AUCUN_SIGNE and not raisons:
        raisons = ["Je n'ai trouvé aucun des signes habituels d'arnaque."]
    complement: list[str] = []
    if verdict.niveau == Niveau.AUCUN_SIGNE:
        complement.append(AUTRE_CANAL)
    if a_demande_de_l_argent(verdict):
        complement.append(geste("deja_paye"))
    for avertissement in verdict.locale.message.avertissements:
        complement.append(f"(Attention : {avertissement}.)")
    if verdict.ia is not None and verdict.ia.etat == "pause_budget":
        complement.append(PAUSE_BUDGET)
    return Reponse(titre(verdict), raisons[:3], [geste(g) for g in gestes(verdict)], complement)
