"""Le juge : un monde simulé passe par toute la chaîne réelle (vie privée → base → analyse → mémoire des refus), puis
on mesure le rappel, la précision, et l'absence de toute fuite (exclus, faux secrets)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from modules.corvees import config, ia, privacy, suite
from modules.corvees.db import Base
from modules.corvees.detection.moteur import analyser, frequence_actuelle
from tests.corvees.simulation.generateur import Monde, generer


@dataclass
class Resultat:
    graine: int
    rappel: float
    precision: float
    top: list[dict]
    manquees: list[str]
    fausses: list[list[str]]
    refusee_revenue: bool
    spotify_en_tete: bool
    fuites: list[str] = field(default_factory=list)  # ce qui n'aurait jamais dû être écrit
    messages_claude: int = 0  # demandes parties chez le Claude imité (la vérification a bien porté dessus)
    monde: Monde | None = None
    base: Path | None = None


def evaluer(graine: int, dossier: Path, corvees=None, jours: int = 28) -> Resultat:
    reglages, _ = config.charger({"dossier": str(dossier)})
    gardien = privacy.Gardien(reglages, privacy.sel(dossier))
    base = Base(dossier / "corvees.db", gardien)
    monde = generer(graine, jours=jours, corvees=corvees)
    for i in range(0, len(monde.evenements), 5000):  # par paquets, comme le démon
        base.ajouter(monde.evenements[i : i + 5000])

    # Une analyse tous les 3 jours, comme le soir : la corvée piégée est refusée dès qu'elle est proposée,
    # et ne doit plus jamais revenir ensuite.
    refusee = next((c for c in monde.corvees if c.refusee), None)
    refusee_le, revenue = None, False
    if refusee:
        for jour in range(10, jours, 3):
            instant = monde.debut + jour * 86400
            vus = base.evenements(monde.debut, instant)
            proposees = analyser(vus, reglages, base.decisions(), instant, fin=instant)
            for c in proposees:
                if refusee.retrouvee_par(c):
                    if refusee_le is None:
                        ref = frequence_actuelle(vus, reglages, c["tokens"], instant)
                        base.decider(c["signature"], c["id"], "reject", None, ref, c["tokens"])
                        refusee_le = jour
                    else:
                        revenue = True

    final = analyser(base.evenements(monde.debut), reglages, base.decisions(), maintenant=monde.fin, fin=monde.fin)
    top = final[: reglages["scoring"]["top"]]
    plantees = [c for c in monde.corvees if not c.refusee]
    trouvees = {c.nom for c in plantees for x in top if c.retrouvee_par(x)}
    justes = [x for x in top if any(c.retrouvee_par(x) for c in plantees)]
    fausses = [x["tokens"] for x in top if x not in justes]

    # La suite du soir, avec un Claude imité qui recopie tout ce qu'il reçoit (le pire cas) : descriptions et
    # propositions écrites sur le disque.
    base.fermer()
    envoye: list[str] = []
    journal: list[str] = []
    suite.traiter(reglages, final, monde.fin, journal.append, demander=_claude_perroquet(envoye))

    # Fuites : rien d'exclu, aucun secret, ni dans la base (fichier brut), ni dans les candidats, ni dans ce qui
    # part chez Claude, ni dans les propositions, ni dans le journal.
    brut = b"".join(p.read_bytes() for p in dossier.glob("corvees.db*"))
    brut += b"".join(p.read_bytes() for p in (dossier / "propositions").rglob("*") if p.is_file())
    texte = json.dumps(final, ensure_ascii=False) + "\n".join(envoye + journal)
    fuites = []
    for cherche in monde.exclus + monde.secrets + [s.replace(" ", "") for s in monde.secrets]:
        if cherche.encode() in brut or cherche in texte:
            fuites.append(cherche)
    return Resultat(
        graine,
        rappel=len(trouvees) / len(plantees),
        precision=len(justes) / len(top) if top else 0.0,
        top=top,
        manquees=[c.nom for c in plantees if c.nom not in trouvees],
        fausses=fausses,
        refusee_revenue=revenue or bool(refusee_le is not None and any(refusee.retrouvee_par(x) for x in final)),
        spotify_en_tete=any(x["tokens"] == ["app:Spotify"] for x in top),
        fuites=fuites,
        messages_claude=len(envoye),
        monde=monde,
        base=dossier / "corvees.db",
    )


def _claude_perroquet(envoye: list[str]):
    """Un Claude imité qui recopie dans ses descriptions les étapes reçues : si un secret partait, il reviendrait."""

    def demander(message: str, **_):
        envoye.append(message)
        recues = json.loads(message[len(ia.CONSIGNES) :])
        corvees = [
            {
                "id": c["id"],
                "titre_court": "Corvée repérée",
                "description_fr": "Tu fais ceci : " + " ; ".join(c["etapes"]),
                "pourquoi_corvee": json.dumps(c, ensure_ascii=False)[:400],
                "solution": {
                    "type": "autre",
                    "explication": "À voir.",
                    "script": "",
                    "installation_pas_a_pas": [],
                    "risques": "Aucun.",
                },
                "gain_minutes_mois": 1,
                "difficulte": "facile",
                "confiance": 0.5,
            }
            for c in recues
        ]
        return SimpleNamespace(donnees={"corvees": corvees}, tokens_entree=1000, tokens_sortie=500)

    return demander
