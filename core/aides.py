"""La mécanique des 💡, commune aux modules qui proposent de l'aide (oreilles, yeux…).

1. Un déclencheur LOCAL est franchi → soumettre() : Haiku (rapide) répond « puis-je aider
   concrètement ? », sans rédiger l'aide.
2. Si oui : 💡 dans le menu de l'icône + notification. L'extrait reste en MÉMOIRE VIVE
   (30 min au plus) : il n'est jamais écrit sur le disque.
3. Tu cliques sur 💡 → servir_demandes() : Sonnet (fort) rédige l'aide.

Ce que TU demandes (« Assistant, … », bouton de l'icône) passe toujours, sauf la pause.
Ce qui vient de lui suit le niveau de proactivité : seuil de confiance et nombre de
vérifications par heure.
"""

import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from core import config, etat
from core.cerveau import ClaudeIndisponible, demander
from core.notifications import notifier

SEUIL_CONFIANCE = {0: None, 1: 90, 2: 80, 3: 70}  # confiance minimale de Claude pour te proposer une aide
VERIFICATIONS_PAR_HEURE = {0: 0, 1: 2, 2: 4, 3: 8}  # « puis-je aider ? » spontanés au maximum par heure
SEUIL_DEMANDE = 50  # tu t'adresses à lui : on est moins exigeant
DUREE_VIE_EXTRAIT = 30 * 60  # l'extrait (mémoire vive uniquement) est oublié après 30 min
DUREE_VIE_AIDE = 2 * 3600  # une aide disparaît du menu après 2 h

SCHEMA_DECISION = {
    "type": "object",
    "properties": {
        "aide_possible": {"type": "boolean"},
        "confiance": {"type": "integer", "minimum": 0, "maximum": 100},
        "titre": {"type": "string"},
    },
    "required": ["aide_possible", "confiance", "titre"],
    "additionalProperties": False,
}


@dataclass
class Decision:
    aide_possible: bool
    confiance: int
    titre: str


def decider(message: str, systeme: str, module: str) -> Decision:
    """« Puis-je aider ? » posé au modèle rapide, réponse en JSON."""
    r = demander(message, module=module, systeme=systeme, schema=SCHEMA_DECISION, modele="rapide")
    d = r.donnees or {}
    confiance = d.get("confiance") if isinstance(d.get("confiance"), int) else 0
    titre = str(d.get("titre", "")).strip()[:80] or "Une aide possible"
    return Decision(d.get("aide_possible") is True, max(0, min(100, confiance)), titre)


def rediger(message: str, systeme: str, module: str) -> str:
    return demander(message, module=module, systeme=systeme, modele="fort").texte.strip()


def niveau() -> int:
    return config.charger()["niveau_proactivite"]


