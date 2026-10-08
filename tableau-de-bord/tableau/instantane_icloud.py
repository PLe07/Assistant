"""L'instantané pour l'iPhone : `iCloud Drive/Tableau/Etat.html` (§5.3).

Écrit toutes les 15 minutes, et dès qu'une pastille, un compteur ou les crédits changent. Une page autonome, lisible
dans Fichiers sur l'iPhone, sans lien ni ressource. Elle contient **seulement les états, les compteurs et les
crédits** : ni phrase venue d'un module, ni contenu de journal, ni chemin, ni jeton. Avant chaque écriture, une
recherche de motifs (e-mail, `/Users/`, jeton, clé, IBAN…) bloque l'écriture si elle trouve quoi que ce soit.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tableau import caviardage, textes
from tableau.module import EMOJI, LIBELLE, ORDRE, EtatModule, Pastille

NOM = "Etat.html"
INTERVALLE_S = 900


@dataclass
class Resultat:
    ecrit: bool
    motif: str = ""
    chemin: Path | None = None


def donnees(etats: list[EtatModule], credits: dict[str, Any]) -> dict[str, Any]:
    """Ce qui a le droit d'aller sur l'iPhone, et rien d'autre."""
    modules = []
    for e in sorted(etats, key=lambda x: (ORDRE[x.pastille], x.nom.lower())):
        modules.append({
            "nom": e.nom, "emoji": e.emoji, "pastille": str(e.pastille), "problemes": len(e.problemes),
            "erreurs_24h": e.erreurs_24h, "file": sum(int(f.get("n") or 0) for f in e.files) if e.files else None,
            "credits_mois": e.credits_mois, "plafond_usd": e.plafond_usd,
        })  # fmt: skip
    return {
        "modules": modules,
        "total_usd": credits.get("total_usd"),
        "plafonds_usd": credits.get("plafonds_usd"),
        "projection_usd": credits.get("projection_usd"),
    }


def signature(d: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _e(x: Any) -> str:
    return html.escape(str(x), quote=True)


STYLE = (
    ":root{--fond:#f6f6f4;--carte:#fff;--texte:#1c1c1e;--doux:#55555b;--trait:#d6d6da}"
    "@media (prefers-color-scheme: dark){:root{--fond:#161618;--carte:#242427;--texte:#f2f2f5;--doux:#c4c4ca;"
    "--trait:#3d3d42}}body{margin:0;background:var(--fond);color:var(--texte);"
    "font:17px/1.45 -apple-system,BlinkMacSystemFont,sans-serif}main{max-width:640px;margin:0 auto;padding:16px}"
    "h1{font-size:1.35rem;margin:.25rem 0}p{margin:.25rem 0}.doux{color:var(--doux);font-size:.9rem}"
    "ul{list-style:none;padding:0;margin:12px 0}li{background:var(--carte);border:1px solid var(--trait);"
    "border-radius:12px;padding:10px 12px;margin:8px 0}.nom{font-weight:600}.chiffres{color:var(--doux);"
    "font-size:.9rem}"
)


def page(d: dict[str, Any], maintenant: float) -> str:
    a_regarder = sum(max(1, m["problemes"]) for m in d["modules"] if m["pastille"] in ("rouge", "jaune"))
    titre = "✅ Tout va bien" if a_regarder == 0 else f"{textes.pluriel(a_regarder, 'chose')} à regarder"
    lignes = []
    for m in d["modules"]:
        p = Pastille(m["pastille"])
        chiffres = []
        if m["erreurs_24h"] is not None:
            chiffres.append(f"{m['erreurs_24h']} erreur{'s' if m['erreurs_24h'] > 1 else ''} sur 24 h")
        if m["file"]:
            chiffres.append(f"{textes.pluriel(m['file'], 'document')} en attente")
        if m["credits_mois"] is not None:
            chiffres.append(
                textes.dollars(m["credits_mois"])
                + (f" sur {textes.dollars(m['plafond_usd'])}" if m["plafond_usd"] else "")
                + " ce mois-ci"
            )
        lignes.append(
            f"<li><span class='nom'>{_e(m['emoji'])} {_e(m['nom'])}</span> · {EMOJI[p]} {_e(LIBELLE[p])}"
            + (f"<br><span class='chiffres'>{_e(' · '.join(chiffres))}</span>" if chiffres else "")
            + "</li>"
        )
    projection = d["projection_usd"]
    credits = f"Crédits Claude ce mois-ci : {textes.dollars(d['total_usd'])}" + (
        f" sur {textes.dollars(d['plafonds_usd'])}" if d["plafonds_usd"] else ""
    )
    if projection is not None:
        credits += f" · projection {textes.dollars(projection)}"
    quand = time.strftime("%d/%m à ", time.localtime(maintenant)) + textes.heure(maintenant)
    return (
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'><meta name='color-scheme' "
        f"content='light dark'><title>Tableau de bord</title><style>{STYLE}</style></head><body><main>"
        f"<h1>{_e(titre)}</h1><p class='doux'>Instantané du {_e(quand)}</p><ul>{''.join(lignes)}</ul>"
        f"<p>{_e(credits)}</p><p class='doux'>Le détail est sur le Mac : tableau ouvrir.</p></main></body></html>\n"
    )


class Instantane:
    def __init__(self, dossier: Path, jeton: str = "") -> None:
        self.dossier = dossier
        self.jeton = jeton
        self._signature: str | None = None
        self._ecrit_le = 0.0

    def ecrire_si_utile(
        self, etats: list[EtatModule], credits: dict[str, Any], maintenant: float, forcer: bool = False
    ) -> Resultat:
        d = donnees(etats, credits)
        sig = signature(d)
        if not forcer and sig == self._signature and maintenant - self._ecrit_le < INTERVALLE_S:
            return Resultat(False, "rien de neuf")
        texte = page(d, maintenant)
        sensibles = caviardage.contient_sensible(texte, (self.jeton,) if self.jeton else ())
        if sensibles:
            return Resultat(False, f"bloqué : {', '.join(sensibles)}")
        if not self.dossier.parent.is_dir():
            return Resultat(False, "iCloud Drive introuvable sur ce Mac")
        try:
            self.dossier.mkdir(exist_ok=True)
            cible = self.dossier / NOM
            temporaire = self.dossier / f".{NOM}.tmp"
            descripteur = os.open(temporaire, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descripteur, "w", encoding="utf-8") as f:
                f.write(texte)
            temporaire.replace(cible)
        except OSError as e:
            return Resultat(False, f"écriture impossible ({e.__class__.__name__})")
        self._signature = sig
        self._ecrit_le = maintenant
        return Resultat(True, "", cible)
