"""Le démon de Quotidien (LaunchAgent `com.<session>.quotidien`) : une boucle qui ne s'arrête jamais sur une erreur.

Toutes les 3 s : le battement (pour `doctor`) et l'entrée iCloud des raccourcis « Mon frigo » et « Envie de… »
(réponse en quelques secondes). Dans un fil à part, pour ne jamais retarder ces réponses :
- les tâches datées (`planification`) : brief 7 h 15, rappels de la veille 20 h, alerte météo 21 h, menu du dimanche ;
- toutes les 5 minutes : les anniversaires (rappels J-7, J-1, J, une seule fois chacun) ;
- une fois par jour : le ménage (réponses iCloud anciennes, messages prêts périmés).
Les réglages sont relus quand un fichier change. Une brique en panne est notée et retentée au tour suivant.
"""

from __future__ import annotations

import signal
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from quotidien import config, icloud, reseau
from quotidien.db import Base as BaseDonnees
from quotidien.journal import log
from quotidien.notifier import Notifieur
from quotidien.systeme import Systeme

PAS_S = 3.0
BATTEMENT_S = 30
ANNIVERSAIRES_S = 300
ANNUAIRE_S = 3600
VERIFICATION = "frigo-verification-"


@dataclass
class Composants:
    """Ce qui parle au monde extérieur (les tests en imitent chaque morceau)."""

    telecharger: Callable[..., Any] = reseau.telecharger
    fournisseur_contacts: Callable[[], tuple[str, list[dict[str, Any]]]] | None = None
    client_ia: Any = None


@dataclass
class Tour:
    fait: list[str] = field(default_factory=list)
    erreurs: list[str] = field(default_factory=list)


