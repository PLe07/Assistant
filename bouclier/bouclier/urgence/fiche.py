"""La fiche urgence (n°22) : les numéros **vérifiés** sur des sites officiels, les réflexes pas à pas, et tes infos.

Un numéro n'apparaît que s'il est dans `sources.json` (pages officielles) et que la dernière revérification ne l'a
pas trouvé absent de toutes ses pages. La page HTML est 100 % autonome : aucune ressource extérieure (ni police, ni
image, ni feuille de style), elle s'ouvre sans réseau.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from bouclier.arnaque.reponse import reflexes
from bouclier.urgence import sources
from bouclier.urgence.infos import MesInfos

GROUPES = (
    ("Urgences", ("samu", "police", "pompiers", "urgence-europe", "urgence-sms")),
    ("Arnaque, carte bancaire, piratage", ("opposition", "33700", "info-escroqueries", "17cyber", "signal-spam",
                                           "thesee", "perceval")),
    ("Santé, à Bordeaux", ("antipoison-bordeaux", "chu-bordeaux", "pharmacie-garde")),
)  # fmt: skip
ORDRE_SITUATIONS = ("telephone", "carte", "arnaque", "compte", "papiers", "fuite")


@dataclass
class Verification:
    date: str  # AAAA-MM-JJ
    absents: list[str] = field(default_factory=list)
    injoignables: list[str] = field(default_factory=list)
    en_ligne: bool = False  # True : pages retéléchargées sur le Mac ; False : vérification de la construction


def lire_verification(fichier: Path, registre: sources.Registre) -> Verification:
    try:
        data = json.loads(fichier.read_text(encoding="utf-8"))
        return Verification(str(data["date"]), list(data.get("absents", [])), list(data.get("injoignables", [])), True)
    except (OSError, ValueError, KeyError, TypeError):
        return Verification(registre.verifie_le)


@dataclass
class Ligne:
    id: str
    libelle: str
    valeur: str  # le numéro ou le site
    payant: bool


@dataclass
class Fiche:
    groupes: list[tuple[str, list[Ligne]]]
    situations: list[tuple[str, list[str]]]
    infos: MesInfos
    verification: Verification
    sources_utilisees: list[sources.Source]
    generee_le: dt.date

    def lignes(self) -> list[Ligne]:
        return [ligne for _, lignes in self.groupes for ligne in lignes]


def construire(infos: MesInfos, verification: Verification, registre: sources.Registre | None = None,
               aujourd_hui: dt.date | None = None) -> Fiche:  # fmt: skip
    registre = registre or sources.charger()
    groupes: list[tuple[str, list[Ligne]]] = []
    utilisees: dict[str, sources.Source] = {}
    for titre, ids in GROUPES:
        lignes = []
        for ident in ids:
            if ident in verification.absents:
                continue  # plus confirmé par aucune page officielle : exclu
            e = registre.element(ident)
            if isinstance(e, sources.Numero):
                lignes.append(Ligne(e.id, e.libelle, e.numero, not e.gratuit))
            else:
                lignes.append(Ligne(e.id, e.libelle, e.adresse, False))
            for s in e.sources:
                utilisees[s] = registre.sources[s]
        if lignes:
            groupes.append((titre, lignes))
    data = reflexes()["situations"]
    situations = [(data[s]["titre"], list(data[s]["etapes"])) for s in ORDRE_SITUATIONS]
    for s in ORDRE_SITUATIONS:
        for ident in data[s]["sources"]:
            utilisees[ident] = registre.sources[ident]
    return Fiche(groupes, situations, infos, verification, list(utilisees.values()), aujourd_hui or dt.date.today())


def _date_fr(texte: str) -> str:
    try:
        return dt.date.fromisoformat(texte).strftime("%d/%m/%Y")
    except ValueError:
        return texte


def mention_verification(fiche: Fiche) -> str:
    quand = _date_fr(fiche.verification.date)
    if fiche.verification.en_ligne:
        return f"Numéros vérifiés le {quand} sur les sites officiels (liste des pages en bas)."
    return (f"Numéros vérifiés le {quand} sur les sites officiels (liste des pages en bas) ; revérification sur ton"
            " Mac à l'installation.")  # fmt: skip


STYLE = """
:root { --fond: #ffffff; --texte: #111; --doux: #555; --ligne: #ddd; --rouge: #b71c1c; }
@media (prefers-color-scheme: dark) { :root { --fond: #111; --texte: #f2f2f2; --doux: #aaa; --ligne: #333;
  --rouge: #ff6b6b; } }
* { box-sizing: border-box; }
body { margin: 0; padding: 16px; background: var(--fond); color: var(--texte);
       font: 17px/1.45 -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif; }
main { max-width: 760px; margin: 0 auto; }
h1 { font-size: 26px; margin: 0; } h2 { font-size: 19px; margin: 24px 0 8px; color: var(--rouge); }
table { width: 100%; border-collapse: collapse; } td { padding: 7px 4px; border-bottom: 1px solid var(--ligne); }
td.num { font-size: 22px; font-weight: 700; white-space: nowrap; width: 1%; padding-right: 14px; }
td.num a { color: inherit; text-decoration: none; }
ol { padding-left: 22px; margin: 4px 0 12px; } li { margin: 3px 0; } .doux, small { color: var(--doux); }
@media print { body { padding: 0; font-size: 12px; } h2 { margin-top: 12px; } td.num { font-size: 15px; } }
"""


def _tel(valeur: str) -> str:
    chiffres = sources.chiffres(valeur)
    if chiffres and len(chiffres) == len(valeur.replace(" ", "")):
        return f'<a href="tel:{chiffres}">{escape(valeur)}</a>'
    return escape(valeur)


def html(fiche: Fiche) -> str:
    p: list[str] = []
    titre = "Fiche urgence" + (f" — {escape(fiche.infos.nom)}" if fiche.infos.nom else "")
    p.append(f'<h1>🆘 {titre}</h1><p class="doux">{escape(mention_verification(fiche))}</p>')
    for titre_groupe, lignes in fiche.groupes:
        p.append(f"<h2>{escape(titre_groupe)}</h2><table>")
        for ligne in lignes:
            payant = " <small>(payant)</small>" if ligne.payant else ""
            p.append(f'<tr><td class="num">{_tel(ligne.valeur)}</td><td>{escape(ligne.libelle)}{payant}</td></tr>')
        p.append("</table>")
    i = fiche.infos
    mes = []
    for c in i.contacts:
        mes.append(f'<tr><td class="num">{_tel(c.telephone)}</td><td>{escape(c.nom or "Contact")}</td></tr>')
    if i.operateur_tel:
        qui = f" ({escape(i.operateur)})" if i.operateur else ""
        mes.append(
            f'<tr><td class="num">{_tel(i.operateur_tel)}</td><td>Mon opérateur{qui} : suspendre la ligne</td></tr>'
        )
    if i.banque_tel:
        qui = f" ({escape(i.banque)})" if i.banque else ""
        mes.append(f'<tr><td class="num">{_tel(i.banque_tel)}</td><td>Ma banque{qui} : carte perdue ou volée'
                   " (numéro noté par moi)</td></tr>")  # fmt: skip
    if mes:
        p.append("<h2>Mes contacts</h2><table>" + "".join(mes) + "</table>")
    p.append("<h2>Réflexes pas à pas</h2>")
    for titre_situation, etapes in fiche.situations:
        p.append(f"<h3>{escape(titre_situation)}</h3><ol>" + "".join(f"<li>{escape(e)}</li>" for e in etapes) + "</ol>")
    p.append("<p class=\"doux\">Données de santé : utilise la « Fiche médicale » de l'app Santé de l'iPhone (visible"
             " depuis l'écran verrouillé).</p>")  # fmt: skip
    p.append('<h2>Sources officielles</h2><ul class="doux">')
    for s in fiche.sources_utilisees:
        p.append(f"<li><small>{escape(s.editeur)} : {escape(s.url)}</small></li>")
    p.append(f"</ul><p class=\"doux\"><small>Fiche générée par Bouclier le {fiche.generee_le.strftime('%d/%m/%Y')}."
             " À relire tous les 6 mois.</small></p>")  # fmt: skip
    return ("<!doctype html>\n<html lang=\"fr\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Fiche urgence</title>"
            f"<style>{STYLE}</style></head><body><main>{''.join(p)}</main></body></html>\n")  # fmt: skip
