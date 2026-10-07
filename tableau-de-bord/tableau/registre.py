"""Le registre `modules.toml` (dans `~/Library/Application Support/TableauDeBord/`), généré puis modifiable (§3).

- Premier démarrage : il est **généré** avec les modules connus de ton écosystème (installés ou non : un absent est
  « ⚪ pas installé », sans alarme) et chaque agent `com.<session>.*` inconnu (adaptateur générique).
- Ensuite, il est **à toi** : il n'est jamais réécrit. Un module découvert plus tard (un futur `com.<session>.xxx`)
  y est **ajouté à la fin**, sans toucher au reste.
- `dossier_projet = "auto"` : le dossier est déduit de la découverte (le plist du module, ou le dossier de
  l'assistant) ; tu peux y mettre un chemin.

Les attentes (« brief vers 7h15 », « analyse vers 21 h »…) et les plafonds viennent des README des modules
(DECISIONS.md, D-13) ; les heures et plafonds réglés chez le module lui-même priment (lus dans ses réglages).
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import fields
from pathlib import Path
from typing import Any

from tableau.decouverte import Decouverte
from tableau.module import Attente, DefModule

AUTO = "auto"
PYTHON_DU_PROJET = ".venv/bin/python"


def _assistant(prefixe: str) -> list[DefModule]:
    """Les modules qui vivent dans le dépôt de l'assistant."""
    return [
        DefModule(
            id="assistant",
            nom="Assistant",
            emoji="🤖",
            adaptateur="assistant",
            labels=["com.assistant.superviseur", "com.assistant.icone"],
            superviseur="mails",
            dossier_projet=AUTO,
            bases=["donnees/etat.db"],
            perimetre_code=["."],
            perimetre_exclu=[
                "modules/corvees",
                "modules/demarrage",
                "modules/trieur",
                "corvees.py",
                "demarrage.py",
                "trieur.py",
                "bouclier",
                "quotidien",
                "tableau-de-bord",
            ],  # fmt: skip
            commande_diagnostic=[PYTHON_DU_PROJET, "assistant.py", "etat"],
            aide="python assistant.py etat (dans ~/Assistant)",
            attendu=True,
        ),
        DefModule(
            id="corvees",
            nom="Corvées",
            emoji="🔁",
            adaptateur="corvees",
            labels=[f"com.{prefixe}.corvees"],
            superviseur="corvees",
            dossier_projet=AUTO,
            perimetre_code=["modules/corvees", "corvees.py"],
            plafond_usd=2.0,
            commande_diagnostic=[PYTHON_DU_PROJET, "corvees.py", "doctor"],
            aide="python corvees.py doctor (dans ~/Assistant)",
            attentes=[
                Attente("analyse", "quotidienne", "analyse quotidienne vers 21h", heure="21:00", tolerance_min=60)
            ],
            attendu=True,
        ),
        DefModule(
            id="nettoyeur",
            nom="Nettoyeur",
            emoji="🧹",
            adaptateur="nettoyeur",
            labels=[f"com.{prefixe}.nettoyeur"],
            superviseur="demarrage",
            dossier_projet=AUTO,
            perimetre_code=["modules/demarrage", "demarrage.py"],
            commande_diagnostic=[PYTHON_DU_PROJET, "demarrage.py", "doctor"],
            aide="python demarrage.py doctor (dans ~/Assistant)",
            attentes=[
                Attente("releve", "periodique", "un relevé toutes les 2 min", toutes_les_min=2, tolerance_min=10)
            ],
            attendu=True,
        ),
        DefModule(
            id="trieur",
            nom="Trieur",
            emoji="🗂",
            adaptateur="trieur",
            labels=[f"com.{prefixe}.trieur"],
            superviseur="trieur",
            dossier_projet=AUTO,
            files=["icloud:BoiteMac", "~/Documents/À trier par l'assistant", "~/Desktop/À trier"],
            file_max_min=15,
            perimetre_code=["modules/trieur", "trieur.py"],
            plafond_usd=1.0,
            commande_diagnostic=[PYTHON_DU_PROJET, "trieur.py", "doctor"],
            aide="python trieur.py doctor (dans ~/Assistant)",
            attendu=True,
        ),
    ]


