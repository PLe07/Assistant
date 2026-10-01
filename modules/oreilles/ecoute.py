"""L'écoute : enchaîne découpage → transcription → déclencheur → Claude → 💡.

CONFIDENTIALITÉ
- Le son n'existe qu'en mémoire, le temps d'une phrase, puis il est oublié.
- Le texte transcrit n'est jamais écrit sur le disque ni dans le journal.
- Seul l'extrait déclencheur (2 phrases au plus) part à Claude, et seulement après un déclencheur.
- Cet extrait reste en mémoire vive (30 min max) pour rédiger l'aide si tu cliques sur 💡 ;
  l'arrêt du module (pause micro, pause globale) l'efface aussitôt.
La mécanique des 💡 (Claude, limites, mémoire vive) est dans core/aides.py.
"""

import time

from core.aides import Assistance
from modules.oreilles import aide
from modules.oreilles import parametres as p
from modules.oreilles.declencheurs import Detecteur, lire_perso
from modules.oreilles.transcription import Transcripteur


class Ecoute(Assistance):
    message_expiration = "Cette aide a expiré : le micro a été coupé entre-temps."

    def __init__(self, log, test: bool = False, avec_claude: bool = False, afficher=print,
                 transcripteur=None, detecteur=None):
        super().__init__("oreilles", log, test=test, avec_claude=avec_claude, afficher=afficher)
        self.transcripteur = transcripteur or Transcripteur(p.reglage("modele_transcription", "small"))
        self.detecteur = detecteur or Detecteur()
        self.precedente = ("", 0.0)

    def decider(self, extrait):
        return aide.decider(extrait)

    def rediger(self, extrait, titre):
        return aide.rediger(extrait, titre)

    def traiter_phrase(self, audio) -> None:
        texte = self.transcripteur.transcrire(audio)
        del audio  # le son est oublié
        if not texte:
            return
        if self.test:
            self.afficher(f"📝 « {texte} »")
        texte_avant, quand_avant = self.precedente
        self.precedente = (texte, time.time())
        d = self.detecteur.analyser(texte, p.reglage("mode", "passif"), p.reglage("mot_appel", "assistant"),
                                    lire_perso(p.FICHIER_DECLENCHEURS))
        if d is None:
            if self.test:
                self.afficher("   · rien de détecté")
            return
        contexte = texte_avant if time.time() - quand_avant < 30 else ""
        extrait = f"{contexte} {texte}".strip()[-400:]
        self.soumettre(extrait, d.type, demande=d.type == "mot_appel")

    def oublier(self, tout: bool = False) -> None:
        super().oublier(tout)
        if tout:
            self.precedente = ("", 0.0)
