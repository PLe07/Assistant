"""La chaîne unique (§3) : quel que soit le chemin d'arrivée, un fichier de la file est
empreinte → doublon ? → extraction → classement local → Claude si besoin (§6) → destination → déplacement sûr →
tags, garantie, notification. Et l'inverse : annuler, corriger (et apprendre), suivre un déplacement à la main.

Rien n'est perdu : en cas d'erreur, l'original reste où il est (3 essais, puis « erreur » dans le journal).
"""

from __future__ import annotations

import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.journal import journal
from modules.trieur import base as base_
from modules.trieur import config, rangement, systeme
from modules.trieur.classement import Classement, classer, emetteurs, issue, nommage, regles, remplir
from modules.trieur.extraction import Extraction, extraire, image, ocr

log = journal("trieur")
ESSAIS_MAX = 3
# Une correction (ou un déplacement à la main) vaut un indice fort pour cet émetteur. Pas de points en moins pour
# l'ancien type : un même émetteur envoie souvent plusieurs types (factures et courriers d'EDF).
POINTS_APPRIS = 8.0
AUTOMATIQUES = ("boite", "a_trier", "telechargements", "airdrop")  # les entrées surveillées (pas une demande)
TYPE_DES_CATEGORIES = {"facture_service": "abonnement", "releve_bancaire": "banque", "sante": "sante",
                       "assurance": "assurance", "billet_transport": "transport", "reservation": "hebergement",
                       "ticket_caisse": "supermarche", "facture_achat": "commerce"}  # fmt: skip


@dataclass
class Outils:
    reglages: dict[str, Any]
    base: base_.Base
    systeme: systeme.Systeme
    moteur: ocr.Moteur | None
    ia: Any = None  # §6 : ia.classer(extraction, classement, element) → Classement | None
    coffre: Any = None  # §7 : coffre.enregistrer(element, classement, fichier), coffre.oublier(element)
    avertir: Callable[[base_.Element], None] | None = None  # §9 : les notifications (groupées)
    emetteurs: tuple[emetteurs.Emetteur, ...] | None = None
    regles: regles.Regles | None = None
    ajoutes: list[int] = field(default_factory=list)  # les pièces jointes mises dans la file pendant ce tour

    @property
    def classes(self) -> Path:
        return config.chemin(self.reglages, "classes")

    def travail(self, element: int) -> Path:
        return config.dossier_donnees(self.reglages) / "travail" / str(element)


def outils(reglages: dict[str, Any], base: base_.Base | None = None, systeme_: systeme.Systeme | None = None,
           moteur: ocr.Moteur | None | str = "auto", ia: Any = "auto") -> Outils:  # fmt: skip
    """Tout ce qu'il faut pour traiter : « auto » choisit le vrai (Vision ou autre OCR, Claude, le Mac)."""
    from modules.trieur.classement import perso_emetteurs
    from modules.trieur.garanties.coffre import Coffre
    from modules.trieur.ia import couche

    m = ocr.choisir() if moteur == "auto" else moteur
    b, s = base or base_.ouvrir(reglages), systeme_ or systeme.choisir()
    return Outils(reglages, b, s, m if not isinstance(m, str) else None, coffre=Coffre(reglages, b, s),
                  ia=couche(reglages, b) if ia == "auto" else ia,
                  emetteurs=emetteurs.charger(perso_emetteurs(reglages)))  # fmt: skip


# --- traiter -----------------------------------------------------------------------------------------------------


def traiter_la_file(o: Outils, limite: int = 50) -> list[base_.Element]:
    """Tout ce qui attend, dans l'ordre d'arrivée (les pièces jointes trouvées en route comprises)."""
    faits = []
    for _ in range(3):  # un courriel ajoute ses pièces jointes : un 2e passage les prend
        attente = o.base.en_attente(limite)
        if not attente:
            break
        for el in attente:
            r = traiter(o, el.id)
            if r is not None:
                faits.append(r)
    return faits


