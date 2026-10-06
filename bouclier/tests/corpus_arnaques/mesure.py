"""Mesure du détecteur sur un corpus (§11.1) : tableau des niveaux et liste des erreurs.

python -m tests.corpus_arnaques.mesure [principal|inedit] [-v]
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass, field

from bouclier.arnaque.detecteur import AnalyseLocale, Contexte, analyser
from bouclier.arnaque.extraction import depuis_eml, depuis_texte
from bouclier.arnaque.signaux import Niveau
from tests.corpus_arnaques import generer
from tests.corpus_arnaques.generer import Echantillon


def contexte_imite(corpus: list[Echantillon]) -> Contexte:
    dates, flux = generer.contexte(corpus)
    normalises = {u.rstrip("/").lower() for u in flux}

    def rdap(domaine: str):  # type: ignore[no-untyped-def]
        return dates.get(domaine)

    def dans_flux(url: str) -> str | None:
        return "OpenPhish" if url.rstrip("/").lower() in normalises else None

    return Contexte(rdap=rdap, flux=dans_flux, comptes=lambda: set(generer.INVENTAIRE),
                    aujourd_hui=generer.MAINTENANT.date())  # fmt: skip


def analyser_echantillon(e: Echantillon, ctx: Contexte) -> AnalyseLocale:
    message = depuis_eml(e.brut) if e.canal == "mail" else depuis_texte(e.brut.decode("utf-8"), "sms")
    return analyser(message, ctx)


@dataclass
class Resultats:
    arnaques: Counter[Niveau] = field(default_factory=Counter)
    legitimes: Counter[Niveau] = field(default_factory=Counter)
    injections: Counter[Niveau] = field(default_factory=Counter)
    erreurs: list[tuple[str, str, int, list[str]]] = field(default_factory=list)
    analyses: dict[str, AnalyseLocale] = field(default_factory=dict)

    @property
    def n_arnaques(self) -> int:
        return sum(self.arnaques.values())

    @property
    def n_legitimes(self) -> int:
        return sum(self.legitimes.values())

    def taux_arnaques_detectees(self) -> float:
        bons = self.arnaques[Niveau.ARNAQUE] + self.arnaques[Niveau.TRES_SUSPECT]
        return 100 * bons / max(1, self.n_arnaques)

    def taux_arnaques_blanches(self) -> float:
        return 100 * self.arnaques[Niveau.AUCUN_SIGNE] / max(1, self.n_arnaques)

    def taux_legitimes(self, niveau: Niveau) -> float:
        return 100 * self.legitimes[niveau] / max(1, self.n_legitimes)

    def tableau(self, nom: str) -> str:
        lignes = [f"Corpus {nom} : {self.n_arnaques} arnaques (dont {sum(self.injections.values())} injections),"
                  f" {self.n_legitimes} légitimes"]  # fmt: skip
        lignes.append("| | 🔴 | 🟠 | 🟡 | ⚪ |")
        lignes.append("|---|---|---|---|---|")
        for titre, compte in (("Arnaques", self.arnaques), ("Légitimes", self.legitimes)):
            cellules = " | ".join(str(compte[n]) for n in (Niveau.ARNAQUE, Niveau.TRES_SUSPECT, Niveau.PRUDENCE,
                                                           Niveau.AUCUN_SIGNE))  # fmt: skip
            lignes.append(f"| {titre} | {cellules} |")
        lignes.append(f"Arnaques 🟠/🔴 : {self.taux_arnaques_detectees():.1f} % · arnaques ⚪ : {self.taux_arnaques_blanches():.1f} %"
                      f" · légitimes 🔴 : {self.taux_legitimes(Niveau.ARNAQUE):.1f} %"
                      f" · légitimes 🟠 : {self.taux_legitimes(Niveau.TRES_SUSPECT):.1f} %")  # fmt: skip
        return "\n".join(lignes)


def mesurer(corpus: list[Echantillon]) -> Resultats:
    ctx = contexte_imite(corpus)
    r = Resultats()
    for e in corpus:
        a = analyser_echantillon(e, ctx)
        r.analyses[e.id] = a
        if e.verite == "arnaque":
            r.arnaques[a.niveau] += 1
            if e.injection:
                r.injections[a.niveau] += 1
            if a.niveau.value < Niveau.TRES_SUSPECT.value:
                r.erreurs.append((e.id, a.niveau.pastille, a.score, [f"{s.code}({s.poids})" for s in a.signaux]))
        else:
            r.legitimes[a.niveau] += 1
            if a.niveau.value >= Niveau.TRES_SUSPECT.value:
                r.erreurs.append((e.id, a.niveau.pastille, a.score, [f"{s.code}({s.poids})" for s in a.signaux]))
    return r


if __name__ == "__main__":
    nom = sys.argv[1] if len(sys.argv) > 1 else "principal"
    corpus = generer.corpus_principal() if nom == "principal" else generer.corpus_inedit()
    res = mesurer(corpus)
    print(res.tableau(nom))
    for ident, pastille, score, signaux in res.erreurs:
        print(f"  {pastille} {ident} ({score}) {' '.join(signaux)}")
    if "-v" in sys.argv:
        for e in corpus:
            a = res.analyses[e.id]
            print(f"{a.niveau.pastille} {e.id:14} {a.score:3} {' '.join(f'{s.code}({s.poids})' for s in a.signaux)}")
