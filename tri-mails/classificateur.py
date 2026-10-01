"""Le cerveau : pré-tri gratuit, puis Claude (via l'abonnement, avec Claude Code).

Claude est appelé en mode non interactif (`claude -p`), sans aucun outil,
avec notre propre prompt à la place de celui de Claude Code (bien plus court),
et une réponse JSON imposée par un schéma.
"""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import config
from gmail_client import Mail


class ClaudeIndisponible(Exception):
    """Panne passagère (réseau, quota, jeton…) : on réessaiera au prochain passage."""


class ReponseInvalide(Exception):
    """Claude a répondu, mais pas dans le format attendu."""


@dataclass
class Classement:
    mail_id: str
    bac: str
    raison: str
    vaut_mon_temps: bool
    source: str  # "IA", "R1" ou "R2"


@dataclass
class Resultat:
    classements: dict = field(default_factory=dict)  # id du mail → Classement
    erreurs: list = field(default_factory=list)
    non_tentes: set = field(default_factory=set)  # pas envoyés à Claude (panne) : à retenter
    indisponible: bool = False
    appels: int = 0
    tokens_entree: int = 0
    tokens_sortie: int = 0


SCHEMA = {
    "type": "object",
    "properties": {
        "classements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "bac": {"type": "string", "enum": list(config.BACS)},
                    "raison": {"type": "string"},
                    "vaut_mon_temps": {"type": "boolean"},
                },
                "required": ["id", "bac", "raison", "vaut_mon_temps"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["classements"],
    "additionalProperties": False,
}

# --- Pré-tri gratuit ------------------------------------------------------------

_NO_REPLY = re.compile(
    r"no[-_.]?reply|do[-_.]?not[-_.]?reply|ne[-_.]?pas[-_.]?repondre|notification", re.I
)


def _regles_perso() -> str:
    if config.FICHIER_REGLES_PERSO.exists():
        return config.FICHIER_REGLES_PERSO.read_text(encoding="utf-8").strip()
    return ""


def _cite_dans_regles_perso(mail: Mail, regles: str) -> bool:
    """L'adresse, ou son domaine (sous-domaines compris), est-elle citée dans regles_perso.txt ?

    « u-bordeaux.fr » couvre aussi « iae.u-bordeaux.fr ». Un domaine qui n'apparaît
    que dans une adresse (« marie@gmail.com ») ne couvre pas tout gmail.com.
    """
    adresse = mail.expediteur_adresse
    if not adresse or not regles:
        return False
    texte = regles.lower()
    if re.search(rf"(?<![\w.+-]){re.escape(adresse)}(?![\w-])", texte):
        return True
    return any(re.search(rf"(?<![\w@.-]){re.escape(d)}(?![\w-])", texte) for d in _domaines(adresse))


def _domaines(adresse: str) -> list[str]:
    """« a@moodle.u-bordeaux.fr » → ["moodle.u-bordeaux.fr", "u-bordeaux.fr"] (jamais « fr » seul)."""
    morceaux = adresse.partition("@")[2].split(".")
    return [".".join(morceaux[i:]) for i in range(len(morceaux) - 1) if morceaux[i]]


# --- Expéditeurs jamais archivés (garantie écrite dans le code) ------------------

BAC_PLANCHER = "a_lire"  # le bac le plus bas qui reste dans la boîte de réception


def _liste_jamais_archiver() -> set[str]:
    """Domaines et adresses de jamais_archiver.txt (une entrée par ligne, # = commentaire)."""
    if not config.FICHIER_JAMAIS_ARCHIVER.exists():
        return set()
    entrees = set()
    for ligne in config.FICHIER_JAMAIS_ARCHIVER.read_text(encoding="utf-8").splitlines():
        ligne = ligne.split("#")[0].strip().lower().lstrip("@")
        if ligne:
            entrees.add(ligne)
    return entrees


def jamais_archiver(mail: Mail, liste: set[str]) -> bool:
    adresse = mail.expediteur_adresse
    return bool(adresse) and (adresse in liste or any(d in liste for d in _domaines(adresse)))


def _appliquer_plancher(c: Classement) -> Classement:
    """Un bac qui archive (🟢, ⚫) est remonté à 🟡 À-lire : le mail reste dans la boîte."""
    if not config.BACS[c.bac].archiver:
        return c
    raison = f"{c.raison} (expéditeur jamais archivé)"
    return Classement(c.mail_id, BAC_PLANCHER, raison, c.vaut_mon_temps, f"{c.source}+plancher")


def pre_trier(mail: Mail, regles: str = "") -> Classement | None:
    if _cite_dans_regles_perso(mail, regles):
        return None  # tes règles perso priment : Claude décide
    if config.REGLE_R1_PROMOTIONS and mail.categorie == "Promotions" and mail.desinscription:
        return Classement(mail.id, "poubelle", "Promotion (Gmail) avec lien de désinscription", False, "R1")
    if (
        config.REGLE_R2_RESEAUX_SOCIAUX
        and mail.categorie == "Réseaux sociaux"
        and _NO_REPLY.search(mail.expediteur_adresse)
    ):
        return Classement(mail.id, "info_auto", "Notification automatique de réseau social", False, "R2")
    return None


# --- Appel à Claude -------------------------------------------------------------


def binaire_claude() -> str:
    chemin = (
        os.getenv("CLAUDE_BIN")
        or shutil.which("claude")
        or str(Path.home() / ".local" / "bin" / "claude")
    )
    if not Path(chemin).exists():
        raise ClaudeIndisponible(
            "Claude Code est introuvable. Installe-le : curl -fsSL https://claude.ai/install.sh | bash"
        )
    return chemin


def _expliquer_erreur(texte: str) -> str:
    bas = texte.lower()
    if "401" in bas or "authenticat" in bas or "bearer" in bas:
        return "Jeton Claude refusé (expiré ou révoqué). Lance : python renouveler_jeton.py"
    if "limit" in bas or "quota" in bas or "429" in bas:
        return "Quota de l'abonnement atteint : le tri reprendra plus tard, tout seul."
    return f"Claude Code a renvoyé une erreur : {texte.strip()[:300]}"


def executer_claude(message: str, systeme: str | None = None, schema: dict | None = None) -> dict:
    """Envoie `message` à Claude via ton abonnement. Renvoie la réponse JSON de Claude Code."""
    jeton = os.getenv("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    if not jeton:
        raise ClaudeIndisponible("Jeton Claude absent du .env. Lance : python renouveler_jeton.py")

    # Sans clé API dans l'environnement : Claude Code utilise forcément l'abonnement.
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    env["CLAUDE_CODE_OAUTH_TOKEN"] = jeton

    commande = [
        binaire_claude(), "-p",
        "--model", config.MODELE,
        "--effort", config.EFFORT,
        "--output-format", "json",
        "--no-session-persistence",
        "--safe-mode",  # ni CLAUDE.md, ni extensions : rien d'inutile dans le contexte
        "--strict-mcp-config",
    ]
    if systeme:
        commande += ["--system-prompt", systeme]
    if schema:
        commande += ["--json-schema", json.dumps(schema)]
    commande += ["--tools", ""]  # en dernier : --tools accepte une liste

    try:
        proc = subprocess.run(
            commande, input=message, capture_output=True, text=True,
            timeout=config.DELAI_CLAUDE_SECONDES, env=env, cwd=config.DOSSIER,
        )
    except subprocess.TimeoutExpired:
        raise ClaudeIndisponible(f"Claude n'a pas répondu en {config.DELAI_CLAUDE_SECONDES} s.")
    except OSError as e:
        raise ClaudeIndisponible(f"Impossible de lancer Claude Code : {e}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ClaudeIndisponible(_expliquer_erreur(proc.stderr or proc.stdout or f"code {proc.returncode}"))
    if not isinstance(data, dict) or data.get("is_error") or proc.returncode != 0:
        detail = data.get("result", "") if isinstance(data, dict) else proc.stdout
        raise ClaudeIndisponible(_expliquer_erreur(str(detail) or proc.stderr))
    return data


def _extraire_json(data: dict) -> dict:
    sortie = data.get("structured_output")
    if isinstance(sortie, dict):
        return sortie
    texte = str(data.get("result", "")).strip()
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut == -1 or fin <= debut:
        raise ReponseInvalide("pas de JSON dans la réponse de Claude")
    try:
        return json.loads(texte[debut : fin + 1])
    except json.JSONDecodeError as e:
        raise ReponseInvalide(f"JSON illisible : {e}")


def prompt_systeme(regles: str = "") -> str:
    texte = config.FICHIER_PROMPT.read_text(encoding="utf-8").strip()
    if regles:
        texte += (
            "\n\nRègles personnelles du destinataire "
            "(prioritaires sur les règles ci-dessus) :\n" + regles
        )
    return texte


def formater_mail(code: str, mail: Mail) -> str:
    indices = (
        f"catégorie Gmail : {mail.categorie or 'aucune'} ; "
        f"lien de désinscription : {'oui' if mail.desinscription else 'non'} ; "
        f"réponse à une conversation : {'oui' if mail.reponse else 'non'}"
    )
    contenu = (
        f"De : {mail.expediteur_nom} <{mail.expediteur_adresse}>\n"
        f"Destinataires : {mail.destinataires}\n"
        f"Objet : {mail.objet}\n"
        f"Date : {mail.date:%d/%m/%Y %H:%M}\n"
        f"Indices : {indices}\n"
        f"Extrait :\n{mail.extrait}"
    )
    # Un mail ne doit pas pouvoir « fermer » sa balise et se faire passer pour un autre.
    contenu = re.sub(r"<\s*/?\s*mail", "‹mail", contenu, flags=re.I)
    return f'<mail id="{code}">\n{contenu}\n</mail>'


def classer_lot(mails: list[Mail], systeme: str) -> tuple[list[Classement], dict]:
    codes = {f"m{i}": m for i, m in enumerate(mails, 1)}  # ids courts : moins de tokens
    message = (
        f"Classe ces {len(mails)} mails. Renvoie exactement un classement par mail, "
        f"avec son id ({', '.join(codes)}).\n\n"
        + "\n\n".join(formater_mail(c, m) for c, m in codes.items())
    )
    data = executer_claude(message, systeme=systeme, schema=SCHEMA)
    classements = []
    for item in _extraire_json(data).get("classements", []):
        if not isinstance(item, dict):
            continue
        mail = codes.pop(str(item.get("id")), None)
        bac, vaut = item.get("bac"), item.get("vaut_mon_temps")
        if mail is None or bac not in config.BACS or not isinstance(vaut, bool):
            continue  # réponse incomplète : ce mail sera retenté plus tard
        raison = str(item.get("raison", "")).strip()[:200]
        classements.append(Classement(mail.id, bac, raison, vaut, "IA"))
    return classements, data.get("usage") or {}


def classer(mails: list[Mail], au_fil=None) -> Resultat:
    """Classe une liste de mails. Ceux qui échouent restent non classés (retentés plus tard)."""
    res = Resultat()
    regles = _regles_perso()
    liste = _liste_jamais_archiver()
    proteges = {m.id for m in mails if jamais_archiver(m, liste)}
    pour_claude = []
    for mail in mails:
        c = None if mail.id in proteges else pre_trier(mail, regles)  # protégé : Claude décide
        if c:
            res.classements[mail.id] = c
        else:
            pour_claude.append(mail)

    if not pour_claude:
        return res
    systeme = prompt_systeme(regles)
    lots = [pour_claude[i : i + config.TAILLE_LOT] for i in range(0, len(pour_claude), config.TAILLE_LOT)]
    for n, lot in enumerate(lots, 1):
        if au_fil:
            au_fil(f"Classement par Claude… lot {n}/{len(lots)} ({len(lot)} mails)")
        try:
            classements, usage = classer_lot(lot, systeme)
        except ClaudeIndisponible as e:
            res.erreurs.append(str(e))
            res.indisponible = True
            res.non_tentes.update(m.id for reste in lots[n - 1 :] for m in reste)
            break  # inutile d'insister : on réessaiera au prochain passage
        except ReponseInvalide as e:
            res.erreurs.append(f"Lot {n} : {e}")
            continue
        res.appels += 1
        res.tokens_entree += sum(
            int(usage.get(k) or 0)
            for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
        )
        res.tokens_sortie += int(usage.get("output_tokens") or 0)
        for c in classements:
            res.classements[c.mail_id] = _appliquer_plancher(c) if c.mail_id in proteges else c
    return res