def traiter(o: Outils, element: int) -> base_.Element | None:
    if not o.base.prendre(element):
        return None  # déjà pris (le démon et une commande en même temps)
    el = o.base.element(element)
    assert el is not None
    try:
        _traiter(o, el)
    except Exception as e:  # l'original n'a pas bougé : il sera repris, 3 fois au plus
        etat = "erreur" if el.essais >= ESSAIS_MAX else "en_attente"
        o.base.mettre_a_jour(el.id, etat=etat, erreur=f"{e.__class__.__name__} : {e}"[:300], traite=time.time())
        log.warning("%s : %s (%s)", el.nom, e, "abandon" if etat == "erreur" else "nouvel essai")
    finally:
        shutil.rmtree(o.travail(el.id), ignore_errors=True)
    fini = o.base.element(element)
    if fini is not None and o.avertir and fini.etat not in ("en_attente", "ignore"):
        o.avertir(fini)
    return fini


def _traiter(o: Outils, el: base_.Element) -> None:
    source = Path(el.chemin)
    if not source.exists():
        o.base.mettre_a_jour(el.id, etat="erreur", erreur="fichier introuvable", traite=time.time())
        return
    empreinte = rangement.empreinte(source)
    o.base.mettre_a_jour(el.id, empreinte=empreinte, taille=source.stat().st_size)
    if el.source in AUTOMATIQUES and o.base.annule_avec(empreinte):
        # Un document que tu as fait annuler, revenu à sa place : on ne le reprend pas tout seul.
        o.base.mettre_a_jour(el.id, etat="ignore", erreur="annulé auparavant", traite=time.time())
        return
    deja = o.base.doublon_de(empreinte, el.id)
    if deja is not None:
        _doublon(o, el, source, empreinte, deja)
        return
    reglages = o.reglages
    debut = int(reglages["classement"]["pages_analysees_debut"])
    e = extraire(source, o.moteur, o.travail(el.id), debut, coins=o.systeme.coins)
    for nom_pj, contenu in e.pieces_jointes:
        _piece_jointe(o, el, nom_pj, contenu)
    c = _classer(o, el, e)
    sortie = _issue(c, e, reglages)
    if el.source == "telechargements" and not _sur_pour_les_telechargements(c, sortie, reglages):
        o.base.mettre_a_jour(el.id, etat="ignore", traite=time.time(), type=c.type if c else None,
                             confiance=c.confiance if c else None)  # fmt: skip
        return
    dossier, nom = destination(o, c, sortie, e, el)
    infos: dict[str, Any] = {"nature": e.nature, "erreur": e.erreur, "duree_s": round(e.duree_s, 2)}
    if sortie == "classe" and c is not None and e.nature == "image" and e.image is not None:
        fichier = _ranger_une_photo_de_document(o, el, c, e, dossier, nom, source, empreinte, infos)
    else:
        fichier = rangement.deplacer(source, dossier, nom, o.base, el.id, attendue=empreinte)
    etat = {"classe": "classe", "photos": "photos"}.get(sortie, "a_verifier")
    if c is not None and etat != "photos":
        infos.update(numero=c.numero, detail=c.detail, raisons=c.raisons[:8], scores=c.scores,
                     emetteur_connu=c.emetteur_connu, en_ligne=c.en_ligne)  # fmt: skip
    _tags(o, el, fichier, etat, c)
    o.base.mettre_a_jour(
        el.id, etat=etat, traite=time.time(), destination=str(fichier), infos=infos, erreur=None,
        type=c.type if c else None, confiance=c.confiance if c else None, emetteur=c.emetteur if c else None,
        date=c.date.isoformat() if c and c.date else None, par=c.source if c else None,
        montant=str(c.montant) if c and c.montant is not None else None,
    )  # fmt: skip
    if etat == "classe" and c is not None and o.coffre is not None:
        o.coffre.enregistrer(el.id, c, fichier)
    log.info("%s → %s/%s (%s, %.2f)", el.nom, fichier.parent.name, fichier.name, c.type if c else sortie,
             c.confiance if c else 0.0)  # fmt: skip


def _classer(o: Outils, el: base_.Element, e: Extraction) -> Classement | None:
    if not e.texte.strip():
        return None
    c = classer(e.texte, o.reglages, note=el.note, appris=o.base.appris(), base_emetteurs=o.emetteurs, regles_=o.regles)
    seuil = float(o.reglages["classement"]["seuil_ia"])
    if o.ia is not None and (c.type == "autre" or c.confiance < seuil) and not e.erreur:
        reponse: Classement | None = o.ia.classer(e, c, el)
        if reponse is not None:
            return reponse
    return c


