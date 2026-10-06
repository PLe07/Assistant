"""Le dernier mot (§3.3) : l'avis de l'IA ne peut jamais rendre un message « sûr », ni effacer un indice critique.

- L'IA peut **monter** le niveau sans limite (prudence de plus, jamais de risque de plus).
- Un indice local **critique** (sosie qui demande de payer, lien déjà signalé, demande de code…) tient le verdict à
  🟠 au moins, quoi que dise l'IA.
- Sans indice critique, l'IA ne peut **descendre** que d'un niveau, et seulement si elle est sûre d'elle
  (confiance ≥ 0,6) : un message que les règles locales trouvent très suspect reste au moins « Prudence ».
- Les phrases de l'IA sont filtrées : rien qui rassure (« c'est sûr », « sans danger »), aucun lien ni numéro (une
  IA manipulée pourrait en ajouter), aucun jargon. Elles complètent les raisons locales sans les remplacer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bouclier.arnaque.detecteur import AnalyseLocale
from bouclier.arnaque.ia import AvisIA, ResultatIA
from bouclier.arnaque.score import ramener
from bouclier.arnaque.signaux import Niveau

CONFIANCE_POUR_BAISSER = 0.6

_RASSURANT = re.compile(
    r"\b(sûr|sure|sur à|sans (aucun )?(danger|risque)|aucun (danger|risque)|fiable|légitime|legitime|authentique"
    r"|officiel et|en toute sécurité|tu peux (cliquer|répondre|payer|appeler|ouvrir)|rassur|100 ?%|pas une arnaque"
    r"|n'est pas une arnaque|safe|legit)",
    re.IGNORECASE,
)
_LIEN_OU_NUMERO = re.compile(r"https?://|www\.|\b[a-z0-9\-]+\.(fr|com|net|org|top|xyz|info)\b|(?:\d[\s.]?){6,}", re.I)
_JARGON = re.compile(
    r"\b(url|phishing|smishing|spoofing|dkim|spf|dmarc|punycode|tld|rdap|header|ip|json|malware|payload)\b",
    re.IGNORECASE,
)


def raisons_ia_acceptables(avis: AvisIA) -> list[str]:
    gardees = []
    for r in avis.raisons:
        r = " ".join(r.split())
        if _RASSURANT.search(r) or _LIEN_OU_NUMERO.search(r) or _JARGON.search(r) or len(r) > 200:
            continue
        gardees.append(r)
    return gardees


@dataclass
class Verdict:
    niveau: Niveau
    score: int
    locale: AnalyseLocale
    ia: ResultatIA | None = None
    raisons: list[str] = field(default_factory=list)
    veto: bool = False  # l'IA voulait descendre plus bas : les règles locales l'en ont empêchée

    @property
    def ia_consultee(self) -> bool:
        return self.ia is not None and self.ia.etat == "ok"


def plancher(locale: AnalyseLocale, avis: AvisIA) -> Niveau:
    """Le niveau sous lequel l'IA ne peut pas faire descendre le verdict."""
    if avis.confiance < CONFIANCE_POUR_BAISSER:
        return locale.niveau
    un_de_moins = max(0, locale.niveau.value - 1)
    if locale.critiques:
        return Niveau(max(Niveau.TRES_SUSPECT.value, un_de_moins))
    return Niveau(un_de_moins)


def combiner(locale: AnalyseLocale, resultat: ResultatIA | None) -> Verdict:
    raisons_locales = locale.raisons(3)
    if resultat is None or resultat.etat != "ok" or resultat.avis is None:
        return Verdict(locale.niveau, locale.score, locale, resultat, raisons_locales)
    avis = resultat.avis
    voulu = Niveau.depuis_code(avis.niveau)
    bas = plancher(locale, avis)
    niveau = voulu if voulu.value >= bas.value else bas
    veto = voulu.value < bas.value
    score = ramener(locale.score, niveau)
    # Les raisons : d'abord les indices locaux (vérifiables), puis celles de l'IA qui passent le filtre.
    raisons = list(raisons_locales)
    for r in raisons_ia_acceptables(avis):
        if len(raisons) >= 3:
            break
        if r not in raisons:
            raisons.append(r)
    if niveau.value > locale.niveau.value and len(raisons_locales) == 3:
        # L'IA a vu plus grave : sa première raison acceptable prend la dernière place.
        ia_ok = [r for r in raisons_ia_acceptables(avis) if r not in raisons_locales]
        if ia_ok:
            raisons = [*raisons_locales[:2], ia_ok[0]]
    return Verdict(niveau, score, locale, resultat, raisons[:3], veto)
