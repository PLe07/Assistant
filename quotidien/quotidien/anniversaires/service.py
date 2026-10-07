"""Les anniversaires assemblés (§6) : qui, quand, les rappels J-7 / J-1 / J émis une seule fois, le message prêt.

- J-7 (proches seulement : famille, couple, ami proche) à 10 h : penser au cadeau ;
- J-1 à 19 h 30 : « demain, anniversaire de … → message prêt » ;
- le jour J à 9 h : la notification, puis (si `dialogue`) la fenêtre des 3 variantes avec « Ouvrir dans Messages ».
Chaque rappel est noté une fois émis (table `anniversaires_emis`) : jamais deux fois, même après un redémarrage.
Un rappel manqué (Mac en veille) est rattrapé seulement s'il sert encore : pas de « demain » le jour même.
Jamais entre 23 h et 7 h. Deux anniversaires le même jour : une seule notification.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import cache
from pathlib import Path
from typing import Any

from quotidien import config
from quotidien.anniversaires import contacts, dates, messages, proches
from quotidien.anniversaires.proches import Personne
from quotidien.db import Base as BaseDonnees
from quotidien.journal import log
from quotidien.notifier import Notifieur, en_silence
from quotidien.repas.envies import normaliser
from quotidien.repas.page import date_longue
from quotidien.systeme import Systeme

GENRES = ("j7", "j1", "j", "fete")
ICI = Path(__file__).resolve().parent


@cache
def _fetes() -> dict[str, str]:
    donnees: dict[str, str] = json.loads((ICI / "fetes.json").read_text(encoding="utf-8"))["fetes"]
    return donnees


def jour_de_fete(prenom: str, annee: int) -> date | None:
    """La fête du prénom (calendrier français), ou None. Le premier prénom compte (« Marie Anne » : Marie)."""
    mots = prenom.strip().split()
    mmjj = _fetes().get(normaliser(mots[0])) if mots else None
    if mmjj is None:
        return None
    mois, jour = (int(x) for x in mmjj.split("-"))
    return date(annee, mois, jour)


@dataclass
class Annuaire:
    personnes: list[Personne] = field(default_factory=list)
    statut_contacts: str = "desactive"
    sans_date: int = 0
    avertissements: list[str] = field(default_factory=list)


def annuaire(reglages: config.Reglages, aujourdhui: date,
             fournisseur: contacts.Fournisseur | None = None) -> Annuaire:  # fmt: skip
    """Contacts (si permis) + proches.toml. Contacts refusés ou absents : mode dégradé avec proches.toml seul."""
    r = reglages.reglages["anniversaires"]
    fiches = proches.lire_fiches(aujourdhui=aujourdhui)
    a = Annuaire(avertissements=list(fiches.avertissements))
    lus: list[Personne] = []
    if r["contacts"]:
        lecture = contacts.lire(aujourdhui, fournisseur)
        a.statut_contacts, a.sans_date, lus = lecture.statut, lecture.sans_date, lecture.personnes
    a.personnes = proches.fusionner(lus, fiches.personnes)
    return a


@dataclass
class Echeance:
    personne: Personne
    jour: date  # le jour de l'anniversaire
    genre: str  # j7, j1 ou j
    quand: float  # à partir de quand l'émettre
    fin: float  # au-delà, il ne sert plus

    @property
    def cle(self) -> str:
        return f"{self.personne.cle}/{self.jour.isoformat()}/{self.genre}"

    @property
    def age(self) -> int | None:
        return dates.age(self.personne.naissance, self.jour)


def echeances(personnes: list[Personne], aujourdhui: date, reglages: dict[str, Any]) -> list[Echeance]:
    """Les rappels des anniversaires des 8 prochains jours (et d'aujourd'hui)."""
    h, a = reglages["horaires"], reglages["anniversaires"]
    fuseau = reglages["lieu"]["fuseau"]
    avant = int(a["jours_avant_proches"])
    resultat = []
    for p in personnes:
        if not p.naissance.jour:
            continue
        jour = dates.prochaine(p.naissance, aujourdhui, a["date_29_fevrier"])
        if (jour - aujourdhui).days > max(avant, 1):
            continue
        veille = jour - timedelta(days=1)
        fin_du_jour = dates.moment(jour, h["silence_debut"], fuseau)
        if p.proche:
            resultat.append(Echeance(p, jour, "j7", dates.moment(jour - timedelta(days=avant), h["anniversaire_cadeau"],
                                     fuseau), dates.moment(veille, "00:00", fuseau)))  # fmt: skip
        resultat.append(Echeance(p, jour, "j1", dates.moment(veille, h["anniversaire_veille"], fuseau),
                                 dates.moment(jour, "00:00", fuseau)))  # fmt: skip
        resultat.append(Echeance(p, jour, "j", dates.moment(jour, h["anniversaire_jour"], fuseau), fin_du_jour))
    if a["fetes"]:  # option : les fêtes du jour (sauf le jour de l'anniversaire)
        for p in personnes:
            fete = jour_de_fete(p.prenom, aujourdhui.year)
            anniversaire = dates.prochaine(p.naissance, aujourdhui, a["date_29_fevrier"]) if p.naissance.jour else None
            if fete == aujourdhui and anniversaire != fete:
                resultat.append(Echeance(p, fete, "fete", dates.moment(fete, h["anniversaire_jour"], fuseau),
                                         dates.moment(fete, h["silence_debut"], fuseau)))  # fmt: skip
    return resultat


def dues(db: BaseDonnees, personnes: list[Personne], maintenant: float, reglages: dict[str, Any]) -> list[Echeance]:
    if en_silence(maintenant, reglages):
        return []
    aujourdhui = dates.aujourdhui(maintenant, reglages["lieu"]["fuseau"])
    emis = {r[0] for r in db.lignes("SELECT cle FROM anniversaires_emis")}
    return [
        e for e in echeances(personnes, aujourdhui, reglages) if e.quand <= maintenant < e.fin and e.cle not in emis
    ]


def marquer(db: BaseDonnees, liste: list[Echeance], maintenant: float) -> None:
    with db.transaction() as cx:
        for e in liste:
            cx.execute("INSERT OR IGNORE INTO anniversaires_emis(cle, emis_le) VALUES (?, ?)", (e.cle, maintenant))


# --- Messages prêts (une fois par personne et par anniversaire) -------------------------------------------------


def message_pret(db: BaseDonnees, reglages: dict[str, Any], personne: Personne, jour: date, maintenant: float,
                 **kwargs: Any) -> messages.Messages:  # fmt: skip
    cle = f"{personne.cle}/{jour.isoformat()}"
    ligne = db.cx.execute("SELECT json FROM messages_prets WHERE cle = ?", (cle,)).fetchone()
    if ligne is not None:
        d = json.loads(ligne[0])
        return messages.Messages(list(d["variantes"]), str(d["source"]))
    m = messages.rediger(db, reglages, personne, dates.age(personne.naissance, jour), jour.year, **kwargs)
    with db.transaction() as cx:
        cx.execute("INSERT OR REPLACE INTO messages_prets(cle, cree_le, json) VALUES (?, ?, ?)",
                   (cle, maintenant, json.dumps({"variantes": m.variantes, "source": m.source},
                                                ensure_ascii=False)))  # fmt: skip
        cx.execute("DELETE FROM messages_prets WHERE cree_le < ?", (maintenant - 60 * 86400,))
    return m


# --- Textes -------------------------------------------------------------------------------------------------------


def _qui(liste: list[Echeance], avec_age: bool = True) -> str:
    noms = []
    for e in liste:
        age = f" ({e.age} ans)" if e.age and avec_age else ""
        noms.append(f"{e.personne.prenom}{age}")
    return noms[0] if len(noms) == 1 else ", ".join(noms[:-1]) + " et " + noms[-1]


def texte_notification(genre: str, liste: list[Echeance], aujourdhui: date) -> tuple[str, str]:
    """(titre, texte) d'une notification pour un groupe de rappels du même jour et du même genre."""
    pluriel = "s" if len(liste) > 1 else ""
    jour = liste[0].jour
    qui = _qui(liste)
    if genre == "j7":
        dans = (jour - aujourdhui).days
        return (f"🎁 Dans {dans} jours", f"Anniversaire{pluriel} de {qui}, {date_longue(jour)}. "
                "Une idée de cadeau ?")  # fmt: skip
    if genre == "j1":
        return "🎂 Demain", f"Anniversaire{pluriel} de {qui} → message prêt."
    if genre == "fete":
        return "🌼 Bonne fête", f"C'est la fête de {_qui(liste, avec_age=False)} aujourd'hui → petit message prêt."
    return "🎂 Aujourd'hui", f"Anniversaire{pluriel} de {qui}. Message prêt : ouvre-le et envoie-le toi-même."