def _issue(c: Classement | None, e: Extraction, reglages: dict[str, Any]) -> str:
    if e.nature == "lien":
        return "liens"
    if e.nature == "fichier" and not e.erreur:
        return "fichiers"
    sortie = issue(c, e.nature, e.mots, e.erreur, reglages)
    if sortie == "a_verifier" and e.nature == "texte" and (c is None or c.type == "autre"):
        return "notes"
    return sortie


def _sur_pour_les_telechargements(c: Classement | None, sortie: str, reglages: dict[str, Any]) -> bool:
    """§2 E5 : un PDF téléchargé n'est rangé que si le Trieur est sûr de lui ; sinon il ne bouge pas."""
    minimum = float(reglages["telechargements"]["confiance_min"])
    return sortie == "classe" and c is not None and c.confiance >= minimum


def destination(o: Outils, c: Classement | None, sortie: str, e: Extraction, el: base_.Element) -> tuple[Path, str]:
    r = o.reglages
    arbo = r["arborescence"]
    extension = Path(el.nom).suffix.lower() or ".bin"
    if sortie == "classe" and c is not None:
        ext = ".pdf" if e.nature == "image" and e.image is not None else extension
        return o.classes / nommage.dossier(c, r), nommage.nom(c, ext, r)
    if sortie == "photos":
        return config.chemin(r, "photos"), el.nom
    if sortie == "liens":
        return o.classes / arbo.get("liens", "Liens"), el.nom
    if sortie == "notes":
        return o.classes / arbo["notes"], el.nom
    if sortie == "fichiers":
        sous = arbo["fichiers"].replace("{extension}", extension.lstrip(".") or "autres")
        return o.classes / sous, el.nom
    return o.classes / arbo["a_verifier"], el.nom


def _ranger_une_photo_de_document(o: Outils, el: base_.Element, c: Classement, e: Extraction, dossier: Path, nom: str,
                                  source: Path, empreinte: str, infos: dict[str, Any]) -> Path:  # fmt: skip
    """Une photo de document devient un PDF cherchable (l'image recadrée + le texte invisible) ; la photo
    d'origine est gardée dans Originaux/AAAA."""
    assert e.image is not None
    pdf = o.travail(el.id) / "document.pdf"
    image.pdf_cherchable(e.image, e.morceaux, pdf)
    fichier = rangement.creer(pdf, dossier, nom, o.base, el.id)
    originaux = nommage.dossier(c, o.reglages, "originaux")
    archive = rangement.deplacer(source, o.classes / originaux, Path(nom).stem + Path(el.nom).suffix.lower(), o.base,
                                 el.id, genre="archive", attendue=empreinte)  # fmt: skip
    infos["original"] = str(archive)
    return fichier


def _piece_jointe(o: Outils, el: base_.Element, nom: str, contenu: bytes) -> None:
    dossier = config.dossier_donnees(o.reglages) / "pieces" / str(el.id)
    dossier.mkdir(parents=True, exist_ok=True)
    nom = nommage.propre(Path(nom).stem, 80) + Path(nom).suffix.lower() or "piece-jointe"
    chemin = nommage.libre(dossier, nom)
    chemin.write_bytes(contenu)
    o.ajoutes.append(o.base.ajouter(chemin, "courriel", note=el.note, parent=el.id))


def _doublon(o: Outils, el: base_.Element, source: Path, empreinte: str, deja: base_.Element) -> None:
    """Le même contenu est déjà rangé. Un doublon arrivé par la boîte ou « À trier » va dans À vérifier/Doublons
    (jamais effacé) ; une pièce jointe (une copie à nous) est effacée ; ailleurs, le fichier ne bouge pas."""
    infos = {"de": deja.id, "rangé": deja.destination}
    if el.source in ("boite", "a_trier"):
        dossier = o.classes / o.reglages["arborescence"]["a_verifier"] / "Doublons"
        fichier = rangement.deplacer(source, dossier, el.nom, o.base, el.id, attendue=empreinte)
        o.base.mettre_a_jour(el.id, etat="doublon", destination=str(fichier), infos=infos, traite=time.time())
    else:
        if el.source == "courriel":
            source.unlink(missing_ok=True)
        o.base.mettre_a_jour(el.id, etat="doublon", infos=infos, traite=time.time())


