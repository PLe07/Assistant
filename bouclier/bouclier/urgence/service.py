"""Générer la fiche urgence (HTML, PDF, carte A6, écran verrouillé), la copier sur iCloud, la revérifier en ligne
et rappeler de la relire tous les 6 mois."""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from bouclier.config import Chemins
from bouclier.db import Base
from bouclier.journal import log
from bouclier.notifier import Notifieur
from bouclier.urgence import carte_a6, ecran_verrouille, fiche, infos, pdf, sources

NOM_PDF = "Fiche urgence.pdf"
SIX_MOIS_S = 182 * 86400


@dataclass
class Sorties:
    html: Path
    pdf: Path
    carte: Path
    ecran: Path | None
    icloud: Path | None
    avertissements: list[str] = field(default_factory=list)


def fichier_verification(chemins: Chemins) -> Path:
    return chemins.caches / "verification_sources.json"


def _ecrire(chemin: Path, donnees: bytes) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_name(f".{chemin.name}.tmp")
    temporaire.write_bytes(donnees)
    os.chmod(temporaire, 0o600)
    os.replace(temporaire, chemin)
    return chemin


def construire_fiche(chemins: Chemins, aujourd_hui: dt.date | None = None) -> fiche.Fiche:
    registre = sources.charger()
    verification = fiche.lire_verification(fichier_verification(chemins), registre)
    return fiche.construire(infos.charger(chemins.infos_urgence), verification, registre, aujourd_hui)


def generer(chemins: Chemins, base: Base | None = None, aujourd_hui: dt.date | None = None) -> Sorties:
    f = construire_fiche(chemins, aujourd_hui)
    dossier = chemins.sorties
    s = Sorties(
        html=_ecrire(dossier / "Fiche urgence.html", fiche.html(f).encode("utf-8")),
        pdf=_ecrire(dossier / NOM_PDF, pdf.pdf(f)),
        carte=_ecrire(dossier / "Carte urgence A6.pdf", carte_a6.pdf(f)),
        ecran=None,
        icloud=None,
    )
    image = ecran_verrouille.image(f)
    if image is not None:
        s.ecran = _ecrire(dossier / "Ecran verrouille urgence.png", image)
    if f.infos.erreur:
        s.avertissements.append(f.infos.erreur)
    if f.infos.ecartes:
        s.avertissements.append(f"pas de données de santé sur la fiche : {', '.join(sorted(set(f.infos.ecartes)))}"
                                " écarté(s) (utilise la Fiche médicale de l'app Santé)")  # fmt: skip
    if chemins.icloud_drive.is_dir():
        chemins.icloud.mkdir(exist_ok=True)
        cible = chemins.icloud / NOM_PDF
        temporaire = chemins.icloud / f".{NOM_PDF}.tmp"
        shutil.copyfile(s.pdf, temporaire)
        os.replace(temporaire, cible)
        s.icloud = cible
    else:
        s.avertissements.append("iCloud Drive introuvable : la fiche n'a pas été copiée sur l'iPhone")
    if base is not None:
        base.ecrire_meta("fiche_generee_le", str(time.time()))
    return s


@dataclass
class ResultatVerification:
    reverif: sources.Reverification
    nouveaux_absents: list[str]


def verifier(chemins: Chemins, base: Base, notifieur: Notifieur, telecharger: sources.Telecharger | None = None,
             aujourd_hui: dt.date | None = None) -> ResultatVerification:  # fmt: skip
    registre = sources.charger()
    avant = fiche.lire_verification(fichier_verification(chemins), registre)
    r = sources.verifier_en_ligne(registre, telecharger) if telecharger else sources.verifier_en_ligne(registre)
    nouveaux: list[str] = []
    if r.pages_lues:
        jour = (aujourd_hui or dt.date.today()).isoformat()
        etat = {"date": jour, "confirmes": r.confirmes, "absents": r.absents, "injoignables": r.injoignables}
        _ecrire(fichier_verification(chemins), json.dumps(etat, ensure_ascii=False, indent=1).encode())
        nouveaux = [a for a in r.absents if a not in avant.absents]
        if nouveaux:
            noms = ", ".join(registre.element(a).libelle for a in nouveaux)
            notifieur.envoyer("urgence", "🆘 Fiche urgence : un numéro a changé",
                              f"Plus confirmé par sa source officielle, retiré de la fiche : {noms}.")  # fmt: skip
        generer(chemins, base, aujourd_hui)
    base.ecrire_meta("sources_verifiees_le", str(time.time()))
    log().info("revérification des numéros : %d confirmés, %d absents, %d injoignables (%d pages)",
               len(r.confirmes), len(r.absents), len(r.injoignables), r.pages_lues)  # fmt: skip
    return ResultatVerification(r, nouveaux)


def rappel(base: Base, notifieur: Notifieur, horloge: Callable[[], float] = time.time) -> bool:
    """Tous les 6 mois : « relis ta fiche urgence » (le premier rappel vient 6 mois après la première fiche)."""
    depuis = base.lire_meta("fiche_rappel_le")
    if depuis is None:
        base.ecrire_meta("fiche_rappel_le", str(horloge()))
        return False
    if horloge() - float(depuis) < SIX_MOIS_S:
        return False
    notifieur.envoyer("urgence", "🆘 Relis ta fiche urgence",
                      "Six mois ont passé : vérifie tes contacts (bouclier urgence editer). Les numéros officiels"
                      " sont revérifiés automatiquement.")  # fmt: skip
    base.ecrire_meta("fiche_rappel_le", str(horloge()))
    return True
