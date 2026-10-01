"""L'écoute : enchaîne découpage → transcription → déclencheur → Claude → 💡.

CONFIDENTIALITÉ
- Le son n'existe qu'en mémoire, le temps d'une phrase, puis il est oublié.
- Le texte transcrit n'est jamais écrit sur le disque ni dans le journal, SAUF ce que tu adresses
  à l'Assistant avec le mot d'appel (« Assistant, … ») : ça entre dans ta mémoire (core/memoire.py).
- Seul l'extrait déclencheur (2 phrases au plus) part à Claude, et seulement après un déclencheur.
- Cet extrait reste en mémoire vive (30 min max) pour rédiger l'aide si tu cliques sur 💡 ;
  l'arrêt du module (pause micro, pause globale) l'efface aussitôt.
La mécanique des 💡 (Claude, limites, mémoire vive) est dans core/aides.py.
"""

import time

from core import consignes, etat, memoire, rappels
from core.aides import SEUIL_CONFIANCE, Assistance, niveau
from core.cerveau import ClaudeIndisponible
from core.notifications import notifier
from modules.oreilles import aide
from modules.oreilles import parametres as p
from modules.oreilles.declencheurs import Detecteur, lire_perso, retirer_mot_appel
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
        if d.type == "mot_appel":
            demande = retirer_mot_appel(texte, p.reglage("mot_appel", "assistant"))
            genre = consignes.classer(demande)
            if genre in ("rappel", "note", "souvenir"):
                self.consigne(genre, demande)
                return
            if not self.test:
                memoire.noter("parole", demande, "oreilles")  # ce que tu lui demandes entre dans ta mémoire
            self.soumettre(extrait, d.type, demande=True)
        elif d.type == "rappel":
            self.proposer_rappel(extrait)
        else:
            self.soumettre(extrait, d.type)

    # --- « Assistant, rappelle-moi… / note que… / qu'est-ce que je t'avais dit… » -----------------

    def consigne(self, genre: str, demande: str) -> None:
        if self.test:
            self.afficher({"rappel": "   ⏰ demande de rappel", "note": "   📝 demande de note",
                           "souvenir": "   🧠 question à ta mémoire"}[genre])
            if genre == "note":
                self.afficher(f"   → serait noté dans ta mémoire : « {consignes.contenu_note(demande)} »")
            elif genre == "souvenir":
                self.afficher(f"   → {len(memoire.chercher(consignes.SOUVENIR.sub(' ', demande)))} souvenir(s) trouvé(s)"
                              " dans ta mémoire" + ("" if self.avec_claude else " (avec --avec-claude : la réponse)"))
            if self.avec_claude and genre == "rappel":
                self._essai_rappel(demande, direct=True)
            elif self.avec_claude and genre == "souvenir":
                self.afficher("   … Claude réfléchit")
                self.afficher(f"   🧠 {consignes.repondre(demande, 'essai', module='oreilles', garder=False)}")
            elif genre == "rappel":
                self.afficher("   → Claude comprendrait quoi et quand (avec --avec-claude : le rappel compris)")
            return
        memoire.noter_intention("oreilles", genre, "", "demande")
        self.claude.submit(self._consigne, genre, demande)

    def _consigne(self, genre: str, demande: str) -> None:
        try:
            if genre == "note":
                consignes.noter(demande, "oreilles")
            elif genre == "rappel":
                if consignes.rappeler(demande, "oreilles", module="oreilles") is None:
                    memoire.noter("parole", demande, "oreilles")  # pas un rappel, finalement : la 💡 habituelle
                    self._decider(demande, "mot_appel", True, "")
            else:
                reponse = consignes.repondre(demande, "oreilles", module="oreilles")
                id_aide = etat.proposer_aide("memoire", f"🧠 {demande[:70]}")
                etat.finir_aide(id_aide, reponse, "prete")
                notifier("Assistant", "🧠 Ta réponse est prête : icône en haut à droite → « 💡 Aides »",
                         module="memoire", urgent=True)
        except Exception as e:  # jamais le contenu dans le journal : seulement le type d'erreur
            self.log.error("Demande « %s » impossible (%s)", genre, type(e).__name__)

    # --- « pense à… » entendu sans le mot d'appel : une 💡 propose de créer le rappel --------------

    def proposer_rappel(self, extrait: str) -> None:
        if self.test:
            self.afficher("   ⚡ déclencheur « rappel »")
            if self.avec_claude:
                self._essai_rappel(extrait, direct=False)
            return
        if self.spontane_permis("rappel"):
            self.claude.submit(self._proposer_rappel, extrait)

    def _proposer_rappel(self, extrait: str) -> None:
        try:
            r = rappels.comprendre(extrait, module="oreilles")
        except ClaudeIndisponible:
            return  # déjà noté dans le journal par le cerveau
        except Exception as e:
            self.log.error("Rappel : compréhension impossible (%s)", type(e).__name__)
            return
        retenu = r is not None and r.confiance >= (SEUIL_CONFIANCE[niveau()] or 101)
        self.log.info("Déclencheur « rappel » → Claude : %s (confiance %d)",
                      "rappel proposé" if retenu else "pas de rappel", r.confiance if r else 0)
        if retenu:
            self.proposer_action(f"Créer le rappel {r.decrire()} ?"[:90], lambda: rappels.creer(r, "oreilles"),
                                 "rappel", r.confiance)
        else:
            memoire.noter_intention("oreilles", "rappel", "", "rien", r.confiance if r else 0)

    def _essai_rappel(self, phrase: str, direct: bool) -> None:
        self.afficher("   … Claude réfléchit")
        try:
            r = rappels.comprendre(phrase, module="oreilles")
        except ClaudeIndisponible as e:
            self.afficher(f"   ⛔ {e}")
            return
        if r is None:
            self.afficher("   🤖 Claude : pas un rappel → rien")
        elif direct:
            self.afficher(f"   ⏰ Claude : rappel {r.decrire()} → serait créé (confiance {r.confiance})")
        else:
            seuil = SEUIL_CONFIANCE[niveau()] or 101
            self.afficher(f"   ⏰ Claude : rappel {r.decrire()} (confiance {r.confiance})"
                          f" → {'serait proposé 💡' if r.confiance >= seuil else 'rien'}")

    def oublier(self, tout: bool = False) -> None:
        super().oublier(tout)
        if tout:
            self.precedente = ("", 0.0)
