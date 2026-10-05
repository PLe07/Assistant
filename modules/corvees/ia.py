"""La couche IA : Claude décrit en français chaque corvée repérée et propose une façon de l'automatiser.

Ce qui part chez Claude, et seulement ça : pour au plus 8 corvées, leurs étapes résumées et déjà caviardées
(« fmove:Downloads→Documents/Factures [pdf, Facture_*] »), combien de fois par mois, sur combien de jours, l'heure
habituelle. Jamais un événement brut, une date précise, un contenu de fichier ou un titre de fenêtre.

Garde-fous : une demande par jour au plus ; réponse vérifiée par un schéma (une relance de correction si elle ne
colle pas) ; trois essais sur panne passagère, avec une attente croissante ; budget mensuel (2 $ par défaut) au-delà
duquel les descriptions sont faites sur place, sans Claude. Rien ici ne fait tomber le démon.
"""

from __future__ import annotations

import copy
import json
import time
from collections.abc import Callable
from typing import Any

from jsonschema import Draft202012Validator

from modules.corvees import privacy
from modules.corvees.normalize import debut_du_jour, mois_de

TYPES_SOLUTION = [
    "raccourci_macos",
    "app_raccourcis",
    "script_shell",
    "alias_zsh",
    "tache_launchd",
    "regle_dossier",
    "autre",
]

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["corvees"],
    "properties": {
        "corvees": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "titre_court",
                    "description_fr",
                    "pourquoi_corvee",
                    "solution",
                    "gain_minutes_mois",
                    "difficulte",
                    "confiance",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "titre_court": {"type": "string", "minLength": 3, "maxLength": 80},
                    "description_fr": {"type": "string", "minLength": 10, "maxLength": 600},
                    "pourquoi_corvee": {"type": "string", "maxLength": 400},
                    "solution": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["type", "explication", "script", "installation_pas_a_pas", "risques"],
                        "properties": {
                            "type": {"enum": TYPES_SOLUTION},
                            "explication": {"type": "string", "maxLength": 1000},
                            "script": {"type": "string", "maxLength": 4000},
                            "installation_pas_a_pas": {
                                "type": "array",
                                "maxItems": 12,
                                "items": {"type": "string", "maxLength": 400},
                            },
                            "risques": {"type": "string", "maxLength": 500},
                        },
                    },
                    "gain_minutes_mois": {"type": "number", "minimum": 0, "maximum": 10000},
                    "difficulte": {"enum": ["facile", "moyen", "avancé"]},
                    "confiance": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        }
    },
}
_VALIDATEUR = Draft202012Validator(SCHEMA)
_BORNES = ("minLength", "maxLength", "minimum", "maximum", "maxItems")

SYSTEME = (
    "Tu es un expert de l'automatisation sur Mac (macOS récent, zsh, app Raccourcis, launchd). "
    "Tu écris en français simple, en tutoyant, pour un débutant. Tu réponds uniquement par le JSON demandé."
)

CONSIGNES = """Voici des corvées répétées repérées sur le Mac de l'utilisateur. Pour chacune, avec le même id :
- titre_court : 3 à 8 mots ; description_fr : ce qu'il fait à la main, en une ou deux phrases ;
- pourquoi_corvee : pourquoi c'est répétitif et automatisable ;
- solution : la plus simple possible, sans installer d'outil si on peut.
  type : raccourci_macos (raccourci clavier ou réglage de macOS), app_raccourcis (app Raccourcis, automatisation
  personnelle), script_shell (script zsh), alias_zsh (une seule ligne « alias nom='…' »), tache_launchd (la commande
  zsh à lancer ; le détecteur écrit lui-même le fichier .plist : à l'heure habituelle, ou dès qu'un fichier arrive
  dans le dossier de départ), regle_dossier (action de dossier du Finder, ou Hazel), autre.
  script : vide si la solution n'en a pas besoin. Jamais sudo, jamais rm -rf, jamais curl|sh ; n'écris que dans le
  dossier personnel (~) ; chemins entre guillemets.
  installation_pas_a_pas : les étapes, une par ligne ; risques : ce qui pourrait mal tourner, en une phrase ;
- gain_minutes_mois : minutes gagnées par mois (au plus le temps passé aujourd'hui) ;
- difficulte : facile, moyen ou avancé ; confiance : de 0 à 1.

Lecture des étapes : app:X = ouvrir l'appli X ; url:site = aller sur ce site ; fen:appli:titre = une fenêtre ;
fmove:A→B [ext, motif] = déplacer un fichier du dossier A au dossier B (chemins depuis ~) ; fren:A [ext, avant→après]
= renommer ; fconv:A [ext1→ext2, motif] = convertir ; fdel = supprimer ; fcreate = un fichier apparaît ;
clip:A→B = copier dans l'appli A et coller dans l'appli B ; cmd: = une commande du terminal.
« * » = une partie qui change à chaque fois. « [secret] », « [email] »… = valeurs masquées.

Corvées :
"""