class Demon:
    def __init__(self, db: BaseDonnees, systeme: Systeme, horloge: Callable[[], float] = time.time,
                 composants: Composants | None = None,
                 ouvrir_base: Callable[[], BaseDonnees] | None = None) -> None:  # fmt: skip
        self.db, self.systeme, self.horloge = db, systeme, horloge
        self.c = composants or Composants()
        self.ouvrir_base = ouvrir_base or (lambda: BaseDonnees(config.chemin_base()))
        self.reveil = threading.Event()
        self._dernier_battement = float("-inf")
        self._reglages: tuple[tuple[Any, ...], config.Reglages] | None = None
        self._annuaire: tuple[float, Any] | None = None

    # --- Réglages (relus quand un fichier change) -----------------------------------------------------------------
    def reglages(self) -> config.Reglages:
        cle = tuple(_signature(config.dossier_support() / n) for n in ("profil.toml", "reglages.toml", "proches.toml"))
        if self._reglages is None or self._reglages[0] != cle:
            r = config.charger()
            for a in r.avertissements:
                log().warning("réglages : %s", a)
            self._reglages = (cle, r)
            self._annuaire = None
        return self._reglages[1]

    def notifieur(self, r: config.Reglages) -> Notifieur:
        return Notifieur(self.db, self.systeme, r.reglages, self.horloge)

    def heure_locale(self, r: config.Reglages) -> datetime:
        """L'heure qu'il est dans le fuseau des réglages (pas celui du Mac en voyage)."""
        return datetime.fromtimestamp(self.horloge(), ZoneInfo(r["lieu"]["fuseau"])).replace(tzinfo=None)

    def aujourdhui(self, r: config.Reglages) -> date:
        from quotidien import planification

        return planification.aujourdhui(self.horloge(), r.reglages)

    def annuaire(self, r: config.Reglages) -> Any:
        """Contacts + proches.toml, relus au plus une fois par heure (et quand un réglage change)."""
        from quotidien.anniversaires import service

        if self._annuaire is None or self.horloge() - self._annuaire[0] > ANNUAIRE_S:
            self._annuaire = (self.horloge(), service.annuaire(r, self.aujourdhui(r), self.c.fournisseur_contacts))
        return self._annuaire[1]

    # --- L'entrée iCloud des raccourcis ----------------------------------------------------------------------------
    def _frigo(self, r: config.Reglages, d: icloud.Demande) -> str:
        from quotidien.frigo import service
        from quotidien.repas.base import charger

        base = charger()
        garder = not d.id.startswith(VERIFICATION)  # la vérification de l'installation ne touche pas ton frigo
        if d.image:
            rep = service.depuis_photo(self.db, r, d.chemin, base, garder, self.horloge(), client=self.c.client_ia,
                                       lire_trousseau=self.systeme.trousseau_lire)  # fmt: skip
        else:
            rep = service.depuis_texte(self.db, r, d.texte(), base, garder, self.horloge())
        return service.formater(rep, base, court=True)

    def _envie(self, r: config.Reglages, d: icloud.Demande) -> str:
        from quotidien.repas import service

        return service.noter_envie(self.db, r, d.texte(), self.horloge(), client=self.c.client_ia,
                                   lire_trousseau=self.systeme.trousseau_lire)[1]  # fmt: skip

    def _entree(self, r: config.Reglages, t: Tour) -> None:
        n = icloud.traiter(self.db, {"frigo": lambda d: self._frigo(r, d), "envie": lambda d: self._envie(r, d)},
                           self.horloge())  # fmt: skip
        if n:
            t.fait.append(f"iCloud : {n} demande(s) des raccourcis")

    # --- Les tâches datées ----------------------------------------------------------------------------------------
    def _brief(self, r: config.Reglages) -> str:
        from quotidien import brief
        from quotidien.anniversaires import service as anniv

        jour = self.aujourdhui(r)
        a = self.annuaire(r)

        def ligne_anniv() -> str | None:
            return anniv.ligne_brief(a.personnes, jour, r.reglages["anniversaires"]["date_29_fevrier"])

        b = brief.produire(self.db, r, jour, self.horloge(), anniversaires=ligne_anniv,
                           meteo=lambda: _ligne_meteo(self.db, r, jour, self.horloge, self.c.telecharger))  # fmt: skip
        brief.publier(b)
        if b.lignes:
            self.notifieur(r).notifier("brief", "☀️ Ma journée", b.texte)
        self.db.ecrire_meta("brief:dernier", b.texte)
        return f"brief : {len(b.lignes)} ligne(s)"

    def _rappels_veille(self, r: config.Reglages) -> str:
        from quotidien.repas import planificateur as pl
        from quotidien.repas import rappels_veille
        from quotidien.repas.base import charger

        base = charger()
        jour = self.aujourdhui(r)
        menu = pl.menu_couvrant(self.db, jour + timedelta(days=1))
        if menu is None:
            return "rappels de la veille : pas de menu"
        profil, _ = pl.profil_depuis(r, base)
        textes = [x.texte for x in rappels_veille.rappels(menu, base, profil.jour_courses) if x.jour == jour]
        if textes:
            self.notifieur(r).notifier("veille", "🌙 Pour demain", "\n".join(textes))
        return f"rappels de la veille : {len(textes)}"

    def _alerte_meteo(self, r: config.Reglages) -> str:
        from quotidien.meteo import regles
        from quotidien.meteo import service as meteo

        jour = self.aujourdhui(r)
        prev = meteo.prevision(self.db, r, self.horloge, self.c.telecharger)
        tenue, _ = regles.charger_regles()
        texte = meteo.alerte_veille(prev, jour, r.profil, tenue) if prev is not None else None
        if texte:
            self.notifieur(r).notifier("alerte_meteo", "🌦️ Demain change", texte)
        return "alerte météo : " + ("envoyée" if texte else "rien à signaler")

    def _menu(self, r: config.Reglages) -> str:
        from quotidien import rappels_apple
        from quotidien.repas import service
        from quotidien.repas.base import charger

        base = charger()
        debut = service.semaine_affichee(r, self.heure_locale(r))
        resultat = service.produire(self.db, r, debut, base=base, maintenant=self.horloge())
        ajoutes = rappels_apple.synchroniser_courses(self.db, self.systeme, r.reglages, resultat.liste, base)
        cout = resultat.liste.total
        self.notifieur(r).notifier("menu", "🍽️ Menu de la semaine prêt",
                                   f"{len(resultat.menu.repas)} repas, courses ≈ {cout:.0f} € "
                                   f"({len(resultat.liste.articles)} articles"
                                   + (f", {ajoutes} dans Rappels" if ajoutes else "") + ").")  # fmt: skip
        return f"menu : semaine du {debut.isoformat()}"

    def _anniversaires(self, r: config.Reglages) -> str:
        from quotidien import rappels_apple
        from quotidien.anniversaires import service

        a = self.annuaire(r)
        ia_kwargs: dict[str, Any] = {"client": self.c.client_ia, "lire_trousseau": self.systeme.trousseau_lire}
        emis = service.emettre(self.db, r, self.systeme, a.personnes, self.horloge(), **ia_kwargs)
        jour = self.aujourdhui(r)
        elements = rappels_apple.elements_anniversaires(self.db, r.reglages, a.personnes, jour, self.horloge(),
                                                        **ia_kwargs)  # fmt: skip
        rappels = rappels_apple.Rappels(self.db, self.systeme, r.reglages)
        if elements:
            rappels.ajouter("anniversaires", elements)
        rappels.retirer_anniversaires_passes(jour)
        return f"anniversaires : {len(emis)} rappel(s)" if emis else ""

    def _menage(self) -> str:
        icloud.nettoyer(self.horloge())
        return ""

    def taches(self, r: config.Reglages) -> list[tuple[str, Callable[[], str], Any]]:
        """Les tâches à faire maintenant : (nom, action, échéance à noter ou None)."""
        from quotidien import planification

        actions: dict[str, Callable[[], str]] = {
            "brief": lambda: self._brief(r),
            "rappels_veille": lambda: self._rappels_veille(r),
            "alerte_meteo": lambda: self._alerte_meteo(r),
            "menu": lambda: self._menu(r),
        }
        dues: list[tuple[str, Callable[[], str], Any]] = [
            (e.tache, actions[e.tache], e) for e in planification.dues(self.db, r.reglages, self.horloge())
        ]
        if self._du("anniversaires", ANNIVERSAIRES_S):
            dues.append(("anniversaires", lambda: self._anniversaires(r), None))
        if self._du("menage", 86400):
            dues.append(("menage", self._menage, None))
        return dues

    def a_faire(self) -> bool:
        """Y a-t-il une tâche à lancer ? (sans ouvrir de fil ni de connexion pour rien toutes les 3 s)"""
        from quotidien import planification

        r = self.reglages()
        if planification.dues(self.db, r.reglages, self.horloge()):
            return True
        return self._du("anniversaires", ANNIVERSAIRES_S) or self._du("menage", 86400)

    def _du(self, nom: str, intervalle: float) -> bool:
        dernier = self.db.lire_meta(f"dernier:{nom}")
        return dernier is None or self.horloge() - float(dernier) >= intervalle

    # --- Les tours ------------------------------------------------------------------------------------------------
    def tour_rapide(self) -> Tour:
        t = Tour()
        if self.horloge() - self._dernier_battement >= BATTEMENT_S:
            self._dernier_battement = self.horloge()
            self.db.ecrire_meta("demon_battement", str(self._dernier_battement))
        r = self.reglages()
        try:
            self._entree(r, t)
        except Exception as e:  # noqa: BLE001 - une brique en panne n'arrête jamais la boucle
            t.erreurs.append(f"entrée iCloud : {e.__class__.__name__}")
            log().warning("entrée iCloud en échec (%s)", e.__class__.__name__)
        return t

    def tour_lent(self) -> Tour:
        from quotidien import planification

        t = Tour()
        r = self.reglages()
        for nom, action, echeance in self.taches(r):
            try:
                resultat = action()
            except Exception as e:  # noqa: BLE001 - retentée au prochain tour (et notée)
                t.erreurs.append(f"{nom} : {e.__class__.__name__}")
                log().warning("tâche %s en échec (%s)", nom, e.__class__.__name__)
                self.db.ecrire_meta(f"erreur:{nom}", f"{self.horloge()}|{e.__class__.__name__}")
                continue
            if echeance is not None:
                planification.noter(self.db, echeance, self.horloge(), resultat)
            else:
                self.db.ecrire_meta(f"dernier:{nom}", str(self.horloge()))
            if resultat:
                t.fait.append(resultat)
                log().info("%s", resultat)
        return t

    def tour(self) -> Tour:
        rapide, lent = self.tour_rapide(), self.tour_lent()
        return Tour(rapide.fait + lent.fait, rapide.erreurs + lent.erreurs)

    # --- La boucle ------------------------------------------------------------------------------------------------
    def _fil_lent(self) -> None:  # pragma: no cover - fil du vrai démon (le tour lent est testé directement)
        try:
            db = self.ouvrir_base()
        except Exception as e:  # noqa: BLE001
            log().warning("tour lent impossible : base illisible (%s)", e.__class__.__name__)
            return
        try:
            Demon(db, self.systeme, self.horloge, self.c, self.ouvrir_base).tour_lent()
        except Exception as e:  # noqa: BLE001
            log().warning("tour lent en échec (%s)", e.__class__.__name__)
        finally:
            db.fermer()

    def lancer(self, arret: threading.Event, max_tours: int | None = None) -> int:
        tours = 0
        fil: threading.Thread | None = None
        log().info("démon démarré")
        icloud.preparer_dossiers()
        while not arret.is_set():
            self.tour_rapide()
            if (fil is None or not fil.is_alive()) and self.a_faire():
                fil = threading.Thread(target=self._fil_lent, name="quotidien-taches", daemon=True)
                fil.start()
            tours += 1
            if max_tours is not None and tours >= max_tours:
                break
            self.reveil.wait(PAS_S)
            self.reveil.clear()
        if fil is not None:
            fil.join(timeout=30)
        log().info("démon arrêté")
        return tours