def connus(prefixe: str) -> list[DefModule]:
    """Ton écosystème tel que décrit par les README des modules (absents compris)."""
    return [
        *_assistant(prefixe),
        DefModule(
            id="bouclier",
            nom="Bouclier",
            emoji="🛡️",
            adaptateur="bouclier",
            labels=[f"com.{prefixe}.bouclier"],
            dossier_projet=AUTO,
            dossier_donnees="~/Library/Application Support/Bouclier",
            dossier_logs="~/Library/Logs/Bouclier",
            bases=["~/Library/Application Support/Bouclier/bouclier.db"],
            files=["icloud:Bouclier/entree"],
            perimetre_code=["."],
            plafond_usd=2.0,
            commande_diagnostic=["~/.local/bin/bouclier", "doctor"],
            aide="bouclier doctor",
            attentes=[
                Attente("gmail", "periodique", "relève Gmail toutes les 5 min", toutes_les_min=5, tolerance_min=15)
            ],
            attendu=True,
        ),
        DefModule(
            id="quotidien",
            nom="Quotidien",
            emoji="☀️",
            adaptateur="quotidien",
            labels=[f"com.{prefixe}.quotidien"],
            dossier_projet=AUTO,
            dossier_donnees="~/Library/Application Support/Quotidien",
            dossier_logs="~/Library/Logs/Quotidien",
            bases=["~/Library/Application Support/Quotidien/quotidien.db"],
            files=["icloud:Quotidien/entree"],
            perimetre_code=["."],
            plafond_usd=2.0,
            commande_diagnostic=["~/.local/bin/quotidien", "doctor"],
            aide="quotidien doctor",
            attentes=[Attente("brief", "quotidienne", "brief chaque jour vers 7h15", heure="07:15", tolerance_min=20)],
            attendu=True,
        ),
        DefModule(
            id="ambiance",
            nom="Ambiance",
            emoji="🎶",
            adaptateur="ambiance",
            labels=[f"com.{prefixe}.ambiance", f"com.{prefixe}.ambiance.audio"],
            dossier_projet=AUTO,
            dossier_donnees="~/Library/Application Support/Ambiance",
            dossier_logs="~/Library/Logs/Ambiance",
            perimetre_code=["."],
            attendu=True,
        ),
        DefModule(
            id="n8n",
            nom="n8n",
            emoji="🔗",
            adaptateur="n8n",
            conteneur="n8n",
            port=5678,
            aide="docker ps (Docker Desktop doit être ouvert)",
            attendu=True,
        ),
    ]


def est_a_nous(label: str, prefixe: str) -> bool:
    if label == f"com.{prefixe}.tableau" or label.startswith(f"com.{prefixe}.tableau."):
        return True
    return ".tdbtest." in label and not os.environ.get("TABLEAU_INCLURE_TESTS")


def vers_tilde(chemin: Path | None, maison: Path) -> str | None:
    if chemin is None:
        return None
    try:
        return "~/" + chemin.relative_to(maison).as_posix()
    except ValueError:
        return str(chemin)


def generique(label: str, prefixe: str, decouverte: Decouverte, maison: Path) -> DefModule:
    agent = decouverte.agents.get(label)
    fin = label[len(f"com.{prefixe}.") :] if label.startswith(f"com.{prefixe}.") else label
    ident = re.sub(r"[^a-z0-9]+", "-", fin.lower()).strip("-") or "module"
    nom = fin.replace(".", " ").replace("-", " ").strip().capitalize() or label
    logs = None
    if agent is not None and agent.erreurs:
        parent = Path(agent.erreurs).parent
        logs = vers_tilde(parent, maison) if parent != Path("/") else None
    support = maison / "Library" / "Application Support" / nom
    return DefModule(
        id=ident,
        nom=nom,
        emoji="🧩",
        adaptateur="generique",
        labels=[label],
        dossier_projet=vers_tilde(agent.projet, maison) if agent is not None and agent.projet else None,
        dossier_logs=logs,
        dossier_donnees=vers_tilde(support, maison) if support.is_dir() else None,
        perimetre_code=["."] if agent is not None and agent.projet else [],
        doit_tourner=bool(agent and agent.garde_en_vie and not agent.periodique),
    )


# --- TOML : écriture (notre format, simple) et lecture (tolérante) ---------------------------------------------------


def _toml(valeur: Any) -> str:
    if isinstance(valeur, bool):
        return "true" if valeur else "false"
    if isinstance(valeur, (int, float)):
        return repr(valeur)
    if isinstance(valeur, list):
        return "[" + ", ".join(_toml(v) for v in valeur) + "]"
    texte = str(valeur).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{texte}"'


