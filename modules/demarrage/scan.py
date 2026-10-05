"""Le scan : chaque collecteur tourne seul (une panne le rend « dégradé », jamais tout le scan), puis les fiches
sont complétées par launchd (S6), les signatures, l'app parente et sa dernière utilisation.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import PurePosixPath
from typing import Any

from modules.demarrage.collecteurs import (
    agents_globaux,
    agents_utilisateur,
    apple,
    applications,
    apps_embarquees,
    extensions,
    helpers,
    launchd_etat,
    ouverture_session,
    planifie,
    shell,
)
from modules.demarrage.collecteurs.applications import Index
from modules.demarrage.collecteurs.launchd_etat import EtatLaunchd
from modules.demarrage.collecteurs.plists import app_parente, est_systeme
from modules.demarrage.fichiers import absent_certain
from modules.demarrage.modele import Collecteur, Fiche, Inventaire, identifiant
from modules.demarrage.signatures import CacheSignatures, dernieres_utilisations, signer
from modules.demarrage.systeme import Systeme

log = logging.getLogger("demarrage")

PREFIXE_MOI = "com.assistant."
PREFIXE_TESTS = "com.assistant.nettoyeur.test."  # les éléments de test du bout en bout : jugés comme les autres
# Ce que launchd charge pour toi sans que ce soit un élément de démarrage : apps ouvertes à la main, XPC anonymes.
_EPHEMERES = ("application.", "anonymous.", "com.apple.")
_DOMAINE = {
    "agent_utilisateur": "gui", "agent_global": "gui", "agent_app": "gui", "ouverture_app": "gui", "launchd": "gui",
    "daemon_global": "system", "daemon_app": "system",
}  # fmt: skip
DETAILS_MAX = 60  # appels « launchctl print » par scan, au plus


def _proteger(nom: str, fn: Callable[[], tuple[list[Fiche], list[str]]]) -> tuple[list[Fiche], Collecteur]:
    debut = time.perf_counter()
    try:
        fiches, erreurs = fn()
    except Exception as e:  # un collecteur cassé ne casse pas le scan
        log.exception("[demarrage] collecteur %s en panne", nom)
        return [], Collecteur(nom, "indisponible", f"{type(e).__name__} : {e}")
    detail = " ; ".join(erreurs)
    etat = "dégradé" if erreurs else "ok"
    c = Collecteur(nom, etat, detail, len(fiches))
    log.debug("[demarrage] %s : %d fiche(s) en %.2f s", nom, len(fiches), time.perf_counter() - debut)
    return fiches, c


def domaine(f: Fiche) -> str:
    return str(f.details.get("domaine") or _DOMAINE.get(f.source, "gui"))


def appliquer_launchd(fiches: list[Fiche], etat: EtatLaunchd) -> None:
    """Chargé ? PID ? Désactivé ? Actif au prochain démarrage ?"""
    for f in fiches:
        if f.source in ("cron", "extension", "ouverture"):
            continue
        dom = domaine(f)
        services = etat.gui if dom == "gui" else etat.systeme
        lisible = etat.gui_lisible if dom == "gui" else etat.systeme_lisible
        service = services.get(f.label)
        f.charge = (service is not None) if lisible else None
        if service and service.pid:
            f.pids = [service.pid]
        if service and service.dernier_code is not None:
            f.details["dernier_code"] = service.dernier_code
        surcharges = etat.desactives_gui if dom == "gui" else etat.desactives_systeme
        if f.label in surcharges:
            f.desactive = surcharges[f.label]
        elif f.desactive is None:
            f.desactive = False if lisible else None
        if f.source in ("agent_app", "daemon_app", "ouverture_app"):
            # Embarqué : actif seulement si l'app l'a enregistré auprès de launchd (ou des Réglages, vu en S5).
            f.actif = bool(f.charge) and not f.desactive if f.charge is not None else None
        else:
            f.actif = not f.desactive if f.desactive is not None else None


def inconnus_charges(systeme: Systeme, fiches: list[Fiche], etat: EtatLaunchd) -> list[Fiche]:
    """Les labels que launchd a chargés dans ta session sans qu'on ait trouvé leur fichier (S6)."""
    connus = {f.label for f in fiches}
    nouveaux: list[Fiche] = []
    for label, service in sorted(etat.gui.items()):
        if label in connus or label.startswith(_EPHEMERES) or len(nouveaux) >= DETAILS_MAX:
            continue
        d = launchd_etat.detail(systeme, f"gui/{systeme.uid}", label)
        f = Fiche(id=identifiant("launchd", label), label=label, source="launchd", charge=True, desactive=False)
        f.actif = True
        f.pids = [service.pid] if service.pid else []
        if d:
            f.programme, f.chemin_plist = d.programme, d.chemin
            f.app_parente, aide = app_parente(systeme, d.programme, d.chemin)
            if aide:
                f.details["app_aide"] = aide
            if d.relances is not None:
                f.details["relances"] = d.relances
        nouveaux.append(f)
    return nouveaux