def _tags(o: Outils, el: base_.Element, fichier: Path, etat: str, c: Classement | None) -> None:
    if etat == "classe" and c is not None:
        tags = [c.libelle] + (["Garantie"] if c.garanties else [])
    elif etat == "a_verifier":
        tags = ["À vérifier"]
    else:
        return
    if o.systeme.poser_tags(fichier, tags):
        o.base.noter_action(el.id, "tag", None, str(fichier), ",".join(tags))


# --- annuler, corriger, apprendre ------------------------------------------------------------------------------


class Refus(Exception):
    """Une demande impossible, expliquée simplement."""


def annuler(o: Outils, element: int) -> list[str]:
    """Défait tout ce que le Trieur a fait pour cet élément, dans l'ordre inverse. Renvoie ce qui a été fait."""
    el = o.base.element(element)
    if el is None:
        raise Refus(f"aucun élément n°{element}")
    if el.etat == "annule":
        raise Refus(f"l'élément n°{element} est déjà annulé")
    actions = o.base.actions(element)
    if not actions:
        raise Refus(f"rien à annuler pour l'élément n°{element} ({el.etat})")
    supprimees = {a["source"] for a in actions if a["genre"] == "supprime_source"}
    faits: list[str] = []
    if o.coffre is not None:
        faits += o.coffre.oublier(element)
    for a in reversed(actions):
        genre, cible = a["genre"], Path(a["cible"]) if a["cible"] else None
        if genre in ("range", "archive") and cible is not None:
            if not cible.exists():
                faits.append(f"introuvable : {cible} (déplacé à la main ?)")
            elif a["source"] in supprimees:
                retour = rangement.ramener(cible, Path(a["source"]), o.base, element)
                faits.append(f"remis : {retour}")
            elif rangement.empreinte(cible) == a["empreinte"]:
                cible.unlink()
                faits.append(f"copie retirée : {cible.name}")
        elif genre == "cree" and cible is not None and cible.exists():
            if rangement.empreinte(cible) == a["empreinte"]:
                cible.unlink()
                faits.append(f"PDF retiré : {cible.name}")
            else:
                faits.append(f"gardé (modifié depuis) : {cible}")
        elif genre == "alias" and cible is not None and (cible.exists() or cible.is_symlink()):
            cible.unlink()
            faits.append(f"alias retiré : {cible.name}")
        o.base.defaire(a["id"])
    o.base.mettre_a_jour(element, etat="annule", traite=time.time())
    log.info("annulé n°%s : %s", element, "; ".join(faits))
    return faits


def corriger(o: Outils, element: int, type_: str, emetteur: str | None = None) -> base_.Element:
    """Reclasse un document (nouveau nom, nouveau dossier, garantie revue) et retient la leçon pour la suite."""
    if type_ not in regles.TYPES:
        raise Refus(f"type inconnu : {type_} (types : {', '.join(regles.TYPES)})")
    el = o.base.element(element)
    if el is None or el.etat not in ("classe", "a_verifier") or not el.destination:
        raise Refus(f"l'élément n°{element} n'est pas un document rangé")
    fichier = Path(el.destination)
    if not fichier.exists():
        raise Refus(f"le fichier rangé est introuvable : {fichier}")
    e = extraire(fichier, o.moteur, o.travail(element), int(o.reglages["classement"]["pages_analysees_debut"]))
    try:
        r = o.regles or regles.charger()
        c = classer(e.texte, o.reglages, note=el.note, base_emetteurs=o.emetteurs, regles_=r)
        ancien_type, ancien_emetteur = el.type, el.emetteur or c.emetteur
        c.type, c.libelle, c.confiance, c.source = type_, r.libelles.get(type_, type_), 1.0, "correction"
        if emetteur:
            c.emetteur, c.emetteur_connu = emetteur, True
        remplir(c, e.texte, o.reglages, el.note)
        if o.coffre is not None:
            o.coffre.oublier(element)
        dossier = o.classes / nommage.dossier(c, o.reglages)
        nouveau = rangement.deplacer(fichier, dossier, nommage.nom(c, fichier.suffix, o.reglages), o.base, element)
        _tags(o, el, nouveau, "classe", c)
        cle = emetteurs.cle(c.emetteur or "")
        if cle:
            o.base.apprendre(cle, type_, POINTS_APPRIS)
        if emetteur and ancien_emetteur and emetteurs.cle(ancien_emetteur) != cle:
            _retenir_emetteur(o, emetteur, ancien_emetteur, type_)
        infos = el.details | {"corrige": {"de": ancien_type, "vers": type_, "quand": time.time()}}
        o.base.mettre_a_jour(element, etat="classe", type=type_, confiance=1.0, emetteur=c.emetteur, par="correction",
                             date=c.date.isoformat() if c.date else None, destination=str(nouveau), infos=infos,
                             montant=str(c.montant) if c.montant is not None else None)  # fmt: skip
        if o.coffre is not None:
            o.coffre.enregistrer(element, c, nouveau)
    finally:
        shutil.rmtree(o.travail(element), ignore_errors=True)
    fini = o.base.element(element)
    assert fini is not None
    return fini