class Indisponible(Exception):
    """Claude n'a pas pu décrire les corvées : les descriptions sont faites sur place."""


# --- ce qui part chez Claude --------------------------------------------------------------------------------------


def resume(c: dict[str, Any]) -> dict[str, Any]:
    """Une corvée réduite à ses chiffres et à ses étapes caviardées (ni date, ni empreinte, ni exemple)."""
    details = c.get("details") or {}
    r: dict[str, Any] = {
        "id": c["id"],
        "type": c["type"],
        "etapes": [privacy.caviarder(t) for t in c["tokens"]],
        "fois_par_mois": c["frequence_mois"],
        "jours_distincts": c["jours_distincts"],
        "duree_moyenne_s": c["duree_moyenne_s"],
        "minutes_par_mois": c["minutes_mois"],
    }
    if details.get("creneau"):
        r["heure_habituelle"] = details["creneau"]
    if details.get("jour_semaine"):
        r["jour"] = details["jour_semaine"]
    if details.get("origine"):
        r["fichier_apparu_avant"] = privacy.caviarder(str(details["origine"]))
    return r


def message(candidats: list[dict[str, Any]]) -> str:
    return CONSIGNES + json.dumps([resume(c) for c in candidats], ensure_ascii=False, indent=1)


def schema_pour_claude() -> dict[str, Any]:
    """Le schéma sans les bornes de longueur ni de valeur (vérifiées ici, après coup)."""

    def nettoyer(x: Any) -> Any:
        if isinstance(x, dict):
            return {k: nettoyer(v) for k, v in x.items() if k not in _BORNES}
        if isinstance(x, list):
            return [nettoyer(v) for v in x]
        return x

    return nettoyer(copy.deepcopy(SCHEMA))


# --- ce qui revient ----------------------------------------------------------------------------------------------