class Assistance:
    """À hériter par un module : il fournit decider(extrait) et rediger(extrait, titre)."""

    message_expiration = "Cette aide a expiré : le module a été coupé entre-temps."

    def __init__(self, module: str, log, test: bool = False, avec_claude: bool = False, afficher=print):
        self.module, self.log, self.test, self.avec_claude, self.afficher = module, log, test, avec_claude, afficher
        self.extraits: dict[int, tuple[str, float]] = {}  # id d'aide → (extrait, instant) : MÉMOIRE VIVE
        self.verrou = threading.Lock()
        self.verifications: deque = deque()
        self.claude = ThreadPoolExecutor(max_workers=1)  # Claude réfléchit pendant que le module continue
        self.demandes_en_cours: set[int] = set()
        self.fini = False  # arrêt demandé : plus aucune nouvelle aide

    def decider(self, extrait: str) -> Decision:
        raise NotImplementedError

    def rediger(self, extrait: str, titre: str) -> str:
        raise NotImplementedError

    # --- un déclencheur local vient d'être franchi --------------------------------------

    def soumettre(self, extrait: str, type_: str, demande: bool = False, lieu: str = "") -> None:
        """demande=True : c'est toi qui t'adresses à lui (« Assistant, … »)."""
        if self.test:
            self.afficher(f"   ⚡ déclencheur « {type_} »")
            if self.avec_claude:
                self.afficher("   … Claude réfléchit")
                self._decider(extrait, type_, demande, lieu)
            return
        n = niveau()
        if not demande:
            if n == 0:
                return  # proactivité « muet » : il ne prend aucune initiative, Claude n'est pas appelé
            maintenant = time.time()
            while self.verifications and maintenant - self.verifications[0] > 3600:
                self.verifications.popleft()
            if len(self.verifications) >= VERIFICATIONS_PAR_HEURE[n]:
                self.log.info("Déclencheur « %s » ignoré : limite de vérifications par heure atteinte", type_)
                return
            self.verifications.append(maintenant)
        self.claude.submit(self._decider, extrait, type_, demande, lieu)

    def _decider(self, extrait: str, type_: str, demande: bool, lieu: str) -> None:
        try:
            decision = self.decider(extrait)
        except ClaudeIndisponible as e:
            if self.test:
                self.afficher(f"   ⛔ {e}")
            return  # déjà noté dans le journal par le cerveau
        except Exception as e:
            self.log.error("Vérification « puis-je aider ? » impossible (%s)", type(e).__name__)
            return
        seuil = SEUIL_DEMANDE if demande else (SEUIL_CONFIANCE[niveau()] or 101)
        retenue = decision.aide_possible and decision.confiance >= seuil
        if self.test:
            self.afficher(f"   🤖 Claude : {'aide possible' if decision.aide_possible else 'pas d’aide utile'} "
                          f"(confiance {decision.confiance}) « {decision.titre} »"
                          f" → {'serait proposée 💡' if retenue else 'rien'}")
            return
        # Le journal dit ce qui s'est passé, jamais ce que tu as dit ou ce qui était affiché.
        self.log.info("Déclencheur « %s »%s → Claude : %s (confiance %d)", type_, f" ({lieu})" if lieu else "",
                      "aide proposée" if retenue else "pas d'aide utile", decision.confiance)
        if not retenue or self.fini:
            return
        id_aide = etat.proposer_aide(self.module, decision.titre)
        with self.verrou:
            self.extraits[id_aide] = (extrait, time.time())
        # Ce que tu as demandé passe même en heures silencieuses (jamais pendant la pause).
        notifier("Assistant", f"💡 {decision.titre} — clique sur 💡 en haut de l'écran", module=self.module,
                 urgent=demande)

    # --- les aides demandées depuis l'icône ------------------------------------------------

    def garder_extrait(self, id_aide: int, extrait: str) -> None:
        with self.verrou:
            self.extraits[id_aide] = (extrait, time.time())

    def servir_demandes(self) -> None:
        for a in etat.aides_demandees(self.module):
            if a["id"] in self.demandes_en_cours:
                continue
            with self.verrou:
                extrait = self.extraits.get(a["id"])
            if extrait is None:
                etat.finir_aide(a["id"], "Cette aide a expiré (module coupé entre-temps, ou elle date de plus de 30 min).",
                                "expiree")
                continue
            self.demandes_en_cours.add(a["id"])
            self.claude.submit(self._rediger, a["id"], extrait[0], a["titre"])

    def _rediger(self, id_aide: int, extrait: str, titre: str) -> None:
        try:
            etat.finir_aide(id_aide, self.rediger(extrait, titre), "prete")
            self.log.info("Aide rédigée à ta demande")
        except ClaudeIndisponible as e:
            etat.finir_aide(id_aide, f"Aide indisponible pour l'instant : {e}", "echec")
        except Exception as e:  # jamais le contenu dans le journal : seulement le type d'erreur
            self.log.error("Rédaction de l'aide impossible (%s)", type(e).__name__)
            etat.finir_aide(id_aide, "Aide indisponible : erreur inattendue (voir le journal).", "echec")
        finally:
            self.demandes_en_cours.discard(id_aide)

    def oublier(self, tout: bool = False) -> None:
        """Oublie les extraits trop vieux (ou tous), et purge les vieilles aides de l'état."""
        maintenant = time.time()
        with self.verrou:
            for id_aide, (_, quand) in list(self.extraits.items()):
                if tout or maintenant - quand > DUREE_VIE_EXTRAIT:
                    del self.extraits[id_aide]
        if not self.test:
            etat.purger_aides(maintenant - DUREE_VIE_AIDE)

    def arreter(self) -> None:
        self.fini = True
        self.claude.shutdown(wait=False, cancel_futures=True)
        self.oublier(tout=True)
        if not self.test:
            etat.expirer_aides(self.module, self.message_expiration)