def _retenir_emetteur(o: Outils, nom: str, lu: str, type_: str) -> None:
    """« Ce que j'ai lu en haut » = « nom » : ajouté à tes émetteurs (emetteurs_perso.json)."""
    import json

    from modules.trieur.classement import perso_emetteurs
    from modules.trieur.classement.texte import normaliser

    fichier = perso_emetteurs(o.reglages)
    if fichier is None:
        return
    try:
        donnees = json.loads(fichier.read_text(encoding="utf-8")) if fichier.exists() else {"emetteurs": []}
    except (OSError, ValueError):
        donnees = {"emetteurs": []}
    liste = [x for x in donnees.get("emetteurs", []) if isinstance(x, dict)]
    existant = next((x for x in liste if x.get("nom") == nom), None)
    motifs = {normaliser(nom), normaliser(lu)}
    if existant:
        existant["motifs"] = sorted(set(existant.get("motifs", [])) | motifs)
    else:
        liste.append({"nom": nom, "categorie": TYPE_DES_CATEGORIES.get(type_, "appris"), "motifs": sorted(motifs)})
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(json.dumps({"emetteurs": liste}, ensure_ascii=False, indent=1), encoding="utf-8")
    emetteurs.charger.cache_clear()
    o.emetteurs = emetteurs.charger(fichier)


def type_du_dossier(dossier_relatif: Path, reglages: dict[str, Any]) -> str | None:
    """Le type dont le modèle de dossier correspond (« Factures/2026 » → un type de facture), sinon None.
    Plusieurs types partagent un dossier (les factures) : le premier n'est retenu que s'il est seul."""
    texte = dossier_relatif.as_posix()
    trouves = []
    for type_, modele in reglages["arborescence"].items():
        if type_ not in regles.TYPES:
            continue
        motif = re.escape(modele).replace(re.escape("{annee}"), r"(?:\d{4}|Sans date)")
        motif = motif.replace(re.escape("{banque}"), r"[^/]+").replace(re.escape("{emetteur}"), r"[^/]+")
        if re.fullmatch(motif, texte):
            trouves.append(type_)
    return trouves[0] if len(trouves) == 1 else None


def apprendre_deplacement(o: Outils, ancien: Path, nouveau: Path) -> str | None:
    """Tu as déplacé à la main un document rangé : le Trieur suit le fichier et, si le nouveau dossier est celui
    d'un autre type, retient la leçon. Renvoie le type appris, s'il y en a un."""
    el = o.base.par_destination(ancien)
    if el is None:
        return None
    infos = el.details | {"deplace_a_la_main": str(nouveau)}
    o.base.mettre_a_jour(el.id, destination=str(nouveau), infos=infos)
    try:
        relatif = nouveau.parent.relative_to(o.classes)
    except ValueError:
        return None  # sorti de « Classés » : on suit le fichier, sans leçon
    type_ = type_du_dossier(relatif, o.reglages)
    if type_ is None or type_ == el.type or not el.emetteur:
        return None
    o.base.apprendre(emetteurs.cle(el.emetteur), type_, POINTS_APPRIS)
    o.base.mettre_a_jour(el.id, type=type_, par="déplacement")
    log.info("appris : %s → %s (déplacé à la main)", el.emetteur, type_)
    return type_
