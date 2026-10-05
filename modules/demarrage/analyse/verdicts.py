"""Les verdicts, par règles locales (sans IA). L'ordre des règles est dans la config (verdicts.ordre) : la
première qui s'applique l'emporte. Chaque règle est une fonction testée seule.

🍎 Apple, ne pas toucher · ✅ Utile, à garder · 💤 Inutile au démarrage · 👻 Orphelin · ⚠️ Inconnu, à vérifier

L'action proposée dépend de la source (D-23) ; un élément 🍎 n'en a jamais, un élément ⚠️ n'a que « vérifier » :
on ne conseille jamais de supprimer ce qu'on ne connaît pas.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from modules.demarrage.analyse.connaissances import Connaissance
from modules.demarrage.analyse.scores import Metriques, empeche_la_veille, en_boucle
from modules.demarrage.modele import SOURCES_GLOBALES, Fiche

EMOJIS = {"apple": "🍎", "utile": "✅", "inutile": "💤", "orphelin": "👻", "inconnu": "⚠️"}
TITRES = {
    "apple": "Apple, ne pas toucher",
    "utile": "Utile, à garder",
    "inutile": "Inutile au démarrage",
    "orphelin": "Orphelin (reste d'une app désinstallée)",
    "inconnu": "Inconnu, à vérifier",
}
SIGNATURES_CONNUES = ("apple", "developpeur", "app_store")


@dataclass
class Contexte:
    """Tout ce qu'une règle peut regarder."""

    fiche: Fiche
    metriques: Metriques
    impact: float
    utilite: str  # indispensable, forte, faible, inconnue
    raison_utilite: str
    connaissance: Connaissance | None
    reglages: dict[str, Any]


@dataclass
class Verdict:
    code: str  # apple, utile, inutile, orphelin, inconnu
    raison: str
    action: str  # aucune, desactiver, quarantaine, reglages, instructions, verifier
    regle: str = ""

    @property
    def emoji(self) -> str:
        return EMOJIS[self.code]

    @property
    def titre(self) -> str:
        return TITRES[self.code]


def action_pour(f: Fiche, code: str) -> str:
    """Le moyen d'agir sur cet élément, selon d'où il vient (D-23)."""
    if code == "apple" or f.c_est_moi:
        return "aucune"
    if code == "inconnu":
        return "verifier"
    if f.actif is False and code != "orphelin":
        return "aucune"  # déjà inactif : rien à faire
    if f.source == "ouverture":
        return "reglages"
    if f.source in SOURCES_GLOBALES or f.source == "cron":
        return "instructions"
    if code == "orphelin" and f.source == "agent_utilisateur":
        return "quarantaine"
    return "desactiver"


def _verdict(ctx: Contexte, code: str, raison: str) -> Verdict:
    return Verdict(code, raison, action_pour(ctx.fiche, code))


def editeur_connu(ctx: Contexte) -> bool:
    f = ctx.fiche
    if f.source == "extension":
        return bool(f.equipe)  # macOS n'active une extension que signée et notarisée
    if f.signature in SIGNATURES_CONNUES:
        return not f.details.get("programme_systeme") or ctx.connaissance is not None
    # Signature ad hoc ou absente : connue seulement si la base de connaissances nomme l'éditeur (Homebrew…).
    return ctx.connaissance is not None and ctx.connaissance.editeur is not None


# --- les règles -------------------------------------------------------------------------------------------------


def regle_apple(ctx: Contexte) -> Verdict | None:
    f = ctx.fiche
    sous_system = any(str(c or "").startswith("/System/") for c in (f.chemin_plist, f.programme))
    if (f.est_apple or sous_system) and not f.details.get("se_dit_apple"):
        return _verdict(ctx, "apple", "fait partie de macOS")
    return None


def regle_moi(ctx: Contexte) -> Verdict | None:
    if ctx.fiche.c_est_moi:
        return _verdict(ctx, "utile", "c'est moi : l'Assistant, qui fait tourner ce Nettoyeur")
    return None


def regle_orphelin(ctx: Contexte) -> Verdict | None:
    f = ctx.fiche
    if f.programme_existe is False and f.details.get("absent_certain"):
        if f.details.get("app_deplacee_vers"):
            return _verdict(ctx, "orphelin", f"l'app a été déplacée vers {f.details['app_deplacee_vers']} : "
                                             "ce lancement pointe encore vers l'ancien endroit")  # fmt: skip
        return _verdict(ctx, "orphelin", f"le programme {f.programme} n'existe plus")
    if f.app_attendue_absente and f.signature in SIGNATURES_CONNUES:
        return _verdict(ctx, "orphelin", "l'app à laquelle il appartient a été désinstallée")
    if f.details.get("sans_plist") and f.signature in SIGNATURES_CONNUES:
        return _verdict(ctx, "orphelin", "plus rien ne le lance : reste probable d'une app désinstallée")
    return None


