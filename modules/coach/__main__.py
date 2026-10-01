"""Module « coach » : chaque jour à l'heure choisie (18:30 par défaut), tes questions de révision.

Sous le superviseur (python assistant.py activer coach) : à l'heure dite, la série du jour est
préparée et une notification discrète te le dit. Tu réponds quand tu veux :
    icône → « 🎓 Coach »,  python assistant.py coach,  ou « Assistant, interroge-moi ».
Les autres commandes : python assistant.py coach cours · coach bilan  (voir modules/coach/README.md)
"""

import sys
import time
from datetime import datetime

from core.cerveau import ClaudeIndisponible
from core.module import executer
from modules.coach import parametres as p
from modules.coach import seance

CLE = "coach_prepare"  # le jour où la série a été préparée et annoncée (une seule fois par jour)


def boucle(ctx) -> None:
    prochain_essai = 0.0
    while not ctx.attendre(30):
        heure = datetime.now().strftime("%H:%M")
        if not p.heure() <= heure < p.HEURE_LIMITE or ctx.etat.lire(CLE) == seance.aujourdhui():
            continue
        if time.time() < prochain_essai:
            continue
        try:
            seance.preparer()
        except ClaudeIndisponible as e:
            ctx.log.info("Coach : questions du jour pas prêtes (%s), nouvel essai dans 30 min", e)
            prochain_essai = time.time() + p.REESSAI
            continue
        except seance.PasDeCours as e:
            ctx.log.info("Coach : %s", e)
            ctx.notifier("Assistant", "🎓 Coach : je n'ai aucun cours pour t'interroger. Dépose-les ici : "
                                      "python assistant.py coach cours")
            ctx.etat.ecrire(CLE, seance.aujourdhui())
            continue
        ctx.etat.ecrire(CLE, seance.aujourdhui())
        e = seance.etat_du_jour()
        ctx.log.info("Coach : série du jour prête (%d question(s))", e["total"])
        if e["a_repondre"]:
            ctx.notifier("Assistant", f"🎓 Tes {e['a_repondre']} question(s) du jour sont prêtes : "
                                      "icône en haut à droite → « 🎓 Coach »")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print("Le coach se lance avec :  python assistant.py coach   (ou coach cours, coach bilan)")
        sys.exit(2)
    executer("coach", boucle)
