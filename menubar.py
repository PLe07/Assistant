"""L'icône de contrôle dans la barre du haut de macOS.

    python menubar.py

🟢 tout va bien · 🎙 micro ouvert · 👁 écran observé · 💡 une aide t'attend · ⏸ en pause
· ⚠️ un module a un problème · ⚪ superviseur arrêté.
Le menu permet de tout mettre en pause, de couper le micro ou l'écran d'un clic, et de demander
de l'aide sur la fenêtre que tu as sous les yeux. Quitter l'icône
n'arrête PAS l'assistant : pour ça, utilise « Tout mettre en pause ».
"""

import subprocess
import time

import rumps

from core import config, etat
from core.journal import FICHIER as JOURNAL
from core.journal import journal

log = journal("icone")

PAUSE = "⏸  Tout mettre en pause"
REPRENDRE = "▶️  Reprendre"
COUPER_MICRO = "🎙  Couper le micro"
RALLUMER_MICRO = "🎙  Rallumer le micro (coupé)"
COUPER_ECRAN = "👁  Couper l'écran"
RALLUMER_ECRAN = "👁  Rallumer l'écran (coupé)"
AIDE_ECRAN = "👁  M'aider avec cet écran"
SYMBOLES_AIDE = {"proposee": "💡", "demandee": "⏳", "a_capturer": "⏳", "prete": "✅"}


def _cacher_du_dock() -> None:
    """Une icône de barre de menu ne doit pas apparaître dans le Dock."""
    try:
        from AppKit import NSBundle

        NSBundle.mainBundle().infoDictionary()["LSUIElement"] = "1"
    except Exception:  # sans conséquence : l'icône marche quand même
        pass


def _au_premier_plan() -> None:
    """Une icône de barre de menu n'est jamais l'appli « active » : sans ça, ses fenêtres
    (l'aide de Claude…) peuvent s'ouvrir cachées derrière les autres."""
    try:
        from AppKit import NSApplication

        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        pass