def regle_inconnu(ctx: Contexte) -> Verdict | None:
    f = ctx.fiche
    if f.erreurs and not f.programme:
        return _verdict(ctx, "inconnu", f"fichier de lancement illisible ({f.erreurs[0]}) : launchd ne peut pas "
                                        "s'en servir, il ne lance rien ; reste à savoir d'où il vient")  # fmt: skip
    if f.details.get("se_dit_apple"):
        return _verdict(ctx, "inconnu", "porte un nom d'Apple (com.apple…) sans être signé par Apple")
    if f.programme is None and f.source not in ("extension",):
        return _verdict(ctx, "inconnu", "ne dit pas quel programme il lance")
    if f.programme_existe is False:
        return _verdict(ctx, "inconnu", "programme introuvable, mais son dossier n'est pas lisible : on ne conclut pas")
    if not editeur_connu(ctx):
        if f.details.get("programme_systeme"):
            raison = "lance un programme de macOS depuis une fiche dont on ne connaît pas l'auteur"
        elif f.signature == "non_signe":
            raison = "programme non signé : éditeur inconnu"
        elif f.signature == "invalide":
            raison = "signature invalide (programme modifié après sa signature ?)"
        elif f.signature == "adhoc":
            raison = "signature « ad hoc » : pas d'éditeur identifié"
        else:
            raison = "éditeur inconnu"
        return _verdict(ctx, "inconnu", raison)
    return None


def regle_inactif(ctx: Contexte) -> Verdict | None:
    f = ctx.fiche
    if f.actif is False:
        raison = "déjà désactivé" if f.desactive else "déclaré par son app mais pas activé : il ne se lance pas"
        return _verdict(ctx, "utile", raison)
    return None


def est_mise_a_jour(ctx: Contexte) -> bool:
    if ctx.connaissance is not None:
        return ctx.connaissance.mise_a_jour
    motifs = ctx.reglages["verdicts"]["motifs_mise_a_jour"]
    texte = f"{ctx.fiche.label} {ctx.fiche.programme or ''}".casefold()
    return any(re.search(re.escape(m.casefold()), texte) for m in motifs)


def regle_mise_a_jour(ctx: Contexte) -> Verdict | None:
    if est_mise_a_jour(ctx):
        return _verdict(ctx, "inutile", "simple outil de mise à jour : il peut tourner quand tu ouvres l'app")
    return None


def regle_pas_au_demarrage(ctx: Contexte) -> Verdict | None:
    """La base de connaissances dit « rien ne l'oblige à démarrer tout seul » (Spotify, Steam, Notion…) : 💤 même si
    l'app sert souvent, car on l'ouvre quand on en a besoin. Avant (D-45), une app ouverte à chaque connexion paraissait
    « utilisée hier » justement parce qu'elle s'ouvre toute seule, et restait ✅ en coûtant 1 Go."""
    c = ctx.connaissance
    if c is not None and c.recommandation == "desactiver" and ctx.utilite != "indispensable":
        return _verdict(ctx, "inutile", f"rien ne l'oblige à démarrer tout seul : {c.effet}")
    return None


def regle_lourd_inutile(ctx: Contexte) -> Verdict | None:
    seuil = ctx.reglages["verdicts"]["impact_significatif"]
    if ctx.impact >= seuil and ctx.utilite == "faible":
        return _verdict(ctx, "inutile", f"il coûte (impact {ctx.impact:.0f}/100) et sert peu : {ctx.raison_utilite}")
    return None


def regle_utile(ctx: Contexte) -> Verdict | None:
    negligeable = ctx.impact < ctx.reglages["verdicts"]["impact_negligeable"]
    if negligeable:
        return _verdict(ctx, "utile", "impact négligeable")
    if ctx.utilite in ("forte", "indispensable"):
        return _verdict(ctx, "utile", f"utile : {ctx.raison_utilite}")
    return _verdict(ctx, "utile", f"impact {ctx.impact:.0f}/100, usage inconnu : à toi de voir s'il te sert")


REGLES: dict[str, Callable[[Contexte], Verdict | None]] = {
    "apple": regle_apple,
    "moi": regle_moi,
    "orphelin": regle_orphelin,
    "inconnu": regle_inconnu,
    "inactif": regle_inactif,
    "mise_a_jour": regle_mise_a_jour,
    "pas_au_demarrage": regle_pas_au_demarrage,
    "lourd_inutile": regle_lourd_inutile,
    "utile": regle_utile,
}


def juger(ctx: Contexte) -> Verdict:
    for nom in ctx.reglages["verdicts"]["ordre"]:
        regle = REGLES.get(nom)
        verdict = regle(ctx) if regle else None
        if verdict is not None:
            verdict.regle = nom
            if verdict.code == "apple":
                verdict.action = "aucune"  # jamais, sous aucun prétexte
            if verdict.code == "inconnu":
                verdict.action = "verifier"  # jamais « supprimer »
            return verdict
    return Verdict("utile", "aucune règle ne s'applique", action_pour(ctx.fiche, "utile"), "défaut")


def drapeaux(ctx: Contexte) -> list[str]:
    """Les mentions affichées sur la fiche, en plus du verdict."""
    d = []
    if empeche_la_veille(ctx.metriques, ctx.reglages):
        d.append("empêche la veille")
    if en_boucle(ctx.fiche, ctx.reglages):
        d.append("relancé en boucle (il plante)")
    if ctx.fiche.doublon:
        d.append("label en double")
    if ctx.fiche.c_est_moi:
        d.append("c'est moi")
    return d