CHAMPS = [f.name for f in fields(DefModule) if f.name not in ("attentes",)]


def bloc(m: DefModule) -> str:
    lignes = ["[[module]]"]
    defaut = DefModule(id="", nom="")
    for nom in CHAMPS:
        valeur = getattr(m, nom)
        if nom not in ("id", "nom", "adaptateur") and valeur == getattr(defaut, nom):
            continue
        if valeur is None:
            continue
        lignes.append(f"{nom} = {_toml(valeur)}")
    for a in m.attentes:
        lignes.append("[[module.attente]]")
        lignes.append(f"id = {_toml(a.id)}")
        lignes.append(f"genre = {_toml(a.genre)}")
        lignes.append(f"libelle = {_toml(a.libelle)}")
        if a.heure:
            lignes.append(f"heure = {_toml(a.heure)}")
        if a.toutes_les_min:
            lignes.append(f"toutes_les_min = {a.toutes_les_min}")
        lignes.append(f"tolerance_min = {a.tolerance_min}")
        if a.preuve:
            lignes.append(f"preuve = {_toml(a.preuve)}")
    return "\n".join(lignes) + "\n"


ENTETE = """# Le registre du tableau de bord : un bloc [[module]] par module surveillé.
# Généré au premier démarrage, puis à toi : il n'est jamais réécrit (un nouveau module découvert est ajouté à la fin).
# Mettre « actif = false » sur un module le fait ignorer. « dossier_projet = "auto" » : déduit de la découverte.
# Le détail de chaque champ : modules.example.toml dans le dossier du tableau de bord.
"""


def ecrire(modules: list[DefModule]) -> str:
    return ENTETE + "".join("\n" + bloc(m) for m in modules)


def _attentes(brutes: Any, erreurs: list[str], ident: str) -> list[Attente]:
    resultat: list[Attente] = []
    for a in brutes if isinstance(brutes, list) else []:
        if not isinstance(a, dict) or not a.get("id") or a.get("genre") not in ("quotidienne", "periodique"):
            erreurs.append(f"« {ident} » : une attente mal écrite est ignorée")
            continue
        heure = a.get("heure")
        if a["genre"] == "quotidienne" and not (isinstance(heure, str) and re.fullmatch(r"\d{1,2}:\d{2}", heure)):
            erreurs.append(f"« {ident} » : l'attente « {a['id']} » doit avoir une heure HH:MM : ignorée")
            continue
        if a["genre"] == "periodique" and not isinstance(a.get("toutes_les_min"), int):
            erreurs.append(f"« {ident} » : l'attente « {a['id']} » doit avoir toutes_les_min : ignorée")
            continue
        resultat.append(
            Attente(
                id=str(a["id"]),
                genre=str(a["genre"]),
                libelle=str(a.get("libelle") or a["id"]),
                heure=heure if isinstance(heure, str) else None,
                tolerance_min=int(a["tolerance_min"]) if isinstance(a.get("tolerance_min"), int) else 20,
                toutes_les_min=a.get("toutes_les_min") if isinstance(a.get("toutes_les_min"), int) else None,
                preuve=str(a.get("preuve") or ""),
            )
        )
    return resultat


def lire(texte: str) -> tuple[list[DefModule], list[str]]:
    """Les modules du registre et les erreurs (un bloc faux est ignoré, avec un message ; jamais d'exception)."""
    erreurs: list[str] = []
    try:
        donnees = tomllib.loads(texte)
    except tomllib.TOMLDecodeError as e:
        return [], [f"modules.toml illisible ({e}) : modules connus par défaut"]
    modules: list[DefModule] = []
    vus: set[str] = set()
    defaut = DefModule(id="", nom="")
    types = {f.name: type(getattr(defaut, f.name)) for f in fields(DefModule)}
    for brut in donnees.get("module", []) if isinstance(donnees.get("module"), list) else []:
        if not isinstance(brut, dict) or not isinstance(brut.get("id"), str) or not brut["id"]:
            erreurs.append("un bloc [[module]] sans « id » est ignoré")
            continue
        ident = brut["id"]
        if ident in vus:
            erreurs.append(f"« {ident} » apparaît deux fois : le second bloc est ignoré")
            continue
        valeurs: dict[str, Any] = {"id": ident, "nom": str(brut.get("nom") or ident)}
        for nom in CHAMPS:
            if nom in ("id", "nom") or nom not in brut:
                continue
            v = brut[nom]
            attendu = types[nom]
            if attendu is list and isinstance(v, list) and all(isinstance(x, str) for x in v):
                valeurs[nom] = list(v)
            elif attendu is bool and isinstance(v, bool):
                valeurs[nom] = v
            elif nom in ("plafond_usd",) and isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0:
                valeurs[nom] = float(v)
            elif nom in ("file_max_min", "port") and isinstance(v, int) and not isinstance(v, bool) and v > 0:
                valeurs[nom] = v
            elif attendu in (str, type(None)) and isinstance(v, str):
                valeurs[nom] = v
            else:
                erreurs.append(f"« {ident} » : « {nom} » a une valeur inattendue : ignorée")
        valeurs["attentes"] = _attentes(brut.get("attente"), erreurs, ident)
        modules.append(DefModule(**valeurs))
        vus.add(ident)
    return modules, erreurs