def valider(donnees: Any, ids: set[str]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """(descriptions par id, erreurs). Une réponse hors schéma ne donne rien ; une corvée oubliée est signalée."""
    erreurs = [
        f"{'/'.join(str(p) for p in e.absolute_path) or 'racine'} : {e.message}"
        for e in sorted(_VALIDATEUR.iter_errors(donnees), key=lambda e: list(map(str, e.absolute_path)))
    ]
    if erreurs:
        return {}, erreurs[:10]
    trouvees: dict[str, dict[str, Any]] = {}
    for d in donnees["corvees"]:
        if d["id"] in ids:
            trouvees[d["id"]] = nettoyer(d)
        else:
            erreurs.append(f"id inconnu : {d['id']}")
    oubliees = sorted(ids - trouvees.keys())
    if oubliees:
        erreurs.append(f"corvées oubliées : {', '.join(oubliees)}")
    return trouvees, erreurs


def nettoyer(d: Any) -> Any:
    """Caviarde chaque texte avant de l'écrire sur le disque (au cas où)."""
    if isinstance(d, dict):
        return {k: nettoyer(v) for k, v in d.items()}
    if isinstance(d, list):
        return [nettoyer(v) for v in d]
    if isinstance(d, str):
        return privacy.caviarder(d)
    return d


def cout(entree: int, sortie: int, tarif: dict[str, float]) -> float:
    return entree * float(tarif["entree"]) / 1e6 + sortie * float(tarif["sortie"]) / 1e6


def estimation(texte: str, n: int, tarif: dict[str, float]) -> float:
    """Le coût probable d'une demande (en trop plutôt qu'en moins) : sert à ne pas dépasser le budget."""
    return cout(len(texte) // 3 + 4000, 900 * n, tarif)


# --- la demande du jour -----------------------------------------------------------------------------------------


def _passagere(e: Exception) -> bool:
    """Une panne qui peut passer toute seule (surcharge, quota, délai) ; pas une erreur de réglage."""
    if getattr(e, "definitif", False):
        return False
    texte = str(e).lower()
    return not any(m in texte for m in ("introuvable", "jeton", "absent", "désactivé", "plafond"))


def _pause_restante() -> float:
    """Le temps qu'il reste avant la fin de la pause de l'Assistant après un quota (0 si pas de pause)."""
    try:
        from core import etat

        fin = etat.lire("claude_pause_jusqua")
        return max(0.0, float(fin) - time.time()) if fin else 0.0
    except Exception:
        return 0.0


class Demande:
    """Une demande à Claude : trois essais sur panne passagère, une relance si le JSON ne colle pas au schéma."""

    def __init__(
        self,
        base: Any,
        reglages: dict[str, Any],
        maintenant: float,
        demander: Callable[..., Any] | None = None,
        dormir: Callable[[float], None] = time.sleep,
        pause_restante: Callable[[], float] = _pause_restante,
        journal: Callable[[str], None] | None = None,
    ):
        self.base = base
        self.r = reglages["ia"]
        self.maintenant = maintenant
        self.demander = demander
        self.dormir = dormir
        self.pause_restante = pause_restante
        self.journal = journal or (lambda m: None)
        self.lancements = 0
        self.cout = 0.0

    def _tarif(self) -> dict[str, float]:
        tarifs = self.r["tarifs"]
        return dict(tarifs.get(self.r["modele"], tarifs["fort"]))

    def _un_lancement(self, texte: str) -> Any:
        if self.demander is not None:
            demander = self.demander
        else:
            from core.cerveau import demander as demander_assistant

            demander = demander_assistant
        self.lancements += 1
        try:
            rep = demander(
                texte,
                module="corvees",
                systeme=SYSTEME,
                schema=schema_pour_claude(),
                modele=self.r["modele"],
                delai=int(self.r["delai_s"]),
                essais=1,  # les essais sont comptés ici
            )
        except Exception:
            self.base.noter_cout(mois_de(self.maintenant), self.r["modele"], 0, 0, 0.0, False, self.maintenant)
            raise
        prix = cout(rep.tokens_entree, rep.tokens_sortie, self._tarif())
        self.cout += prix
        self.base.noter_cout(
            mois_de(self.maintenant),
            self.r["modele"],
            rep.tokens_entree,
            rep.tokens_sortie,
            prix,
            True,
            self.maintenant,
        )
        return rep

    def _avec_essais(self, texte: str) -> Any:
        from core.cerveau import ClaudeIndisponible

        essais = max(1, int(self.r["essais"]))
        for essai in range(1, essais + 1):
            try:
                return self._un_lancement(texte)
            except ClaudeIndisponible as e:
                if not _passagere(e) or essai == essais:
                    raise Indisponible(str(e)) from e
                attente = float(self.r["attente_s"]) * 2 ** (essai - 1)
                pause = self.pause_restante()
                if pause:  # quota : l'Assistant s'est mis en pause, on attend la fin sans insister
                    attente = min(float(self.r["attente_max_s"]), pause + 5)
                self.journal(f"Claude : {e} ; essai {essai + 1}/{essais} dans {attente:.0f} s")
                self.dormir(attente)
            except Exception as e:  # imprévu : pas de nouvel essai, description locale
                raise Indisponible(f"{e.__class__.__name__} : {e}") from e
        raise Indisponible("aucun essai")  # pragma: no cover

    def faire(self, candidats: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        texte = message(candidats)
        ids = {c["id"] for c in candidats}
        rep = self._avec_essais(texte)
        trouvees, erreurs = valider(rep.donnees, ids)
        if not trouvees and erreurs:
            self.journal(f"Réponse de Claude hors format ({erreurs[0]}) : une relance de correction")
            correction = (
                f"{texte}\n\nTa réponse précédente ne respectait pas le format attendu :\n- "
                + "\n- ".join(erreurs)
                + "\nRenvoie le JSON complet, corrigé."
            )
            rep = self._avec_essais(correction)
            trouvees, erreurs = valider(rep.donnees, ids)
            if not trouvees:
                raise Indisponible(f"réponse toujours hors format : {erreurs[0] if erreurs else 'vide'}")
        if erreurs:
            self.journal(f"Réponse de Claude : {'; '.join(erreurs)}")
        return trouvees


# --- l'entrée du module -----------------------------------------------------------------------------------------


def decrire(
    base: Any,
    candidats: list[dict[str, Any]],
    reglages: dict[str, Any],
    maintenant: float,
    *,
    demander: Callable[..., Any] | None = None,
    dormir: Callable[[float], None] = time.sleep,
    pause_restante: Callable[[], float] = _pause_restante,
    journal: Callable[[str], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """signature → description, pour chaque corvée. Celles déjà décrites par Claude sont reprises telles quelles ;
    les nouvelles partent chez Claude (une demande par jour au plus, dans le budget) ; sinon, description locale."""
    from modules.corvees.descriptions import locale

    journal = journal or (lambda m: None)
    connues = base.descriptions()
    resultat: dict[str, dict[str, Any]] = {}
    nouvelles = []
    for c in candidats:
        d = connues.get(c["signature"])
        if d and d.get("source") == "claude":
            resultat[c["signature"]] = d
        else:
            nouvelles.append(c)
    r = reglages["ia"]
    a_envoyer = nouvelles[: int(r["max_candidats"])]
    pourquoi = _refus(base, a_envoyer, reglages, maintenant)
    par_id: dict[str, dict[str, Any]] = {}
    if pourquoi:
        if a_envoyer:
            journal(f"Descriptions faites sur place : {pourquoi}")
    else:
        base.ecrire("ia_derniere_demande", maintenant)
        demande = Demande(base, reglages, maintenant, demander, dormir, pause_restante, journal)
        try:
            par_id = demande.faire(a_envoyer)
            journal(
                f"Claude a décrit {len(par_id)} corvée(s) : {demande.lancements} lancement(s), "
                f"{demande.cout:.4f} $ (ce mois : {base.cout_du_mois(mois_de(maintenant)):.2f} $)"
            )
        except Indisponible as e:
            journal(f"Claude indisponible ({e}) : descriptions faites sur place")
    for c in nouvelles:
        if c["id"] in par_id:
            d, source = par_id[c["id"]], "claude"
        else:
            d, source = locale(c), "locale"
        base.noter_description(c["signature"], source, d, maintenant)
        resultat[c["signature"]] = {**d, "source": source}
    return resultat


def _refus(base: Any, a_envoyer: list[dict[str, Any]], reglages: dict[str, Any], maintenant: float) -> str:
    """Pourquoi on ne demande pas à Claude aujourd'hui (vide : on demande)."""
    r = reglages["ia"]
    if not a_envoyer:
        return "rien de nouveau"
    if not r["actif"]:
        return "Claude coupé dans les réglages (modules.corvees.ia.actif)"
    if float(base.lire("ia_derniere_demande", 0) or 0) >= debut_du_jour(maintenant):
        return "déjà une demande à Claude aujourd'hui"
    tarifs = r["tarifs"]
    tarif = tarifs.get(r["modele"], tarifs["fort"])
    depense = base.cout_du_mois(mois_de(maintenant))
    if depense + estimation(message(a_envoyer), len(a_envoyer), tarif) > float(r["budget_mensuel_usd"]):
        return f"budget du mois atteint ({depense:.2f} $ sur {float(r['budget_mensuel_usd']):.2f} $)"
    return ""
