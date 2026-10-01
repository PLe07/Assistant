"""L'observation : fenêtre au premier plan → exclusions → capture → texte → déclencheur → Claude → 💡.

CONFIDENTIALITÉ
- Seule la fenêtre au premier plan est capturée, jamais les applis et sites exclus.
- L'image n'existe qu'en mémoire, le temps de lire son texte, puis elle est jetée.
- Le texte lu n'est jamais écrit sur le disque ni dans le journal (seulement le nom de l'appli).
- Seul un extrait (1 500 caractères au plus, données sensibles masquées) part à Claude, et seulement
  après un déclencheur ou ta demande. Il reste en mémoire vive 30 min au plus.
La mécanique des 💡 (Claude, limites, mémoire vive) est dans core/aides.py.
"""

import time

from core import etat
from core.aides import Assistance
from modules.yeux import aide
from modules.yeux import parametres as p
from modules.yeux.capture import TERMINAUX, Capteur
from modules.yeux.declencheurs import Detecteur, lire_perso
from modules.yeux.filtres import exclue, extrait


class Observation(Assistance):
    message_expiration = "Cette aide a expiré : l'écran a été coupé entre-temps."

    def __init__(self, log, test: bool = False, avec_claude: bool = False, afficher=print,
                 capteur=None, detecteur=None):
        super().__init__("yeux", log, test=test, avec_claude=avec_claude, afficher=afficher)
        self.capteur = capteur or Capteur()
        self.detecteur = detecteur or Detecteur()
        self.capture_en_echec = False

    def decider(self, extrait_):
        return aide.decider(extrait_)

    def rediger(self, extrait_, titre):
        return aide.rediger(extrait_, titre)

    def _lire(self, fenetre: dict) -> list[str] | None:
        lignes = self.capteur.lire(fenetre)
        if lignes is None and not self.capture_en_echec:
            self.log.warning("Capture de la fenêtre impossible (%s) : autorisation ou version de macOS ?", fenetre["appli"])
        self.capture_en_echec = lignes is None
        return lignes

    # --- un coup d'œil -------------------------------------------------------------------

    def regarder(self) -> None:
        f = self.capteur.fenetre()
        if f is None:
            return
        raison = exclue(f, p.applis_exclues(), p.titres_exclus())
        if raison:
            if self.test:
                self.afficher(f"🙈 {f['appli']} : {raison}, rien n'est capturé")
            return
        if self.test and f["appli"] in TERMINAUX:  # il se lirait lui-même
            self.afficher(f"·  {f['appli']} ignoré pendant le test : passe sur la fenêtre à tester")
            return
        lignes = self._lire(f)
        if lignes is None:
            return
        etat.ecrire("yeux_regard", time.time())  # pour « assistant.py etat » (jamais ce qui a été vu)
        declenchements = self.detecteur.analyser(f"{f['appli']}|{f['titre']}", lignes, lire_perso(p.FICHIER_DECLENCHEURS))
        if self.test:
            attente = ", ".join(f"{t} dans {s} s" for t, s in self.detecteur.en_cours()) or "aucun signal"
            self.afficher(f"👁  {f['appli']} · {len(lignes)} lignes lues · {attente}")
        for d in declenchements:
            texte = f"Signal repéré : {d.type}\n{extrait(f, lignes, d.lignes, p.EXTRAIT_MAX)}"
            if not self.test and p.mode() == "journal":
                self.log.info("[mode journal] Aurait déclenché « %s » (%s) : Claude n'est pas appelé", d.type, f["appli"])
                continue
            self.soumettre(texte, d.type, lieu=f["appli"])

    # --- « M'aider avec cet écran » (bouton de l'icône) -------------------------------------------

    def servir_captures(self) -> None:
        for a in etat.aides_a_capturer(self.module):
            f = self.capteur.fenetre()
            if f is None:
                etat.finir_aide(a["id"], "Je n'ai trouvé aucune fenêtre à regarder.", "echec")
                continue
            raison = exclue(f, p.applis_exclues(), p.titres_exclus())
            if raison:
                etat.finir_aide(a["id"], f"Je n'ai rien capturé : {raison}. C'est voulu, pour ta vie privée.", "echec")
                continue
            lignes = self._lire(f)
            if not lignes:
                etat.finir_aide(a["id"], "Je n'ai pas pu lire de texte dans cette fenêtre.", "echec")
                continue
            self.garder_extrait(a["id"], f"Demande d'aide sur l'écran\n{extrait(f, lignes, None, p.EXTRAIT_MAX)}")
            etat.preparer_aide(a["id"], f"Aide sur : {f['appli']}")
            self.log.info("Aide demandée sur l'écran (%s)", f["appli"])
