"""L'icône de contrôle dans la barre du haut de macOS.

    python menubar.py

🟢 tout va bien · 🎙 micro ouvert · 👁 écran observé · 💡 une aide t'attend · ⏸ en pause
· ⚠️ un module a un problème · ⚪ superviseur arrêté.
Le menu permet de tout mettre en pause, de couper le micro ou l'écran d'un clic, et de demander
de l'aide sur la fenêtre que tu as sous les yeux. Quitter l'icône
n'arrête PAS l'assistant : pour ça, utilise « Tout mettre en pause ».
"""

import subprocess
import threading
import time
from datetime import datetime

import rumps

from core import config, consignes, etat, memoire
from core.aides import texte_simple
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
NOTER = "✍️  Noter ou demander…"
CHERCHER = "🔎  Chercher dans ma mémoire…"
RECHERCHER = "🌐  Rechercher sur le web…"
BRIEF = "☀️  Mon brief"
COACH = "🎓  Coach"
VEILLE = "📰  Veille"
QUOI_DE_NEUF = "📰  Quoi de neuf ?"
REDACTEUR = "✒️  Rédacteur"
DEPENSES = "🧾  Dépenses"
# Ces modules écrivent eux-mêmes dans ta mémoire (ou n'y mettent rien), et leurs titres ont déjà leur symbole.
MODULES_AUTONOMES = ("memoire", "veille", "recherche", "redacteur", "depenses", "brief")
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


def _modale(ouvrir):
    """Ouvre une fenêtre devant toi. Tant qu'elle est ouverte, l'icône est figée (macOS) :
    c'est noté dans l'état, pour que « etat » et l'essai puissent te le dire."""
    _au_premier_plan()
    etat.ecrire("icone_fenetre", f"{time.time():.0f}")
    try:
        return ouvrir()
    finally:
        etat.effacer("icone_fenetre")


def _fenetre(*args, **kwargs) -> int:
    return _modale(lambda: rumps.alert(*args, **kwargs))


def _choisir_fichiers(message: str, extensions: list[str]) -> list[str]:
    """La fenêtre « Ouvrir » de macOS (plusieurs fichiers possibles). Renvoie les chemins choisis."""
    from AppKit import NSOpenPanel

    panneau = NSOpenPanel.openPanel()
    panneau.setMessage_(message)
    panneau.setAllowsMultipleSelection_(True)
    panneau.setCanChooseDirectories_(False)
    panneau.setAllowedFileTypes_(extensions)
    if _modale(panneau.runModal) != 1:
        return []
    return [str(u.path()) for u in panneau.URLs()]


