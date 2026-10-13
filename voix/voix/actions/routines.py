"""Les routines de `commandes.toml` : une suite d'étapes, chacune une intention de la liste blanche avec ses
paramètres. **Tout** est vérifié avant de lancer la première étape (intention connue, objets trouvés dans le
catalogue, nombres bornés) ; une étape sensible n'est permise que dans une routine marquée `sensible = true` (alors la
routine entière demande une confirmation). Une routine ne lance pas d'autre routine.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from voix.actions.base import Reponse, erreur, fait
from voix.nlu import durees
from voix.nlu.alias import Routine
from voix.nlu.approx import forme_normale
from voix.nlu.catalogue import Catalogue
from voix.nlu.comprendre import Comprehension
from voix.nlu.intentions import INTENTIONS
from voix.nlu.normalisation import normaliser

ETAPES_PERMISES = {
    i for i in INTENTIONS
    if i.split(".")[0] in ("app", "dossier", "alias", "web", "son", "musique", "systeme", "concentration", "minuteur",
                           "rappel", "raccourci", "module", "fichier")
} - {"fichier.ouvrir_resultat", "fichier.reveler_resultat", "fichier.chercher"}  # fmt: skip
OBJETS = {"app": "app", "dossier": "dossier", "site": "site", "alias": "alias", "playlist": "playlist",
          "raccourci": "raccourci"}  # fmt: skip
TEXTES = {"message": 200, "requete": 200, "texte": 200, "mode": 30, "langue": 2, "lecteur": 10}
ETAPES_MAX = 12


class EtapeRefusee(ValueError):
    pass


def _nombre(v: Any, bas: int, haut: int, cle: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not bas <= v <= haut:
        raise EtapeRefusee(f"« {cle} » doit être un nombre entre {bas} et {haut}")
    return v


def preparer(routine: Routine, catalogue: Catalogue) -> list[Comprehension]:
    """Les étapes, vérifiées et prêtes ; EtapeRefusee à la première étape douteuse (rien n'est lancé)."""
    if not routine.etapes or len(routine.etapes) > ETAPES_MAX:
        raise EtapeRefusee(f"entre 1 et {ETAPES_MAX} étapes")
    pretes: list[Comprehension] = []
    for n, etape in enumerate(routine.etapes, 1):
        intention = etape.get("intention")
        if intention not in ETAPES_PERMISES:
            raise EtapeRefusee(f"étape {n} : « {intention} » n'est pas permise dans une routine")
        if INTENTIONS[intention].sensible and not routine.sensible:
            raise EtapeRefusee(f"étape {n} : « {intention} » demande une routine marquée sensible = true")
        params: dict[str, Any] = {}
        for cle, v in etape.items():
            if cle == "intention":
                continue
            if cle in OBJETS:
                if not isinstance(v, str) or not forme_normale(v):
                    raise EtapeRefusee(f"étape {n} : « {cle} » doit être un nom")
                trouves = [c for c in catalogue.chercher(v, (OBJETS[cle],)) if c.score >= 0.9]
                if not trouves:
                    raise EtapeRefusee(f"étape {n} : {cle} « {v} » introuvable")
                params["objet"] = trouves[0].objet
            elif cle == "niveau":
                params["niveau"] = _nombre(v, 0, 100, cle)
            elif cle == "pas":
                params["pas"] = _nombre(v, 1, 100, cle)
            elif cle == "duree":
                d = durees.duree(normaliser(v).texte) if isinstance(v, str) else None
                if d is None:
                    raise EtapeRefusee(f"étape {n} : durée « {v} » incomprise")
                params["duree_s"] = d
            elif cle in TEXTES:
                if not isinstance(v, str) or not v.strip() or len(v) > TEXTES[cle]:
                    raise EtapeRefusee(f"étape {n} : « {cle} » invalide")
                params[cle] = v.strip()
            else:
                raise EtapeRefusee(f"étape {n} : paramètre inconnu « {cle} »")
        pretes.append(Comprehension("compris", intention, params, 1.0))
    return pretes


def lancer(routine: Routine, catalogue: Catalogue, executer: Callable[[Comprehension], Reponse]) -> Reponse:
    try:
        etapes = preparer(routine, catalogue)
    except EtapeRefusee as e:
        return erreur(f"La routine « {routine.nom} » est refusée : {e}.", "routine.lancer")
    echecs: list[str] = []
    for c in etapes:
        r = executer(c)
        if r.statut == "erreur":
            echecs.append(r.texte)
    if echecs:
        return erreur(f"Routine « {routine.nom} » : {len(etapes) - len(echecs)}/{len(etapes)} étapes faites. "
                      + " ".join(echecs[:2]), "routine.lancer")  # fmt: skip
    return fait(f"Routine « {routine.nom} » ({len(etapes)} étape{'s' if len(etapes) > 1 else ''})", "routine.lancer")