def marquer_doublons(fiches: list[Fiche]) -> None:
    par_label: dict[str, list[Fiche]] = defaultdict(list)
    for f in fiches:
        if (
            f.chemin_plist or f.source == "launchd"
        ):  # un assistant (S8) qui porte le nom de son daemon n'est pas un doublon
            par_label[f.label].append(f)
    for groupe in par_label.values():
        if len(groupe) < 2:
            continue
        for f in groupe:
            f.doublon = True
        par_id: dict[str, list[Fiche]] = defaultdict(list)
        for f in groupe:
            par_id[f.id].append(f)
        for meme in par_id.values():
            if len(meme) > 1:  # même source et même label : on distingue par le fichier
                for f in meme:
                    f.id = identifiant(f.source, f.label, f.chemin_plist or f.programme or "")


def appliquer_apps(fiches: list[Fiche], index: Index) -> None:
    """L'app parente (par AssociatedBundleIdentifiers si le chemin ne la donne pas), et celles qui ont disparu."""
    for f in fiches:
        if f.est_apple:
            continue
        if f.app_parente and f.programme_existe is False and index.par_chemin(f.app_parente) is None:
            f.app_attendue_absente = True
            nom = PurePosixPath(f.app_parente).name
            ailleurs = next((a for a in index.apps if PurePosixPath(a.chemin).name == nom), None)
            if ailleurs:  # l'app a été déplacée : la fiche pointe encore vers l'ancien endroit
                f.details["app_deplacee_vers"] = ailleurs.chemin
        if f.bundles_associes:
            presentes = [a for a in (index.par_bundle(b) for b in f.bundles_associes) if a]
            if presentes and not f.app_parente:
                f.app_parente = presentes[0].chemin
            if not presentes:
                f.app_attendue_absente = True
                f.details["apps_attendues"] = f.bundles_associes


def appliquer_signatures(systeme: Systeme, fiches: list[Fiche], cache: CacheSignatures, delai: float) -> None:
    a_signer = [f for f in fiches if not f.est_apple and f.programme and f.programme_existe]
    signatures = signer(systeme, [f.programme for f in a_signer if f.programme], cache, delai)
    for f in a_signer:
        assert f.programme is not None
        sig = signatures.get(f.programme)
        if sig is None:
            continue
        f.signature, f.editeur, f.equipe = sig.etat, sig.editeur, sig.equipe
        if sig.autorite:
            f.details["autorite"] = sig.autorite
        apple_signe = sig.etat == "apple"
        fiche_apple = f.label.startswith("com.apple.") or f.source in ("ouverture", "ouverture_app")
        if apple_signe and fiche_apple and not f.interprete:
            f.est_apple = True
        elif apple_signe:
            # Un programme de macOS (curl, caffeinate…) lancé par la fiche d'un tiers : la fiche n'est pas d'Apple.
            f.details["programme_systeme"] = True
            f.editeur = None
        if f.label.startswith("com.apple.") and not apple_signe:
            f.details["se_dit_apple"] = True  # se fait passer pour Apple sans signature Apple : à vérifier
    for f in fiches:
        if not f.est_apple and f.interprete and est_systeme(f.interprete) and f.signature == "inconnue":
            f.details["script"] = True


def appliquer_extensions(fiches: list[Fiche]) -> None:
    """Une extension système n'est activée que signée et notarisée : son équipe suffit, et si une autre fiche de la
    même équipe nomme l'éditeur, on le reprend."""
    par_equipe = {f.equipe: f.editeur for f in fiches if f.equipe and f.editeur}
    for f in fiches:
        if f.source == "extension" and f.equipe:
            f.signature = "developpeur"
            f.editeur = par_equipe.get(f.equipe)


def appliquer_utilisations(systeme: Systeme, fiches: list[Fiche], delai: float) -> None:
    apps = sorted({f.app_parente for f in fiches if f.app_parente and not f.est_apple})
    dates = dernieres_utilisations(systeme, apps, delai)
    for f in fiches:
        if f.app_parente in dates:
            f.derniere_utilisation_app = dates[f.app_parente]