class Icone(rumps.App):
    def __init__(self):
        super().__init__("Assistant", title="⚪", quit_button=None)
        self.ligne_etat = rumps.MenuItem("…")
        self.ligne_jour = rumps.MenuItem("…")
        self.bouton_pause = rumps.MenuItem(PAUSE, callback=self.basculer_pause)
        self.bouton_micro = rumps.MenuItem(COUPER_MICRO, callback=self.basculer_micro)
        self.bouton_ecran = rumps.MenuItem(COUPER_ECRAN, callback=self.basculer_ecran)
        # rumps ne crée un sous-menu qu'au premier élément ajouté, et ne sait pas vider un sous-menu
        # qui n'existe pas encore : on en met un tout de suite (sinon « Aides » et « Modules » restent grisés).
        self.aides = rumps.MenuItem("💡 Aides")
        self.aides.add(rumps.MenuItem("(aucune pour l'instant)"))
        self.sous_menu = rumps.MenuItem("Modules")
        self.sous_menu.add(rumps.MenuItem("…"))
        self.derniere_erreur = ""
        self.attendues: set[int] = set()  # aides demandées depuis l'icône, en cours de rédaction
        self.menu = [
            self.ligne_etat,
            self.ligne_jour,
            None,
            self.bouton_pause,
            self.bouton_micro,
            self.bouton_ecran,
            None,
            rumps.MenuItem(AIDE_ECRAN, callback=self.aide_ecran),
            self.aides,
            self.sous_menu,
            rumps.MenuItem("Notification de test", callback=self.test_notif),
            rumps.MenuItem("Ouvrir le journal", callback=self.ouvrir_journal),
            None,
            rumps.MenuItem("Quitter l'icône (l'assistant continue)", callback=rumps.quit_application),
        ]
        self.minuteur = rumps.Timer(self.rafraichir, 2)
        self.minuteur.start()

    def rafraichir(self, _=None) -> None:
        try:
            self._rafraichir()
        except Exception as e:  # jamais en silence : une erreur de l'icône est notée (une fois) dans le journal
            if str(e) != self.derniere_erreur:
                self.derniere_erreur = str(e)
                log.exception("Icône : mise à jour impossible")

    def _rafraichir(self) -> None:
        try:
            r = etat.resume()
        except Exception as e:  # l'icône ne doit jamais planter
            self.title = "⚠️"
            self.ligne_etat.title = f"État illisible : {e}"
            return
        self.title = r["icone"]
        if r["pause"]:
            self.ligne_etat.title = "En pause : rien ne tourne"
        elif not r["superviseur_actif"]:
            self.ligne_etat.title = "Superviseur arrêté"
        else:
            actifs = sum(1 for m in r["modules"] if m["statut"] == "actif")
            alertes = (["micro muet"] if r["micro_muet"] else []) + (
                ["écran non autorisé" if r["ecran_alerte"] == "autorisation" else "capture impossible"]
                if r["ecran_alerte"] else [])  # le pourquoi du ⚠️ (détail : python assistant.py etat)
            self.ligne_etat.title = f"Actif · {actifs} module(s) en marche" + (f" · ⚠️ {', '.join(alertes)}" if alertes else "")
        envoyees, _ = r["notifications"]
        appels, plafond, _, _ = r["claude"]
        self.ligne_jour.title = f"Aujourd'hui : {envoyees} notif · Claude {appels}/{plafond}"
        self.bouton_pause.title = REPRENDRE if r["pause"] else PAUSE
        self.bouton_micro.title = RALLUMER_MICRO if r["pause_micro"] else COUPER_MICRO
        self.bouton_ecran.title = RALLUMER_ECRAN if r["pause_ecran"] else COUPER_ECRAN

        self.aides.title = f"💡 Aides ({len(r['aides'])} à lire)" if r["aides"] else "💡 Aides"
        self.aides.clear()
        for a in r["aides"]:
            item = rumps.MenuItem(f"{SYMBOLES_AIDE.get(a['statut'], '💡')} {a['titre']}", callback=self.ouvrir_aide)
            item.id_aide = a["id"]
            self.aides.add(item)
        if r["aides"]:
            self.aides.add(rumps.MenuItem("Effacer ces aides", callback=self.effacer_aides))
        else:
            self.aides.add(rumps.MenuItem("(aucune pour l'instant)"))

        self.sous_menu.clear()
        for m in r["modules"] or [{"nom": "(superviseur arrêté)", "statut": "", "detail": ""}]:
            texte = f"{m['nom']} : {m['statut']}" + (f" ({m['detail'][:60]})" if m.get("detail") else "")
            self.sous_menu.add(rumps.MenuItem(texte))

        # En dernier : la fenêtre d'une aide attend que tu la fermes, le menu doit être à jour avant.
        for a in etat.aides_recentes(time.time() - 2 * 3600):  # une aide demandée vient d'être rédigée ?
            if a["id"] in self.attendues and a["statut"] in ("prete", "echec", "expiree"):
                self.attendues.discard(a["id"])
                self.afficher_aide(a)

    def basculer_pause(self, _) -> None:
        pause = not config.charger()["pause_globale"]
        config.mettre_en_pause(pause)
        log.info("Pause %s depuis l'icône", "activée" if pause else "levée")
        self.rafraichir()

    def basculer_micro(self, _) -> None:
        coupe = not config.charger()["pause_micro"]
        config.mettre_capteur_en_pause("micro", coupe)
        log.info("Micro %s depuis l'icône", "coupé" if coupe else "rallumé")
        self.rafraichir()

    def basculer_ecran(self, _) -> None:
        coupe = not config.charger()["pause_ecran"]
        config.mettre_capteur_en_pause("ecran", coupe)
        log.info("Écran %s depuis l'icône", "coupé" if coupe else "rallumé")
        self.rafraichir()

    def aide_ecran(self, _) -> None:
        """La fenêtre que tu as sous les yeux est lue par le module « yeux », puis Claude t'aide."""
        r = etat.resume()
        yeux = next((m for m in r["modules"] if m["nom"] == "yeux"), None)
        if r["pause"] or r["pause_ecran"] or yeux is None or yeux["statut"] != "actif":
            _au_premier_plan()
            rumps.alert(title="👁 Les yeux ne sont pas actifs",
                        message="L'écran est coupé, en pause ou le module « yeux » est désactivé.\n"
                                "Pour l'activer :  python assistant.py activer yeux", ok="Fermer")
            return
        self.attendues.add(etat.demander_capture("yeux"))  # la fenêtre de l'aide s'ouvrira toute seule
        log.info("Aide demandée sur l'écran depuis l'icône")
        self.rafraichir()

    def ouvrir_aide(self, item) -> None:
        a = next((x for x in etat.aides_recentes(time.time() - 2 * 3600) if x["id"] == item.id_aide), None)
        if a is None:
            return
        if a["statut"] == "prete":
            self.afficher_aide(a)
        elif a["statut"] == "proposee" and etat.demander_aide(a["id"]):
            self.attendues.add(a["id"])  # Claude rédige ; la fenêtre s'ouvrira toute seule
            item.title = f"⏳ {a['titre']} (je prépare l'aide…)"

    def afficher_aide(self, a: dict) -> None:
        etat.marquer_vue(a["id"])
        texte = a["texte"] or "(aucun texte)"
        _au_premier_plan()
        if rumps.alert(title=f"💡 {a['titre']}", message=texte, ok="Fermer", cancel="Copier") == 0:
            subprocess.run(["pbcopy"], input=texte, text=True)

    def effacer_aides(self, _) -> None:
        for a in etat.aides_recentes(time.time() - 2 * 3600):
            etat.marquer_vue(a["id"])
        self.rafraichir()

    def test_notif(self, _) -> None:
        from core.notifications import notifier

        affichee, raison = notifier("Assistant", "Notification de test ✅", test=True)
        if not affichee:
            _au_premier_plan()
            rumps.alert("Notification non affichée", raison)

    def ouvrir_journal(self, _) -> None:
        subprocess.run(["open", "-a", "Console", str(JOURNAL)])


if __name__ == "__main__":
    import fcntl
    import sys

    config.DONNEES.mkdir(exist_ok=True)
    verrou = open(config.DONNEES / "icone.verrou", "w")
    try:
        fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("L'icône tourne déjà : regarde en haut à droite de l'écran.")
        sys.exit(0)
    _cacher_du_dock()
    Icone().run()