def emettre(db: BaseDonnees, reglages: config.Reglages, systeme: Systeme, personnes: list[Personne],
            maintenant: float, **kwargs: Any) -> list[str]:  # fmt: skip
    """Émet les rappels dus (une notification par jour et par genre), puis les note. Renvoie les textes émis."""
    r = reglages.reglages
    a_faire = dues(db, personnes, maintenant, r)
    if not a_faire:
        return []
    aujourdhui = dates.aujourdhui(maintenant, r["lieu"]["fuseau"])
    notifieur = Notifieur(db, systeme, r, lambda: maintenant)
    groupes: dict[tuple[date, str], list[Echeance]] = defaultdict(list)
    for e in a_faire:
        groupes[(e.jour, e.genre)].append(e)
    emis = []
    for (_jour, genre), liste in sorted(groupes.items(), key=lambda x: (x[0][0], GENRES.index(x[0][1]))):
        liste.sort(key=lambda e: normaliser(e.personne.prenom))
        if genre in ("j1", "j"):
            for e in liste:  # le message est prêt dès la veille (une seule demande à l'IA par anniversaire)
                message_pret(db, r, e.personne, e.jour, maintenant, **kwargs)
        titre, texte = texte_notification(genre, liste, aujourdhui)
        notifieur.notifier("anniversaire", titre, texte)
        marquer(db, liste, maintenant)
        emis.append(f"{titre} — {texte}")
        log().info("anniversaires : rappel %s émis pour %d personne(s)", genre, len(liste))
        if genre in ("j", "fete") and r["anniversaires"]["dialogue"]:
            for e in liste:
                variantes = messages.fete(e.personne) if genre == "fete" else None
                proposer_envoi(db, r, systeme, e.personne, e.jour, maintenant, variantes=variantes)
    return emis


