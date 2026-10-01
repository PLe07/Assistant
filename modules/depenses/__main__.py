"""Le dossier « Reçus » surveillé (python assistant.py activer depenses).

Toutes les 30 s, une photo nouvelle (ou un PDF) déposée dans le dossier est traitée : une notification
dit ce qui a été ajouté (mode réel) ou ce qui l'aurait été (mode test). Tes photos ne sont jamais
déplacées ni supprimées : chacune est reconnue à son empreinte, et n'est traitée qu'une fois.
"""

import time

from core.cerveau import ClaudeIndisponible
from core.module import executer
from core.notifications import notifier
from modules.depenses import parametres as p
from modules.depenses import recu


def nouveaux_fichiers(dossier, vus: dict, echecs: dict) -> list:
    """Les photos pas encore traitées, dont la copie est finie (AirDrop…), les plus anciennes d'abord."""
    fichiers = []
    for f in dossier.iterdir():
        if not f.is_file() or f.name.startswith(".") or f.suffix.lower() not in p.EXTENSIONS:
            continue
        if time.time() - f.stat().st_mtime < p.STABLE_SECONDES or echecs.get(f.name, 0) >= p.ESSAIS_MAX:
            continue
        if recu.empreinte(f) not in vus:
            fichiers.append(f)
    return sorted(fichiers, key=lambda f: f.stat().st_mtime)


def boucle(ctx) -> None:
    echecs: dict[str, int] = {}
    annonce = None
    while True:
        dossier = p.dossier_recus()
        dossier.mkdir(parents=True, exist_ok=True)
        if dossier != annonce:
            ctx.log.info("Dossier des reçus surveillé (mode %s)", p.mode())
            annonce = dossier
        for f in nouveaux_fichiers(dossier, recu.deja_vus(), echecs):
            if ctx.arret.is_set():
                return
            try:
                r = recu.traiter(f, "dossier")
            except ClaudeIndisponible:
                echecs[f.name] = echecs.get(f.name, 0) + 1  # on réessaiera (3 fois au plus)
                break  # Claude en pause ou indisponible : inutile d'essayer les suivantes maintenant
            # prive : le montant et le commerçant ne sont écrits ni dans le journal ni dans l'état
            notifier("Assistant", r["message"], module="depenses", urgent=True, prive=True)
        if ctx.attendre(max(5, int(ctx.reglage("toutes_les_secondes", 30)))):
            return


if __name__ == "__main__":
    executer("depenses", boucle)
