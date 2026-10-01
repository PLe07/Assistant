"""L'écoute : enchaîne découpage → transcription → déclencheur → Claude → 💡.

CONFIDENTIALITÉ
- Le son n'existe qu'en mémoire, le temps d'une phrase, puis il est oublié.
- Le texte transcrit n'est jamais écrit sur le disque ni dans le journal.
- Seul l'extrait déclencheur (2 phrases au plus) part à Claude, et seulement après un déclencheur.
- Cet extrait reste en mémoire vive (30 min max) pour rédiger l'aide si tu cliques sur 💡 ;
  l'arrêt du module (pause micro, pause globale) l'efface aussitôt.
"""

import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from core import etat
from core.cerveau import ClaudeIndisponible
from core.notifications import notifier
from modules.oreilles import aide
from modules.oreilles import parametres as p
from modules.oreilles.declencheurs import Detecteur, lire_perso
from modules.oreilles.transcription import Transcripteur


class Ecoute:
    def __init__(self, log, test: bool = False, avec_claude: bool = False, afficher=print,
                 transcripteur=None, detecteur=None):
        self.log, self.test, self.avec_claude, self.afficher = log, test, avec_claude, afficher
        self.transcripteur = transcripteur or Transcripteur(p.reglage("modele_transcription", "small"))
        self.detecteur = detecteur or Detecteur()
        self.extraits: dict[int, tuple[str, float]] = {}  # id d'aide → (extrait, instant) : MÉMOIRE VIVE
        self.verrou = threading.Lock()
        self.precedente = ("", 0.0)
        self.verifications: deque = deque()
        self.claude = ThreadPoolExecutor(max_workers=1)  # Claude réfléchit pendant qu'on continue d'écouter
        self.demandes_en_cours: set[int] = set()
        self.fini = False  # arrêt demandé : plus aucune nouvelle aide

    # --- une phrase entendue ------------------------------------------------------

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
        if self.test:
            self.afficher(f"   ⚡ déclencheur « {d.type} »")
            if self.avec_claude:
                self.afficher("   … Claude réfléchit")
                self._decider(extrait, d.type)
            return
        niveau = p.niveau()
        if niveau == 0:
            return  # proactivité « muet » : on n'appelle même pas Claude
        if d.type != "mot_appel":
            maintenant = time.time()
            while self.verifications and maintenant - self.verifications[0] > 3600:
                self.verifications.popleft()
            if len(self.verifications) >= p.VERIFICATIONS_PAR_HEURE[niveau]:
                self.log.info("Déclencheur « %s » ignoré : limite de vérifications par heure atteinte", d.type)
                return
            self.verifications.append(maintenant)
        self.claude.submit(self._decider, extrait, d.type)

    def _decider(self, extrait: str, type_: str) -> None:
        try:
            decision = aide.decider(extrait)
        except ClaudeIndisponible as e:
            if self.test:
                self.afficher(f"   ⛔ {e}")
            return  # déjà noté dans le journal par le cerveau
        except Exception as e:
            self.log.error("Vérification « puis-je aider ? » impossible (%s)", type(e).__name__)
            return
        niveau = p.niveau()
        seuil = p.SEUIL_MOT_APPEL if type_ == "mot_appel" else (p.SEUIL_CONFIANCE[niveau] or 101)
        retenue = decision.aide_possible and decision.confiance >= seuil
        if self.test:
            self.afficher(f"   🤖 Claude : {'aide possible' if decision.aide_possible else 'pas d’aide utile'} "
                          f"(confiance {decision.confiance}) « {decision.titre} »"
                          f" → {'serait proposée 💡' if retenue else 'rien'}")
            return
        # Le journal ne contient jamais ce que tu as dit, seulement ce qui s'est passé.
        self.log.info("Déclencheur « %s » → Claude : %s (confiance %d)", type_,
                      "aide proposée" if retenue else "pas d'aide utile", decision.confiance)
        if not retenue or self.fini:
            return
        id_aide = etat.proposer_aide("oreilles", decision.titre)
        with self.verrou:
            self.extraits[id_aide] = (extrait, time.time())
        notifier("Assistant", f"💡 {decision.titre} — clique sur 💡 en haut de l'écran", module="oreilles")

    # --- les aides demandées depuis l'icône ------------------------------------------------

    def servir_demandes(self) -> None:
        for a in etat.aides_demandees("oreilles"):
            if a["id"] in self.demandes_en_cours:
                continue
            with self.verrou:
                extrait = self.extraits.get(a["id"])
            if extrait is None:
                etat.finir_aide(a["id"], "Cette aide a expiré (le micro a été coupé ou elle date de plus de 30 min).", "expiree")
                continue
            self.demandes_en_cours.add(a["id"])
            self.claude.submit(self._rediger, a["id"], extrait[0], a["titre"])

    def _rediger(self, id_aide: int, extrait: str, titre: str) -> None:
        try:
            etat.finir_aide(id_aide, aide.rediger(extrait, titre), "prete")
            self.log.info("Aide rédigée à ta demande")
        except ClaudeIndisponible as e:
            etat.finir_aide(id_aide, f"Aide indisponible pour l'instant : {e}", "echec")
        except Exception as e:  # jamais le texte entendu dans le journal : seulement le type d'erreur
            self.log.error("Rédaction de l'aide impossible (%s)", type(e).__name__)
            etat.finir_aide(id_aide, "Aide indisponible : erreur inattendue (voir le journal).", "echec")
        finally:
            self.demandes_en_cours.discard(id_aide)

    def oublier(self, tout: bool = False) -> None:
        """Oublie les extraits trop vieux (ou tous), et purge les vieilles aides de l'état."""
        maintenant = time.time()
        with self.verrou:
            for id_aide, (_, quand) in list(self.extraits.items()):
                if tout or maintenant - quand > p.DUREE_VIE_EXTRAIT:
                    del self.extraits[id_aide]
        if tout:
            self.precedente = ("", 0.0)
        if not self.test:
            etat.purger_aides(maintenant - p.DUREE_VIE_AIDE)

    def arreter(self) -> None:
        self.fini = True
        self.claude.shutdown(wait=False, cancel_futures=True)
        self.oublier(tout=True)
        if not self.test:
            etat.expirer_aides("oreilles", "Cette aide a expiré : le micro a été coupé entre-temps.")
