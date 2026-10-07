"""L'IA de Quotidien : seulement quand le local ne suffit pas (photo du frigo, message d'anniversaire, envie libre).

- Deux façons d'appeler Claude : le SDK officiel avec ta clé (variable `ANTHROPIC_API_KEY`, ou élément de trousseau
  `quotidien-anthropic` : launchd n'hérite pas du shell), sinon Claude Code (`claude -p`) avec ton abonnement
  (élément de trousseau `quotidien-claude`), comme Bouclier.
- Modèle économique par défaut : `claude-haiku-4-5` (1 $ / 5 $ par million de jetons), réglable.
- **Plafond : 2 $ par mois pour tout le pack.** Chaque appel est estimé avant (on n'appelle pas si l'estimation
  dépasse) et compté après. Au-delà : repli local jusqu'au mois suivant.
- Erreurs passagères (429, 529, 5xx, réseau, délai) : nouvel essai après 2 s, puis 4 s, puis 8 s (ou le délai demandé
  par l'API). JSON invalide : un seul nouvel essai. Toujours un repli local derrière.
- Les réponses sont des JSON validés par un schéma (pydantic) ; tout le reste est refusé.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeVar, cast

from pydantic import BaseModel, ValidationError

from quotidien import config
from quotidien.db import Base
from quotidien.journal import log

DELAIS_NOUVEL_ESSAI = (2.0, 4.0, 8.0)
JETONS_PAR_IMAGE = 1600  # estimation haute pour une image de 1 024 px de côté

Modele = TypeVar("Modele", bound=BaseModel)
Contenu = str | list[dict[str, Any]]


@dataclass
class ReponseBrute:
    texte: str
    jetons_entree: int
    jetons_sortie: int
    cout_usd: float | None = None  # annoncé par Claude Code ; sinon calculé au prix de la config


class ErreurPassagere(Exception):
    def __init__(self, message: str, attendre: float | None = None) -> None:
        super().__init__(message)
        self.attendre = attendre


class ErreurDefinitive(Exception):
    pass


class Client(Protocol):
    nom: str

    def envoyer(self, systeme: str, contenu: Contenu, max_jetons: int, delai: float) -> ReponseBrute: ...


def _retry_after(reponse: Any) -> float | None:
    try:
        return min(30.0, float(reponse.headers.get("retry-after")))
    except (AttributeError, TypeError, ValueError):
        return None


class ClientSDK:
    """Le SDK officiel `anthropic`, avec ta clé."""

    nom = "clé API"

    def __init__(self, cle: str, modele: str, fabrique: Callable[..., Any] | None = None) -> None:
        self.cle, self.modele, self.fabrique = cle, modele, fabrique

    def envoyer(self, systeme: str, contenu: Contenu, max_jetons: int, delai: float) -> ReponseBrute:
        import anthropic

        fabrique = self.fabrique or anthropic.Anthropic
        client = fabrique(api_key=self.cle, max_retries=0, timeout=delai)
        try:
            r = client.messages.create(
                model=self.modele,
                max_tokens=max_jetons,
                system=systeme,
                messages=[{"role": "user", "content": cast(Any, contenu)}],
            )
        except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
            raise ErreurPassagere(f"Claude injoignable ({e.__class__.__name__})") from e
        except anthropic.APIStatusError as e:
            if e.status_code in (408, 409, 429) or e.status_code >= 500:
                raise ErreurPassagere(f"Claude surchargé (code {e.status_code})", _retry_after(e.response)) from e
            raise ErreurDefinitive(f"Claude refuse la demande (code {e.status_code})") from e
        if getattr(r, "stop_reason", None) == "refusal":
            raise ErreurDefinitive("Claude a décliné la demande")
        texte = "".join(getattr(b, "text", "") for b in r.content if getattr(b, "type", "") == "text")
        return ReponseBrute(texte, int(r.usage.input_tokens), int(r.usage.output_tokens))


Executer = Callable[..., subprocess.CompletedProcess[str]]


class ClientClaudeCode:
    """Sans clé API : Claude Code (`claude -p`) avec le jeton de ton abonnement (trousseau `quotidien-claude`).

    Sans outil, sans session gardée, dans un dossier vide : il ne peut rien lire ni rien faire sur le Mac. Une image
    passe par l'entrée « stream-json » (bloc image en base64), comme avec le SDK."""

    nom = "abonnement Claude"

    def __init__(self, binaire: str, modele: str, jeton: str | None, executer: Executer = subprocess.run) -> None:
        self.binaire, self.modele, self.jeton, self.executer = binaire, modele, jeton, executer

    def commande(self, systeme: str, flux: bool) -> list[str]:
        commande = [self.binaire, "-p", "--model", self.modele, "--no-session-persistence", "--safe-mode",
                    "--strict-mcp-config", "--system-prompt", systeme, "--tools", ""]  # fmt: skip
        if flux:
            return [*commande, "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
        return [*commande, "--output-format", "json"]

    def envoyer(self, systeme: str, contenu: Contenu, max_jetons: int, delai: float) -> ReponseBrute:
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        if self.jeton:
            env["CLAUDE_CODE_OAUTH_TOKEN"] = self.jeton
        flux = not isinstance(contenu, str)
        entree = (
            json.dumps({"type": "user", "message": {"role": "user", "content": contenu}}) + "\n"
            if flux
            else str(contenu)
        )
        with tempfile.TemporaryDirectory(prefix="quotidien-ia-") as vide:
            try:
                proc = self.executer(self.commande(systeme, flux), input=entree, capture_output=True, text=True,
                                     timeout=delai, env=env, cwd=vide)  # fmt: skip
            except subprocess.TimeoutExpired as e:
                raise ErreurPassagere(f"Claude n'a pas répondu en {delai:.0f} s") from e
            except OSError as e:
                raise ErreurDefinitive(f"Claude Code ne se lance pas : {e}") from e
        data: Any = None
        for ligne in reversed((proc.stdout or "").strip().splitlines()):
            try:
                candidat = json.loads(ligne)
            except json.JSONDecodeError:
                continue
            if isinstance(candidat, dict) and (not flux or candidat.get("type") == "result"):
                data = candidat
                break
        if not isinstance(data, dict) or data.get("is_error") or proc.returncode != 0:
            brut = str(data.get("result") or data.get("subtype") or "") if isinstance(data, dict) else proc.stderr
            bas = (brut or "").lower()
            if any(m in bas for m in ("429", "529", "overloaded", "rate limit", "limit reached", "timeout")):
                raise ErreurPassagere(f"Claude surchargé : {brut[:120]}")
            raise ErreurDefinitive(f"Claude Code a renvoyé une erreur : {(brut or f'code {proc.returncode}')[:200]}")
        usage = data.get("usage") or {}
        entree_jetons = sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                              "cache_read_input_tokens"))  # fmt: skip
        cout = data.get("total_cost_usd")
        return ReponseBrute(str(data.get("result", "")), entree_jetons, int(usage.get("output_tokens") or 0),
                            float(cout) if isinstance(cout, int | float) else None)  # fmt: skip