def proposer_envoi(db: BaseDonnees, reglages: dict[str, Any], systeme: Systeme, personne: Personne, jour: date,
                   maintenant: float, numero: int | None = None,
                   variantes: list[str] | None = None) -> bool:  # fmt: skip
    """La fenêtre des 3 variantes ; « Ouvrir dans Messages » ouvre Messages avec le texte prérempli (et copié).
    Rien n'est envoyé : c'est toi qui appuies sur Envoyer."""
    variantes = variantes or message_pret(db, reglages, personne, jour, maintenant).variantes
    if numero is not None:
        choix: str | None = variantes[numero - 1]
    else:
        choix = systeme.choisir(f"Message pour {personne.prenom}", "Choisis un message (tu pourras le modifier "
                                "avant d'envoyer) :", "Ouvrir dans Messages", variantes)  # fmt: skip
    if not choix:
        return False
    return systeme.ouvrir_messages(choix, personne.telephone)


# --- Pour le brief et la commande ---------------------------------------------------------------------------------


def a_venir(
    personnes: list[Personne], aujourdhui: date, jours: int, regle_29: str = "28-02"
) -> list[tuple[date, Personne]]:
    resultat = []
    for p in personnes:
        if p.naissance.jour:
            d = dates.prochaine(p.naissance, aujourdhui, regle_29)
            if (d - aujourdhui).days <= jours:
                resultat.append((d, p))
    return sorted(resultat, key=lambda x: (x[0], x[1].prenom))


def ligne_brief(personnes: list[Personne], aujourdhui: date, regle_29: str = "28-02") -> str | None:
    """« 🎂 Aujourd'hui : … » ou « 🎂 Demain : … → message prêt. » ; rien s'il n'y a personne."""
    proches_jours = a_venir(personnes, aujourdhui, 1, regle_29)
    auj = [p for d, p in proches_jours if d == aujourdhui]
    dem = [p for d, p in proches_jours if d > aujourdhui]

    def noms(ps: list[Personne]) -> str:
        n = [p.prenom for p in ps]
        return n[0] if len(n) == 1 else ", ".join(n[:-1]) + " et " + n[-1]

    morceaux = []
    if auj:
        morceaux.append(f"Aujourd'hui : anniversaire{'s' if len(auj) > 1 else ''} de {noms(auj)} → message prêt")
    if dem:
        morceaux.append(f"Demain : anniversaire{'s' if len(dem) > 1 else ''} de {noms(dem)} → message prêt")
    return "🎂 " + " · ".join(morceaux) + "." if morceaux else None