def _signature(chemin: Path) -> tuple[int, int] | None:
    try:
        st = chemin.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _ligne_meteo(db: BaseDonnees, r: config.Reglages, jour: date, horloge: Callable[[], float],
                 telecharger: Callable[..., Any]) -> str:  # fmt: skip
    from quotidien.meteo import service as meteo

    return meteo.du_jour(db, r, jour, horloge, telecharger).texte


def battement(db: BaseDonnees) -> float | None:
    valeur = db.lire_meta("demon_battement")
    return float(valeur) if valeur else None


def principal() -> int:  # pragma: no cover - lancé par launchd
    reseau.installer_garde()
    # Une erreur imprévue irait en clair dans le journal de launchd : seul son type est noté.
    sys.excepthook = lambda genre, *_: log().error("erreur imprévue : %s", genre.__name__)
    threading.excepthook = lambda a: log().error("erreur imprévue dans un fil : %s", a.exc_type.__name__)
    arret = threading.Event()
    demon = Demon(BaseDonnees(config.chemin_base()), Systeme())

    def arreter(*_: object) -> None:
        arret.set()
        demon.reveil.set()

    signal.signal(signal.SIGTERM, arreter)
    signal.signal(signal.SIGINT, arreter)
    return 0 if demon.lancer(arret) >= 0 else 1