def appliquer_relances(systeme: Systeme, fiches: list[Fiche]) -> None:
    """Pour ceux que KeepAlive relance : combien de fois, et avec quel dernier code (boucle de plantages ?)."""
    candidats = [f for f in fiches if not f.est_apple and f.declencheurs.garder_en_vie and f.charge]
    for f in candidats[:DETAILS_MAX]:
        d = launchd_etat.detail(systeme, f"gui/{systeme.uid}" if domaine(f) == "gui" else "system", f.label)
        if d is None:
            continue
        if d.relances is not None:
            f.details["relances"] = d.relances
        if d.dernier_code is not None:
            f.details["dernier_code"] = d.dernier_code


def scanner(
    systeme: Systeme,
    reglages: dict[str, Any],
    cache: CacheSignatures | None = None,
    apps_vues_au_demarrage: list[str] | None = None,
) -> Inventaire:
    """apps_vues_au_demarrage : les apps lancées juste après l'ouverture de session (S5, en dernier recours)."""
    cache = cache if cache is not None else CacheSignatures()
    delais = reglages["delais"]
    inventaire = Inventaire(ts=systeme.maintenant())
    index = Index()

    def indexer() -> tuple[list[Fiche], list[str]]:
        nonlocal index
        index = applications.indexer(systeme)
        return [], []

    etapes: list[tuple[str, Callable[[], tuple[list[Fiche], list[str]]]]] = [
        ("apps", indexer),
        ("S1", lambda: agents_utilisateur.collecter(systeme)),
        ("S2", lambda: agents_globaux.collecter(systeme)),
        ("S3", lambda: apple.collecter(systeme)),
        ("S4", lambda: apps_embarquees.collecter(systeme, index)),
    ]
    for nom, fn in etapes:
        fiches, statut = _proteger(nom, fn)
        inventaire.fiches += fiches
        if nom != "apps" or statut.etat != "ok":
            inventaire.collecteurs.append(statut)

    etat = EtatLaunchd()

    def s6() -> tuple[list[Fiche], list[str]]:
        nonlocal etat
        etat = launchd_etat.collecter(systeme, delais["commande_s"])
        appliquer_launchd(inventaire.fiches, etat)
        return inconnus_charges(systeme, inventaire.fiches, etat), etat.erreurs

    fiches, statut = _proteger("S6", s6)
    inventaire.fiches += fiches
    inventaire.collecteurs.append(statut)

    def s5() -> tuple[list[Fiche], list[str]]:
        r = ouverture_session.collecter(
            systeme, index, inventaire.fiches, apps_vues_au_demarrage, delais["osascript_s"]
        )
        return r.fiches, r.erreurs

    def s10() -> tuple[list[Fiche], list[str]]:
        inventaire.shell, erreurs = shell.collecter(systeme)
        return [], erreurs

    for nom, fn in [
        ("S5", s5),
        ("S7", lambda: extensions.collecter(systeme)),
        ("S8", lambda: helpers.collecter(systeme, inventaire.fiches)),
        ("S9", lambda: planifie.collecter(systeme)),
        ("S10", s10),
    ]:
        fiches, statut = _proteger(nom, fn)
        inventaire.fiches += fiches
        inventaire.collecteurs.append(statut)

    for f in inventaire.fiches:
        f.c_est_moi = f.label.startswith(PREFIXE_MOI) and not f.label.startswith(PREFIXE_TESTS)
        if f.programme_existe is False:
            f.details["absent_certain"] = absent_certain(systeme, f.programme)
    marquer_doublons(inventaire.fiches)
    for nom, fn2 in [
        ("apps parentes", lambda: appliquer_apps(inventaire.fiches, index)),
        ("signatures", lambda: appliquer_signatures(systeme, inventaire.fiches, cache, delais["codesign_s"])),
        ("relances", lambda: appliquer_relances(systeme, inventaire.fiches)),
        ("extensions", lambda: appliquer_extensions(inventaire.fiches)),
        ("utilisation des apps", lambda: appliquer_utilisations(systeme, inventaire.fiches, delais["codesign_s"])),
    ]:
        try:
            fn2()
        except Exception as e:
            log.exception("[demarrage] étape %s en panne", nom)
            inventaire.collecteurs.append(Collecteur(nom, "dégradé", f"{type(e).__name__} : {e}"))
    return inventaire
