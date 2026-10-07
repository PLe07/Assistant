"""La surveillance de Gmail (n°20), en lecture seule absolue : les nouveaux messages de la Boîte de réception.

- Au premier passage, Bouclier note où en est ta boîte et n'analyse pas l'ancien courrier.
- Ensuite, chaque nouveau message (par UID) est lu sans être marqué comme lu (BODY.PEEK, 5 Mo au plus), analysé en
  local ; l'IA n'est consultée que si le score local hésite (20 à 80).
- Une notification seulement si le verdict final est « Arnaque » ou « Très suspect » (dans la limite de 3 par jour,
  jamais la nuit). Tout reste dans l'historique (caviardé).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bouclier.arnaque import analyse, extraction
from bouclier.arnaque.signaux import Niveau
from bouclier.comptes.imap_lecture_seule import LecteurImap
from bouclier.db import Base
from bouclier.journal import log
from bouclier.notifier import Notifieur

CLE = "surveillance"
TAILLE_MAX = 5_000_000


@dataclass
class Releve:
    premier_passage: bool = False
    analyses: int = 0
    alertes: list[str] = field(default_factory=list)


def relever(lecteur: LecteurImap, base: Base, outils: analyse.Outils, notifieur: Notifieur,
            max_par_tour: int = 30) -> Releve:  # fmt: skip
    _, validite = lecteur.examiner("INBOX")
    ligne = base.cx.execute("SELECT uidvalidity, dernier_uid FROM gmail WHERE dossier = ?", (CLE,)).fetchone()
    r = Releve()
    if ligne is None or ligne["uidvalidity"] != validite:
        uids = lecteur.uids_depuis(0)
        with base.transaction() as cx:
            cx.execute("INSERT OR REPLACE INTO gmail(dossier, uidvalidity, dernier_uid) VALUES (?, ?, ?)",
                       (CLE, validite, max(uids, default=0)))  # fmt: skip
        r.premier_passage = True
        return r
    dernier = int(ligne["dernier_uid"])
    for uid in lecteur.uids_depuis(dernier)[:max_par_tour]:
        brut = lecteur.message(uid, TAILLE_MAX)
        if brut:
            message = extraction.depuis_eml(brut)
            resultat = analyse.verifier(message, outils, "gmail")
            r.analyses += 1
            if resultat.verdict.niveau.value >= Niveau.TRES_SUSPECT.value:
                domaine = message.expediteur_adresse.rsplit("@", 1)[-1] if "@" in message.expediteur_adresse else "?"
                titre, corps = resultat.reponse.notification()
                notifieur.envoyer("gmail", titre, f"Mail de {domaine} : {corps}")
                r.alertes.append(titre)
        with base.transaction() as cx:
            cx.execute("UPDATE gmail SET dernier_uid = ? WHERE dossier = ?", (uid, CLE))
    if r.analyses:
        log().info("Gmail : %d nouveau(x) message(s) analysé(s), %d alerte(s)", r.analyses, len(r.alertes))
    return r
