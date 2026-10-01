"""Le cerveau : Claude via ton abonnement (Claude Code en mode non interactif, `claude -p`).

Garde-fous intégrés :
- plafond d'appels par jour (reglages.json → claude.appels_max_par_jour) ;
- pause de 15 min après une panne ou un quota atteint (on ne s'acharne pas) ;
- un nouvel essai automatique après une erreur passagère ;
- notre prompt court remplace celui de Claude Code, aucun outil sauf demande explicite.
"""

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from core import config, etat
from core.journal import journal

# Sans consigne, Claude Code enverrait ses propres instructions (des milliers de tokens).
SYSTEME_PAR_DEFAUT = "Tu es l'assistant personnel de l'utilisateur. Réponds en français, de façon brève et directe."

PAUSE_APRES_PANNE = 15 * 60
DELAI_SECONDES = 180
ESSAIS = 2

log = journal("cerveau")


class ClaudeIndisponible(Exception):
    """Panne passagère, jeton refusé ou quota : on réessaiera plus tard."""


class PlafondAtteint(ClaudeIndisponible):
    """Le plafond d'appels du jour (reglages.json) est atteint."""


@dataclass
class Reponse:
    texte: str
    donnees: dict | None  # le JSON, si un schéma était demandé
    tokens_entree: int
    tokens_sortie: int


def binaire_claude() -> str:
    chemin = os.getenv("CLAUDE_BIN") or shutil.which("claude") or str(Path.home() / ".local" / "bin" / "claude")
    if not Path(chemin).exists():
        raise ClaudeIndisponible("Claude Code est introuvable (curl -fsSL https://claude.ai/install.sh | bash).")
    return chemin


def _expliquer(texte: str) -> tuple[str, bool]:
    """(message clair, faut-il faire une pause de 15 min ?)"""
    bas = texte.lower()
    if "401" in bas or "authenticat" in bas or "bearer" in bas:
        return "Jeton Claude refusé (expiré ou révoqué) : lance  python assistant.py renouveler-jeton", True
    if "limit" in bas or "quota" in bas or "429" in bas:
        return "Quota de l'abonnement atteint : nouvel essai dans 15 min.", True
    return f"Claude Code a renvoyé une erreur : {texte.strip()[:300]}", False


def _nom_modele(modele: str, reglages: dict) -> str:
    if modele == "rapide":
        return reglages["claude"]["modele_rapide"]
    if modele == "fort":
        return reglages["claude"]["modele_fort"]
    return modele


def _un_appel(commande: list[str], message: str, env: dict) -> dict:
    try:
        proc = subprocess.run(commande, input=message, capture_output=True, text=True,
                              timeout=DELAI_SECONDES, env=env, cwd=config.DONNEES)
    except subprocess.TimeoutExpired:
        raise ClaudeIndisponible(f"Claude n'a pas répondu en {DELAI_SECONDES} s.")
    except OSError as e:
        raise ClaudeIndisponible(f"Impossible de lancer Claude Code : {e}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict) or data.get("is_error") or proc.returncode != 0:
        brut = str(data.get("result", "")) if isinstance(data, dict) else (proc.stderr or proc.stdout)
        message_erreur, pause = _expliquer(brut or f"code {proc.returncode}")
        erreur = ClaudeIndisponible(message_erreur)
        erreur.pause = pause
        raise erreur
    return data


def _extraire_json(data: dict) -> dict | None:
    sortie = data.get("structured_output")
    if isinstance(sortie, dict):
        return sortie
    texte = str(data.get("result", ""))
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut == -1 or fin <= debut:
        return None
    try:
        return json.loads(texte[debut : fin + 1])
    except json.JSONDecodeError:
        return None


def demander(
    message: str,
    *,
    module: str = "assistant",
    systeme: str | None = None,
    schema: dict | None = None,
    modele: str = "fort",
    outils: list[str] | None = None,
    effort: str = "low",
) -> Reponse:
    """Pose une question à Claude. modele = "rapide", "fort" ou un nom précis."""
    reglages = config.charger()
    nom_modele = _nom_modele(modele, reglages)

    pause = etat.lire("claude_pause_jusqua")
    if pause and time.time() < float(pause):
        raise ClaudeIndisponible("Claude en pause après une panne : nouvel essai plus tard.")
    plafond = reglages["claude"]["appels_max_par_jour"]
    if etat.appels_aujourdhui()[0] >= plafond:
        raise PlafondAtteint(f"Plafond de {plafond} appels à Claude atteint pour aujourd'hui.")

    jeton = os.getenv("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    if not jeton:
        raise ClaudeIndisponible("Jeton Claude absent du .env de l'assistant.")
    # Sans clé API dans l'environnement : Claude Code utilise forcément l'abonnement.
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    env["CLAUDE_CODE_OAUTH_TOKEN"] = jeton

    commande = [binaire_claude(), "-p", "--model", nom_modele, "--effort", effort,
                "--output-format", "json", "--no-session-persistence", "--safe-mode", "--strict-mcp-config"]
    commande += ["--system-prompt", systeme or SYSTEME_PAR_DEFAUT]
    if schema:
        commande += ["--json-schema", json.dumps(schema)]
    commande += ["--tools", ",".join(outils or [])]  # en dernier : --tools accepte une liste

    config.DONNEES.mkdir(exist_ok=True)
    for essai in range(1, ESSAIS + 1):
        try:
            data = _un_appel(commande, message, env)
            break
        except ClaudeIndisponible as e:
            etat.noter_appel(module, nom_modele, False, erreur=str(e))
            if getattr(e, "pause", False) or essai == ESSAIS:
                if getattr(e, "pause", False):
                    etat.ecrire("claude_pause_jusqua", time.time() + PAUSE_APRES_PANNE)
                log.warning("[%s] %s", module, e)
                raise
            log.info("[%s] %s Nouvel essai dans 10 s.", module, e)
            time.sleep(10)

    usage = data.get("usage") or {}
    entree = sum(int(usage.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    sortie = int(usage.get("output_tokens") or 0)
    etat.noter_appel(module, nom_modele, True, entree, sortie)
    return Reponse(str(data.get("result", "")), _extraire_json(data) if schema else None, entree, sortie)