# --- synchronisation avec la découverte ------------------------------------------------------------------------------


def resoudre(modules: list[DefModule], decouverte: Decouverte, maison: Path) -> list[DefModule]:
    """Remplace « auto » par ce que la découverte a trouvé (sans toucher au fichier)."""
    resultat = []
    assistant = vers_tilde(decouverte.assistant, maison)
    for m in modules:
        if m.dossier_projet == AUTO:
            projet = None
            for label in m.labels:
                agent = decouverte.agents.get(label)
                if agent is not None and agent.projet is not None and m.adaptateur not in ("assistant",):
                    projet = vers_tilde(agent.projet, maison)
                    break
            if projet is None and (m.adaptateur == "assistant" or m.superviseur):
                projet = assistant
            if projet is None and assistant and m.adaptateur in ("bouclier", "quotidien"):
                projet = f"{assistant}/{m.adaptateur}"
            m = _copie(m, dossier_projet=projet)
        resultat.append(m)
    return resultat


def _copie(m: DefModule, **changements: Any) -> DefModule:
    valeurs = {f.name: getattr(m, f.name) for f in fields(DefModule)}
    valeurs.update(changements)
    return DefModule(**valeurs)


def synchroniser(
    fichier: Path, prefixe: str, decouverte: Decouverte, maison: Path
) -> tuple[list[DefModule], list[str], list[str]]:
    """(modules actifs, résolus) ; ids ajoutés ce tour ; erreurs de lecture."""
    attendus = connus(prefixe)
    inconnus = [
        label
        for label in sorted(decouverte.agents)
        if label.startswith(f"com.{prefixe}.")
        and not est_a_nous(label, prefixe)
        and not any(label in m.labels for m in attendus)
    ]
    erreurs: list[str] = []
    ajoutes: list[str] = []
    if not fichier.exists():
        modules = attendus + [generique(label, prefixe, decouverte, maison) for label in inconnus]
        _ecrire(fichier, ecrire(modules))
        ajoutes = [m.id for m in modules]
    else:
        modules, erreurs = lire(fichier.read_text(encoding="utf-8"))
        if not modules and erreurs:
            modules = attendus  # fichier cassé : on surveille quand même, sans le réécrire
        else:
            couverts = {label for m in modules for label in m.labels}
            nouveaux: list[DefModule] = []
            for label in decouverte.agents:
                if label in couverts or est_a_nous(label, prefixe):
                    continue
                connu = next((m for m in attendus if label in m.labels and m.id not in {x.id for x in modules}), None)
                if connu is not None and connu.id not in {n.id for n in nouveaux}:
                    nouveaux.append(connu)
                elif connu is None and label in inconnus:
                    g = generique(label, prefixe, decouverte, maison)
                    while g.id in {m.id for m in modules + nouveaux}:
                        g = _copie(g, id=g.id + "-2")
                    nouveaux.append(g)
            if nouveaux:
                with open(fichier, "a", encoding="utf-8") as f:
                    f.write("".join("\n" + bloc(m) for m in nouveaux))
                modules += nouveaux
                ajoutes = [m.id for m in nouveaux]
    actifs = [m for m in modules if m.actif]
    return resoudre(actifs, decouverte, maison), ajoutes, erreurs


def _ecrire(fichier: Path, texte: str) -> None:
    fichier.parent.mkdir(parents=True, exist_ok=True)
    temporaire = fichier.with_suffix(".tmp")
    temporaire.write_text(texte, encoding="utf-8")
    os.chmod(temporaire, 0o600)
    temporaire.replace(fichier)