def _saisie(titre: str, message: str, ok: str, annuler: str = "Annuler", hauteur: int = 60, defaut: str = "") -> str | None:
    """Une fenêtre avec une zone de texte. Renvoie le texte tapé (None si tu cliques « Annuler »)."""
    fenetre = rumps.Window(message=message, title=titre, default_text=defaut, ok=ok, cancel=annuler, dimensions=(380, hauteur))
    try:  # le curseur directement dans la zone de texte : tu tapes sans cliquer
        fenetre._alert.window().setInitialFirstResponder_(fenetre._textfield)
    except AttributeError:
        pass
    reponse = _modale(fenetre.run)
    return " ".join(str(reponse.text or "").split()) if reponse.clicked == 1 else None


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
        self.titre_note = ("", 0.0)  # ce que l'icône affiche, noté dans l'état (pour « etat » et l'essai)
        self.attendues: set[int] = set()  # aides demandées depuis l'icône, en cours de rédaction
        self.bouton_coach = self._menu_coach()
        self.coach_occupe = False  # le coach prépare tes questions
        self.coach_pret = None  # la séance prête : ses questions s'ouvrent au prochain rafraîchissement
        self.bouton_veille = self._menu_veille()
        self.bouton_redacteur = self._menu_redacteur()
        self.bouton_depenses = self._menu_depenses()
        self.veille_occupee = False  # la veille lit les sites et trie
        self.menu = [
            self.ligne_etat,
            self.ligne_jour,
            None,
            self.bouton_pause,
            self.bouton_micro,
            self.bouton_ecran,
            None,
            rumps.MenuItem(AIDE_ECRAN, callback=self.aide_ecran),
            rumps.MenuItem(BRIEF, callback=self.brief),
            rumps.MenuItem(NOTER, callback=self.noter),
            rumps.MenuItem(CHERCHER, callback=self.chercher),
            rumps.MenuItem(RECHERCHER, callback=self.rechercher),
            self.bouton_coach,
            self.bouton_veille,
            self.bouton_redacteur,
            self.bouton_depenses,
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
        if r["icone"] != self.titre_note[0] or time.time() - self.titre_note[1] > 10:
            etat.ecrire("icone_titre", f"{time.time():.0f}|{r['icone']}")
            self.titre_note = (r["icone"], time.time())
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

        self._titres_coach()
        self.bouton_veille.title = "⏳  Veille : je lis les sites…" if self.veille_occupee else VEILLE

        # En dernier : la fenêtre d'une aide attend que tu la fermes, le menu doit être à jour avant.
        if self.coach_pret:
            cle, self.coach_pret = self.coach_pret, None
            self._coach_questions(cle)
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
            _fenetre(title="👁 Les yeux ne sont pas actifs",
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
            log.info("Aide n°%d demandée depuis l'icône (💡)", a["id"])
            self.attendues.add(a["id"])  # Claude rédige ; la fenêtre s'ouvrira toute seule
            item.title = f"⏳ {a['titre']} (je prépare l'aide…)"

    def afficher_aide(self, a: dict) -> None:
        if a.get("statut") == "prete" and not a.get("vue") and a.get("module") not in MODULES_AUTONOMES:
            try:  # une aide que tu ouvres entre dans ta mémoire (les réponses du second cerveau y sont déjà)
                memoire.noter("aide", a["titre"], a["module"], detail=a["texte"])
            except Exception:
                log.exception("Mémoire : aide pas enregistrée")
        etat.marquer_vue(a["id"])
        texte = texte_simple(a["texte"]) or "(aucun texte)"
        liens = {"veille": ("Ouvrir les liens", self.veille_page), "recherche": ("Ouvrir les sources", self.recherche_page)}
        if a.get("module") in liens:  # le 2e bouton ouvre la page avec les liens cliquables
            libelle, ouvrir = liens[a["module"]]
            if _fenetre(title=a["titre"], message=texte, ok="Fermer", cancel=libelle) == 0:
                ouvrir(None)
        else:
            titre = a["titre"] if a.get("module") in ("redacteur", "depenses", "brief") else f"💡 {a['titre']}"
            if _fenetre(title=titre, message=texte, ok="Fermer", cancel="Copier") == 0:
                subprocess.run(["pbcopy"], input=texte, text=True)

    # --- Mémoire, rappels, second cerveau -----------------------------------------------------

    def noter(self, _) -> None:
        texte = _saisie("✍️ Noter ou demander",
                        "Une note (« le code du portail est… »), un rappel (« rappelle-moi demain à 9 h d'appeler "
                        "la banque »), une question à ta mémoire (« qu'est-ce que j'avais noté sur… ? ») ou une "
                        "recherche (« cherche sur internet le plafond du PEA »).",
                        ok="Envoyer")
        if not texte:
            return
        genre = consignes.classer(texte)
        if genre == "recherche":
            self._rechercher(texte)
        elif genre == "redaction":
            self._rediger(texte)
        elif genre in ("souvenir", "question"):  # la réponse s'ouvrira toute seule dans une fenêtre
            id_aide = etat.proposer_aide("memoire", f"🧠 {texte[:70]}")
            etat.demander_aide(id_aide)
            self.attendues.add(id_aide)
            log.info("Question au second cerveau depuis l'icône")
            threading.Thread(target=self._repondre, args=(id_aide, texte), daemon=True).start()
        elif genre == "rappel":  # Claude comprend quoi et quand : une notification confirme
            log.info("Rappel demandé depuis l'icône")
            threading.Thread(target=self._rappeler, args=(texte,), daemon=True).start()
        else:
            consignes.noter(texte, "icone")
        self.rafraichir()

    def _repondre(self, id_aide: int, question: str) -> None:
        try:
            etat.finir_aide(id_aide, consignes.repondre(question, "icone"), "prete")
        except Exception as e:
            log.exception("Second cerveau : réponse impossible")
            etat.finir_aide(id_aide, f"Réponse impossible : {type(e).__name__} (voir le journal).", "echec")

    def _rappeler(self, texte: str) -> None:
        try:
            if consignes.rappeler(texte, "icone") is None:  # finalement pas un rappel : gardé comme note
                consignes.noter(texte, "icone")
        except Exception:
            log.exception("Rappel impossible")

    def chercher(self, _) -> None:
        requete = _saisie("🔎 Chercher dans ma mémoire", "Un ou plusieurs mots (« dentiste », « banque rendez-vous »).",
                          ok="Chercher")
        if not requete:
            return
        trouves = memoire.chercher(requete, 8)
        log.info("Recherche dans la mémoire depuis l'icône (%d résultat(s))", len(trouves))
        if not trouves:
            _fenetre(title=f"🔎 « {requete} »", message="Rien trouvé dans ta mémoire.", ok="Fermer")
            return
        lignes = []
        for x in trouves:
            ligne = (f"{memoire.GENRES.get(x['genre'], '·')} {datetime.fromtimestamp(x['quand']):%d/%m %H:%M} "
                     f"(n° {x['id']}) · {x['texte'][:200]}")
            if x["detail"]:
                ligne += f"\n      {x['detail'][:300]}"
            lignes.append(ligne)
        if _fenetre(title=f"🔎 « {requete} » : {len(trouves)} souvenir(s)", message="\n\n".join(lignes),
                    ok="Fermer", cancel="Copier") == 0:
            subprocess.run(["pbcopy"], input="\n\n".join(lignes), text=True)

    # --- Recherche sourcée (phase 5) ----------------------------------------------------------------

    def rechercher(self, _) -> None:
        question = _saisie("🌐 Rechercher sur le web", "Ta question (« quel est le plafond du PEA en 2026 ? »). Claude "
                           "cherche sur le web et te répond en 5 lignes, avec ses sources (20 à 90 s).", ok="Rechercher")
        if question:
            self._rechercher(question)

    def _rechercher(self, question: str) -> None:
        """Claude cherche en fond ; la réponse s'ouvre toute seule (comme une aide 💡)."""
        id_aide = etat.proposer_aide("recherche", f"🌐 {question[:70]}")
        etat.demander_aide(id_aide)
        self.attendues.add(id_aide)
        log.info("Recherche sur le web demandée depuis l'icône")

        def chercher():
            from modules.recherche import recherche

            try:
                etat.finir_aide(id_aide, recherche.texte_resultat(recherche.chercher(question, "icone")), "prete")
            except Exception as e:  # jamais en silence : la fenêtre dit pourquoi
                log.info("Recherche impossible (%s)", type(e).__name__)
                etat.finir_aide(id_aide, f"Recherche impossible : {e}", "echec")

        threading.Thread(target=chercher, daemon=True).start()
        self.rafraichir()

    def recherche_page(self, _) -> None:
        from modules.recherche import parametres as rp

        if rp.PAGE.exists():
            subprocess.run(["open", str(rp.PAGE)], check=False)
        else:
            _fenetre(title="🌐 Pas encore de recherche", message="Lance d'abord : 🌐 Rechercher sur le web…", ok="Fermer")

    # --- Brief (phase 5) : agenda, mails à traiter, rappels ; sur ton Mac, sans Claude -------------

    def brief(self, _) -> None:
        from modules.brief import brief

        log.info("Brief demandé depuis l'icône")
        self._en_fond("brief", "☀️ Mon brief", brief.composer)

    # --- Rédacteur dans ta voix (phase 5) ---------------------------------------------------------

    def _menu_redacteur(self) -> rumps.MenuItem:
        menu = rumps.MenuItem(REDACTEUR)
        menu.add(rumps.MenuItem("✒️  Rédiger dans mon style…", callback=self.rediger))
        menu.add(None)
        menu.add(rumps.MenuItem("🎨  Faire ma fiche de style", callback=self.faire_style))
        menu.add(rumps.MenuItem("👤  Mon profil (lettres de motivation)", callback=self.ouvrir_profil))
        return menu

    def _en_fond(self, module: str, titre: str, travail) -> None:
        """Claude travaille en fond ; le résultat s'ouvre tout seul (comme une aide 💡), même un échec."""
        id_aide = etat.proposer_aide(module, titre)
        etat.demander_aide(id_aide)
        self.attendues.add(id_aide)

        def faire():
            try:
                etat.finir_aide(id_aide, travail(), "prete")
            except Exception as e:  # jamais en silence : la fenêtre dit pourquoi
                log.info("%s impossible (%s)", module, type(e).__name__)
                etat.finir_aide(id_aide, f"Impossible pour l'instant : {e}", "echec")

        threading.Thread(target=faire, daemon=True).start()
        self.rafraichir()

    def rediger(self, _) -> None:
        demande = _saisie("✒️ Rédiger dans mon style",
                          "Quoi écrire ? « mail à mon prof pour demander un délai d'une semaine », « lettre de "
                          "motivation pour l'alternance chargé de clientèle chez … » (colle l'annonce), « post "
                          "LinkedIn : j'ai validé l'UE11 ».", ok="Rédiger", hauteur=110)
        if demande:
            self._rediger(demande)

    def _rediger(self, demande: str) -> None:
        from modules.redacteur import redaction

        log.info("Brouillon demandé depuis l'icône")
        self._en_fond("redacteur", f"✒️ {demande[:70]}",
                      lambda: redaction.texte_brouillon(redaction.rediger(demande, "icone")))

    def faire_style(self, _) -> None:
        from modules.redacteur import parametres as rp
        from modules.redacteur import style

        if _fenetre(title="🎨 Ma fiche de style", message="Ton Mac lit tes 25 derniers mails envoyés (seulement ton texte) "
                    f"et les textes déposés dans {rp.MES_TEXTES}. Environ 6 000 caractères partent UNE fois à Claude, "
                    "qui décrit ta manière d'écrire et te montre un échantillon (20 à 40 s).",
                    ok="C'est parti", cancel="Annuler") != 1:
            return
        log.info("Fiche de style demandée depuis l'icône")
        self._en_fond("redacteur", "🎨 Ma fiche de style", lambda: style.texte_fiche(style.creer_fiche()))

    def ouvrir_profil(self, _) -> None:
        from modules.redacteur import parametres as rp
        from modules.redacteur import style

        style.creer_profil()
        subprocess.run(["open", "-e", str(rp.PROFIL)], check=False)

    # --- Dépenses (phase 5) -----------------------------------------------------------------------

    def _menu_depenses(self) -> rumps.MenuItem:
        menu = rumps.MenuItem(DEPENSES)
        menu.add(rumps.MenuItem("🧾  Ajouter un reçu…", callback=self.ajouter_recu))
        menu.add(rumps.MenuItem("📊  Mes dépenses du mois", callback=self.bilan_depenses))
        menu.add(None)
        menu.add(rumps.MenuItem("📂  Ouvrir le tableur", callback=self.ouvrir_tableur))
        menu.add(rumps.MenuItem("📁  Ouvrir le dossier Reçus", callback=self.ouvrir_recus))
        return menu

    def ajouter_recu(self, _) -> None:
        from modules.depenses import parametres as dp
        from modules.depenses import recu

        chemins = _choisir_fichiers("Choisis la photo (ou le PDF) de ton reçu", sorted(e[1:] for e in dp.EXTENSIONS))
        if not chemins:
            return
        log.info("Reçu(s) ajouté(s) depuis l'icône (%d)", len(chemins))
        self._en_fond("depenses", "🧾 Reçu" + (f"s ({len(chemins)})" if len(chemins) > 1 else ""),
                      lambda: "\n".join(recu.traiter(c, "icone")["message"] for c in chemins)
                      + ("\n\n(Mode test : rien n'est écrit. Pour de vrai :  python assistant.py depenses reel)"
                         if dp.mode() != "reel" else ""))

    def bilan_depenses(self, _) -> None:
        from modules.depenses import recu, tableur

        _fenetre(title="📊 Mes dépenses du mois", message=f"{tableur.texte_bilan(tableur.bilan())}\n\n{recu.resume_etat()}",
                 ok="Fermer")

    def ouvrir_tableur(self, _) -> None:
        from modules.depenses import parametres as dp

        if dp.TABLEUR.exists():
            subprocess.run(["open", str(dp.TABLEUR)], check=False)
        else:
            _fenetre(title="📂 Pas encore de tableur", message="Il est créé au premier reçu ajouté en mode réel "
                     "(python assistant.py depenses reel).", ok="Fermer")

    def ouvrir_recus(self, _) -> None:
        from modules.depenses import parametres as dp

        dp.dossier_recus().mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", str(dp.dossier_recus())], check=False)

    # --- Coach (phase 5) : seulement quand tu le demandes ---------------------------------------------

    def _menu_coach(self) -> rumps.MenuItem:
        """« 🎓 Coach » → les 13 UE du DCG, ton bilan, ta dernière correction, le dossier de tes cours."""
        from modules.coach import parametres as cp

        menu = rumps.MenuItem(COACH)
        self.items_ue = []
        for ue in cp.UE:
            item = rumps.MenuItem(ue, callback=self.coach_ue)
            item.ue = ue
            menu.add(item)
            self.items_ue.append(item)
        menu.add(None)
        menu.add(rumps.MenuItem("📊  Mon bilan", callback=self.coach_bilan))
        menu.add(rumps.MenuItem("📄  Revoir ma dernière correction", callback=self.coach_derniere))
        menu.add(rumps.MenuItem("📚  Ouvrir le dossier de mes cours", callback=self.coach_dossier))
        return menu

    def _titres_coach(self) -> None:
        from modules.coach import seance

        self.bouton_coach.title = "⏳  Coach : je prépare tes questions…" if self.coach_occupe else COACH
        etats = seance.etat_ue()
        for item in self.items_ue:
            revoir, pas_finie = etats.get(item.ue, (0, False))
            item.title = item.ue + (" · ⏸ séance pas finie" if pas_finie else f" · {revoir} à revoir" if revoir else "")

    def coach_ue(self, item) -> None:
        """Une UE choisie : la séance pas finie reprend, sinon « combien de questions ? » puis Claude prépare."""
        from modules.coach import parametres as cp
        from modules.coach import seance

        if self.coach_occupe:
            return
        cle = seance.en_cours(item.ue)
        if cle:
            self._coach_questions(cle)
            return
        reponse = _saisie(f"🎓 {item.ue}", f"Combien de questions ? (de {cp.MIN_QUESTIONS} à {cp.MAX_QUESTIONS})",
                          ok="C'est parti", hauteur=24, defaut=str(cp.PAR_DEFAUT))
        if reponse is None:
            return
        n = cp.nombre(reponse)
        log.info("Coach : séance demandée depuis l'icône (%d question(s))", n)
        self.coach_occupe = True
        self.bouton_coach.title = "⏳  Coach : je prépare tes questions…"
        threading.Thread(target=self._coach_preparer, args=(item.ue, n), daemon=True).start()

    def _coach_preparer(self, ue: str, n: int) -> None:
        from modules.coach import seance

        try:
            self.coach_pret = seance.preparer(ue, n)  # la clé de la séance : elle s'ouvre au rafraîchissement
        except Exception as e:  # Claude indisponible… : dit clairement, rien n'est perdu
            log.info("Coach : questions pas prêtes (%s)", e)
            from core.notifications import notifier

            notifier("Assistant", f"🎓 Coach : questions pas prêtes ({e})", module="coach", urgent=True)
        finally:
            self.coach_occupe = False

    def _coach_questions(self, cle: str) -> None:
        """Une fenêtre par question. « Plus tard » : tes réponses déjà données sont gardées."""
        from modules.coach import seance

        s_liste = seance.seance(cle)
        for s in [x for x in s_liste if x["statut"] == "posee"]:
            reponse = _saisie(f"🎓 Question {s['ordre']}/{len(s_liste)} · {s['matiere']}", seance.texte_question(s),
                              ok="Valider", annuler="Plus tard", hauteur=24 if s["type"] == "qcm" else 110)
            if reponse is None:
                break
            seance.repondre(s["seance"], reponse)
        else:
            self._coach_corriger(cle)
        self._titres_coach()  # le menu dit tout de suite ce qui reste

    def _coach_corriger(self, cle: str) -> None:
        """La correction se fait en fond ; sa fenêtre s'ouvre toute seule (comme une aide 💡)."""
        from modules.coach import seance

        id_aide = etat.proposer_aide("coach", "🎓 Correction")
        etat.demander_aide(id_aide)
        self.attendues.add(id_aide)

        def corriger():
            try:
                etat.finir_aide(id_aide, seance.texte_correction(seance.corriger(cle)), "prete")
            except Exception as e:
                log.info("Coach : correction impossible (%s)", e)
                etat.finir_aide(id_aide, f"Correction impossible pour l'instant : {e}\nTes réponses sont gardées : "
                                         "reclique sur la même UE plus tard.", "echec")

        threading.Thread(target=corriger, daemon=True).start()
        self.rafraichir()

    def coach_bilan(self, _) -> None:
        from modules.coach import seance

        _fenetre(title="📊 Mon bilan (coach DCG)", message=seance.texte_bilan(), ok="Fermer")

    def coach_derniere(self, _) -> None:
        from modules.coach import seance

        cle = seance.derniere()
        texte = seance.texte_correction(seance.seance(cle)) if cle else "Pas encore de séance."
        if _fenetre(title="📄 Ma dernière correction", message=texte, ok="Fermer", cancel="Copier") == 0:
            subprocess.run(["pbcopy"], input=texte, text=True)

    def coach_dossier(self, _) -> None:
        from modules.coach import cours
        from modules.coach import parametres as cp

        cours.creer_dossiers()
        subprocess.run(["open", str(cp.COURS)], check=False)

    # --- Veille (phase 5) : seulement quand tu la demandes ----------------------------------------------

    def _menu_veille(self) -> rumps.MenuItem:
        menu = rumps.MenuItem(VEILLE)
        menu.add(rumps.MenuItem(QUOI_DE_NEUF, callback=self.veille))
        menu.add(rumps.MenuItem("📄  Ouvrir la page de ma dernière veille", callback=self.veille_page))
        return menu

    def veille(self, _) -> None:
        """Lit les sites et trie en fond ; le résultat s'ouvre tout seul (comme une aide 💡)."""
        if self.veille_occupee:
            return
        self.veille_occupee = True
        id_aide = etat.proposer_aide("veille", "📰 Veille")
        etat.demander_aide(id_aide)
        self.attendues.add(id_aide)
        log.info("Veille demandée depuis l'icône")

        def lire():
            from modules.veille import revue

            try:
                etat.finir_aide(id_aide, revue.texte_revue(revue.lancer()), "prete")
            except Exception as e:  # jamais en silence : la fenêtre dit pourquoi
                log.exception("Veille impossible")
                etat.finir_aide(id_aide, f"Veille impossible : {e}", "echec")
            finally:
                self.veille_occupee = False

        threading.Thread(target=lire, daemon=True).start()
        self.rafraichir()

    def veille_page(self, _) -> None:
        from modules.veille import parametres as vp

        if vp.PAGE.exists():
            subprocess.run(["open", str(vp.PAGE)], check=False)
        else:
            _fenetre(title="📰 Pas encore de veille", message="Lance d'abord : 📰 Veille → Quoi de neuf ?", ok="Fermer")

    def effacer_aides(self, _) -> None:
        for a in etat.aides_recentes(time.time() - 2 * 3600):
            etat.marquer_vue(a["id"])
        self.rafraichir()

    def test_notif(self, _) -> None:
        from core.notifications import notifier

        affichee, raison = notifier("Assistant", "Notification de test ✅", test=True)
        if not affichee:
            _fenetre("Notification non affichée", raison)

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
    etat.effacer("icone_fenetre")  # une fenêtre restée ouverte quand l'icône a été arrêtée
    Icone().run()