LireTrousseau = Callable[[str], str | None]


def trouver_claude() -> str:
    return shutil.which("claude") or str(config.maison() / ".local" / "bin" / "claude")


def choisir_client(
    reglages: dict[str, Any], lire_trousseau: LireTrousseau, binaire: str | None = None
) -> Client | None:
    """La clé API (environnement puis trousseau), sinon Claude Code. Rien : None (repli local)."""
    ia = reglages["ia"]
    if not ia.get("active", True):
        return None
    cle = os.environ.get("ANTHROPIC_API_KEY", "").strip() or (lire_trousseau("quotidien-anthropic") or "").strip()
    if cle:
        return ClientSDK(cle, str(ia["modele"]))
    binaire = binaire or trouver_claude()
    if not Path(binaire).exists():
        return None
    return ClientClaudeCode(binaire, str(ia["modele"]), lire_trousseau("quotidien-claude"))


# --- Budget --------------------------------------------------------------------------------------------------------


class Budget:
    def __init__(self, base: Base, reglages: dict[str, Any], horloge: Callable[[], float] = time.time) -> None:
        self.base, self.horloge = base, horloge
        ia = reglages["ia"]
        self.plafond = float(ia["budget_mensuel_usd"])
        self.prix_entree = float(ia["prix_entree_par_million"]) / 1e6
        self.prix_sortie = float(ia["prix_sortie_par_million"]) / 1e6

    def mois(self) -> str:
        return time.strftime("%Y-%m", time.localtime(self.horloge()))

    def depense_du_mois(self) -> float:
        ligne = self.base.cx.execute("SELECT COALESCE(SUM(cout_usd), 0) FROM depenses_ia WHERE mois = ?",
                                     (self.mois(),)).fetchone()  # fmt: skip
        return float(ligne[0])

    def reste(self) -> float:
        return max(0.0, self.plafond - self.depense_du_mois())

    def cout(self, jetons_entree: int, jetons_sortie: int) -> float:
        return jetons_entree * self.prix_entree + jetons_sortie * self.prix_sortie

    def estimation(self, systeme: str, contenu: Contenu, max_jetons: int) -> float:
        """Surestime toujours : 3 caractères par jeton pour le français, 1 600 jetons par image."""
        if isinstance(contenu, str):
            texte, images = contenu, 0
        else:
            texte = " ".join(str(b.get("text", "")) for b in contenu if b.get("type") == "text")
            images = sum(1 for b in contenu if b.get("type") == "image")
        return self.cout((len(systeme) + len(texte)) // 3 + 50 + images * JETONS_PAR_IMAGE, max_jetons)

    def permet(self, estimation: float) -> bool:
        return self.depense_du_mois() + estimation <= self.plafond

    def noter(self, r: ReponseBrute, usage: str) -> float:
        cout = r.cout_usd if r.cout_usd is not None else self.cout(r.jetons_entree, r.jetons_sortie)
        with self.base.transaction() as cx:
            cx.execute(
                "INSERT INTO depenses_ia(date, mois, cout_usd, jetons_entree, jetons_sortie, usage)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (self.horloge(), self.mois(), cout, r.jetons_entree, r.jetons_sortie, usage),
            )
        return cout


# --- Une demande, validée --------------------------------------------------------------------------------------------


@dataclass
class Resultat:
    """`valeur` : l'objet validé, ou None ; `statut` : ok, budget, indisponible, erreur, invalide, desactivee."""

    valeur: Any
    statut: str
    detail: str = ""
    cout_usd: float = 0.0


def extraire_json(texte: str) -> Any:
    """Le premier objet JSON du texte (Claude l'entoure parfois de ```json … ```)."""
    texte = texte.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", texte, re.DOTALL)
    if m:
        texte = m.group(1).strip()
    debut = texte.find("{")
    fin = texte.rfind("}")
    if debut < 0 or fin < debut:
        raise ValueError("aucun objet JSON")
    return json.loads(texte[debut : fin + 1])


def demander(
    base: Base,
    reglages: dict[str, Any],
    usage: str,
    systeme: str,
    contenu: Contenu,
    schema: type[Modele],
    *,
    max_jetons: int = 600,
    client: Client | None = None,
    lire_trousseau: LireTrousseau | None = None,
    horloge: Callable[[], float] = time.time,
    dormir: Callable[[float], None] = time.sleep,
) -> Resultat:
    """Une demande à Claude, dont la réponse doit valider `schema`. Ne lève jamais : le statut dit quoi faire."""
    if not reglages["ia"].get("active", True):
        return Resultat(None, "desactivee", "IA désactivée dans reglages.toml")
    if client is None:
        client = choisir_client(reglages, lire_trousseau or (lambda _s: None))
    if client is None:
        return Resultat(None, "indisponible", "ni clé API ni Claude Code sur ce Mac")
    budget = Budget(base, reglages, horloge)
    estimation = budget.estimation(systeme, contenu, max_jetons)
    if not budget.permet(estimation):
        return Resultat(None, "budget", f"plafond de {budget.plafond:.2f} $ atteint ce mois-ci")
    delai = float(reglages["ia"]["delai_s"])
    cout_total = 0.0
    essais_json = 0
    passageres = 0
    while True:
        try:
            brute = client.envoyer(systeme, contenu, max_jetons, delai)
        except ErreurPassagere as e:
            if passageres >= len(DELAIS_NOUVEL_ESSAI):
                log().warning("IA (%s) : %s, abandon après %d essais", usage, e, passageres + 1)
                return Resultat(None, "erreur", str(e), cout_total)
            attente = e.attendre if e.attendre is not None else DELAIS_NOUVEL_ESSAI[passageres]
            passageres += 1
            dormir(attente)
            continue
        except ErreurDefinitive as e:
            log().warning("IA (%s) : %s", usage, e)
            return Resultat(None, "erreur", str(e), cout_total)
        cout_total += budget.noter(brute, usage)
        try:
            valeur = schema.model_validate(extraire_json(brute.texte))
        except (ValueError, ValidationError) as e:
            essais_json += 1
            if essais_json >= 2 or not budget.permet(estimation):
                log().warning("IA (%s) : réponse invalide (%s)", usage, str(e)[:120])
                return Resultat(None, "invalide", str(e)[:200], cout_total)
            continue
        return Resultat(valeur, "ok", client.nom, cout_total)
