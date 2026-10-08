"""La commande `tableau` (§5.4), dans le Terminal.

    tableau etat                      l'état de chaque module, en une ligne
    tableau ouvrir                    ouvre la page locale dans ton navigateur
    tableau module <nom>              le détail d'un module
    tableau credits                   les crédits Claude du mois
    tableau integrite                 le code de chaque projet comparé à sa référence
    tableau integrite accepter <nom>  « C'était moi » : le code actuel devient la référence
    tableau sourdine <durée>          1h, 30min, 2h30… ou « fin »
    tableau rapport                   le rapport des 7 derniers jours
    tableau doctor                    l'état du tableau de bord lui-même
    tableau diagnostic <nom>          lance la commande de diagnostic du module (à ta demande)
    tableau demon                     le démon (lancé par launchd)

Toutes les commandes lisent ce que le démon a enregistré : elles marchent même s'il est arrêté (et le disent).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from tableau import config, registre, systeme, textes, vues
from tableau.analyse.alertes import Alertes
from tableau.analyse.integrite import Gardien
from tableau.barre_menus import Actions, adresse_page, rapport_maintenant
from tableau.db import Base
from tableau.decouverte import decouvrir
from tableau.module import EMOJI, LIBELLE, DefModule
from tableau.notifier import NotificateurMac

VERSION = "1.0.0"


def definitions(chemins: config.Chemins, reglages: config.Reglages) -> tuple[list[DefModule], list[str]]:
    """Le registre, lu sans jamais l'écrire (c'est le démon qui le tient à jour)."""
    erreurs: list[str] = []
    if chemins.registre.exists():
        try:
            modules, erreurs = registre.lire(chemins.registre.read_text(encoding="utf-8"))
        except OSError as e:
            modules, erreurs = [], [f"modules.toml illisible ({e.__class__.__name__})"]
        if not modules:
            modules = registre.connus(reglages.prefixe())
    else:
        modules = registre.connus(reglages.prefixe())
    actifs = [m for m in modules if m.actif]
    return registre.resoudre(actifs, decouvrir(chemins), chemins.maison), erreurs


def source(chemins: config.Chemins | None = None) -> vues.Source:
    chemins = chemins or config.chemins()
    reglages = config.charger(chemins.reglages)
    chemins.preparer()
    base = Base(chemins.base)
    defs, _ = definitions(chemins, reglages)
    gardien = Gardien(base, chemins.maison, chemins.launch_agents, time.time)
    alertes = Alertes(base, reglages, NotificateurMac(), time.time)
    return vues.Source(base, reglages, chemins, {d.id: d for d in defs}, gardien, alertes)


def port(s: vues.Source) -> int:
    brut = s.base.lire_meta("port")
    return int(brut) if brut and brut.isdigit() else int(s.reglages["serveur"]["port"])


def demon_vivant(s: vues.Source) -> tuple[bool, str]:
    brut = s.base.lire_meta("battement_demon")
    if brut is None:
        return False, "le démon n'a encore jamais tourné (lance ./install.sh)"
    age = s.horloge() - float(brut)
    limite = 3 * float(s.reglages["intervalles"]["sante_s"]) + 60
    if age > limite:
        return False, f"pas de tour depuis {textes.duree(age)} : le démon est-il arrêté ?"
    return True, f"dernier tour {textes.il_y_a(float(brut), s.horloge())}"


# --- les commandes (chacune rend son texte, pour être testée) --------------------------------------------------------


def etat(s: vues.Source) -> str:
    d = vues.accueil(s)
    lignes = [d["bandeau"]["texte"]]
    if d["bandeau"]["retenue"]:
        lignes.append(f"Notifications : {d['bandeau']['retenue']}")
    vivant, detail = demon_vivant(s)
    if not vivant:
        lignes.append(f"⚠️ {detail}")
    lignes.append("")
    for c in d["cartes"]:
        lignes.append(f"{c['pastille_emoji']} {c['nom']} : {c['phrase']}")
    if not d["cartes"]:
        lignes.append("Aucun module observé pour l'instant.")
    return "\n".join(lignes)


def module(s: vues.Source, nom: str) -> str:
    ident = _trouver(s, nom)
    d = vues.detail(s, ident) if ident else None
    if d is None:
        connus = ", ".join(sorted(s.defs)) or "aucun"
        return f"Module « {nom} » inconnu. Modules connus : {connus}."
    c = d["carte"]
    lignes = [f"{c['emoji']} {c['nom']} — {c['pastille_emoji']} {c['pastille_libelle']}", c["phrase"], ""]
    mesures = [
        ("Dernière activité", c["derniere_activite"]),
        ("Erreurs sur 24 h", c["erreurs_24h"]),
        ("Processeur", textes.pourcent(c["cpu_pct"], 1) if c["cpu_pct"] is not None else None),
        ("Mémoire", textes.mo(c["rss_mo"]) if c["rss_mo"] is not None else None),
        ("Crédits du mois", _credits(c)),
        ("Prochaine tâche", c["prochaine"]),
    ]
    lignes += [f"  {t} : {v}" for t, v in mesures if v not in (None, "")]
    if d["problemes"]:
        lignes += ["", "À regarder :"] + [f"  {p['message']}" for p in d["problemes"]]
    if d["attentes"]:
        lignes += ["", "A-t-il fait son travail ?"]
        lignes += [f"  {a['libelle']} : {a['detail'] or a['statut']}" for a in d["attentes"]]
    if d["erreurs"]:
        lignes += ["", "Derniers messages d'erreur (caviardés) :"]
        lignes += [f"  {e['quand']} : {e['message']}" for e in d["erreurs"][:5]]
    integ = d["integrite"]
    if integ is not None and integ["ecarts"]:
        lignes += ["", f"⚠️ Code changé : {textes.pluriel(len(integ['ecarts']), 'fichier')} (tableau integrite)."]
    if d["aide"]:
        lignes += ["", f"Pour aller plus loin : {d['aide']}"]
    return "\n".join(lignes)


def _credits(c: dict[str, Any]) -> str | None:
    if c["credits_mois"] is None:
        return None
    texte = textes.dollars(c["credits_mois"])
    if c["plafond_usd"]:
        texte += f" sur {textes.dollars(c['plafond_usd'])}"
    return texte + (" (estimé)" if c["credits_estimes"] else "")


def _trouver(s: vues.Source, nom: str) -> str | None:
    cible = nom.strip().lower()
    for ident, defn in s.defs.items():
        if cible in (ident.lower(), defn.nom.lower()):
            return ident
    return next((e.id for e in s.etats() if cible in (e.id.lower(), e.nom.lower())), None)


def credits_(s: vues.Source) -> str:
    d = vues.vue_credits(s)
    lignes = [f"Crédits Claude · {d['mois']} : {textes.dollars(d['total_usd'])}"
              + (f" sur {textes.dollars(d['plafonds_usd'])} de plafonds" if d["plafonds_usd"] else "")]  # fmt: skip
    if d["projection_usd"] is not None:
        lignes.append(f"Projection à la fin du mois : {textes.dollars(d['projection_usd'])}")
    if d["reel_usd"] is not None:
        lignes.append(f"Coût réel (rapport officiel) : {textes.dollars(d['reel_usd'])}")
    if d["mois_precedent_usd"] is not None:
        lignes.append(f"Mois précédent : {textes.dollars(d['mois_precedent_usd'])}")
    for m in d["modules"]:
        plafond = f" / {textes.dollars(m['plafond_usd'])}" if m["plafond_usd"] else ""
        estime = " (estimé)" if m["source"] == "estimation" else ""
        lignes.append(f"  {m['emoji']} {m['nom']} : {textes.dollars(m['mois_usd'])}{plafond}{estime}")
    if d["abonnement_equivalent_usd"]:
        lignes.append(f"L'assistant (abonnement) vaudrait {textes.dollars(d['abonnement_equivalent_usd'])} "
                      "au tarif de l'API.")  # fmt: skip
    return "\n".join(lignes)


def integrite(s: vues.Source) -> str:
    lignes = ["Intégrité du code (le tableau de bord ne restaure jamais rien) :"]
    for m in vues.vue_integrite(s):
        marque = {"conforme": "✓", "changé": "⚠️"}.get(m["statut"], "·")
        lignes.append(f"  {marque} {m['nom']} : {m['statut']}")
        for e in m["ecarts"][:10]:
            lignes.append(f"      {e.get('genre')} : {e.get('chemin')}")
        if m["ecarts"]:
            lignes.append(f"      Voir : {m['commande_diff']}")
            lignes.append(f"      C'était toi : tableau integrite accepter {m['id']}")
    return "\n".join(lignes)


def accepter(s: vues.Source, nom: str) -> str:
    ident = _trouver(s, nom)
    if ident is None or ident not in s.defs:
        return f"Module « {nom} » inconnu."
    return s.nouvelle_reference(ident)


def doctor(s: vues.Source) -> str:
    c = s.chemins
    vivant, detail = demon_vivant(s)
    lignes = [f"Tableau de bord {VERSION}", f"Démon : {'✅' if vivant else '❌'} {detail}"]
    lignes.append(f"Page locale : http://127.0.0.1:{port(s)}/ (tape « tableau ouvrir » pour l'ouvrir avec son jeton)")
    try:
        st = c.base.stat()
        lignes.append(f"Base : {textes.mo(st.st_size / 1024 / 1024)}, droits {oct(st.st_mode & 0o777)[2:]}")
    except OSError:
        lignes.append("Base : absente")
    reglages = config.charger(c.reglages)
    lignes.append("Réglages : " + ("OK" if not reglages.erreurs else "; ".join(reglages.erreurs)))
    _, erreurs_registre = definitions(c, reglages)
    lignes.append("Registre : " + ("OK" if not erreurs_registre else "; ".join(erreurs_registre)))
    a = s.alertes
    maintenant = s.horloge()
    retenue = a.retenue(maintenant)
    lignes.append(f"Notifications : {a.envoyees_aujourdhui(maintenant)} aujourd'hui"
                  + (f" ; {retenue}" if retenue else ""))  # fmt: skip
    ratees = [n for n in a.dernieres_notifications(10) if not n["envoyee"]]
    if ratees:
        lignes.append(f"  Dernière notification non affichée : {ratees[0]['motif']}")
    try:
        inst = json.loads(s.base.lire_meta("instantane") or "null")
    except ValueError:
        inst = None
    if isinstance(inst, dict):
        etat_inst = "écrit" if inst.get("ecrit") else (inst.get("motif") or "pas écrit")
        lignes.append(f"Instantané iPhone : {etat_inst} ({textes.il_y_a(float(inst.get('ts') or 0), maintenant)})")
    motif_reel = s.base.lire_meta("credits_reels_motif")
    if s.reglages["credits"]["api_admin"]:
        lignes.append("Coût réel : " + (motif_reel or "relevé"))
    lignes.append("")
    lignes.append(f"Modules découverts ({len(s.defs)}) :")
    etats = {e.id: e for e in s.etats()}
    for ident, defn in sorted(s.defs.items()):
        e = etats.get(ident)
        pastille = f"{EMOJI[e.pastille]} {LIBELLE[e.pastille]}" if e else "pas encore observé"
        lignes.append(f"  {defn.emoji} {defn.nom} ({ident}) — adaptateur {defn.adaptateur} — {pastille}")
        if e is not None:
            inconnus = e.technique.get("inconnus") or []
            erreurs = e.technique.get("erreurs_de_lecture") or {}
            for nom in inconnus:
                lignes.append(f"      inconnu : {nom} ({erreurs.get(nom, 'raison non notée')})")
    lignes.append("")
    outils = ["launchctl", "docker", "lsof", "git", "osascript"]
    lignes.append("Commandes de lecture : " + ", ".join(f"{o} {'✅' if shutil.which(o) else '—'}" for o in outils))
    lignes.append(f"Journal : {c.logs / 'tableau.log'}".replace(str(c.maison), "~", 1))
    return "\n".join(lignes)


def diagnostic(s: vues.Source, nom: str) -> str:
    ident = _trouver(s, nom)
    if ident is None or ident not in s.defs:
        return f"Module « {nom} » inconnu."
    d = s.diagnostic(ident, systeme.DemandeExplicite("terminal", ident))
    return d["sortie"]


def installation_(action: str, python: Path | None, projet: Path | None) -> int:
    from tableau import installation

    c = config.chemins()
    reglages = config.charger(c.reglages)
    if action == "label":
        print(reglages.label())
        return 0
    if action == "preparer":
        if python is None or projet is None:
            print("tableau installation preparer --python <python> --projet <dossier>", file=sys.stderr)
            return 2
        b = installation.preparer(c, reglages, python, projet)
    elif action == "verifier":
        b = installation.verifier(c)
    else:
        b = installation.desinstaller(c, reglages)
    print(b.texte())
    return 1 if b.refus else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tableau", description="Le tableau de bord de ton assistant.")
    p.add_argument("--version", action="version", version=f"tableau {VERSION}")
    sous = p.add_subparsers(dest="commande")
    sous.add_parser("etat", help="l'état de chaque module")
    sous.add_parser("ouvrir", help="ouvre la page locale")
    m = sous.add_parser("module", help="le détail d'un module")
    m.add_argument("nom")
    sous.add_parser("credits", help="les crédits Claude du mois")
    i = sous.add_parser("integrite", help="le code de chaque projet comparé à sa référence")
    i.add_argument("action", nargs="?", choices=["accepter"])
    i.add_argument("nom", nargs="?")
    so = sous.add_parser("sourdine", help="met les alertes en sourdine (1h, 30min, fin)")
    so.add_argument("duree")
    sous.add_parser("rapport", help="le rapport des 7 derniers jours")
    sous.add_parser("doctor", help="l'état du tableau de bord lui-même")
    dg = sous.add_parser("diagnostic", help="lance la commande de diagnostic d'un module")
    dg.add_argument("nom")
    de = sous.add_parser("demon", help="le démon (lancé par launchd)")
    de.add_argument("--sans-barre", action="store_true", help="sans l'icône de la barre des menus")
    ins = sous.add_parser("installation", help="utilisé par install.sh et uninstall.sh")
    ins.add_argument("action", choices=["preparer", "label", "verifier", "desinstaller"])
    ins.add_argument("--python", type=Path)
    ins.add_argument("--projet", type=Path)
    a = p.parse_args(argv)
    if a.commande is None:
        a.commande = "etat"
    if a.commande == "demon":
        from tableau import daemon

        return daemon.lancer(barre=False if a.sans_barre else None)
    if a.commande == "installation":
        return installation_(a.action, a.python, a.projet)
    s = source()
    try:
        if a.commande == "etat":
            texte = etat(s)
        elif a.commande == "ouvrir":
            adresse = adresse_page(port(s), config.jeton(s.chemins))
            vivant, detail = demon_vivant(s)
            if systeme.est_un_mac():
                Actions(s, adresse).faire("ouvrir")
            texte = f"Ouvert dans ton navigateur : {adresse}" + ("" if vivant else f"\n⚠️ {detail}")
        elif a.commande == "module":
            texte = module(s, a.nom)
        elif a.commande == "credits":
            texte = credits_(s)
        elif a.commande == "integrite":
            if a.action == "accepter":
                if not a.nom:
                    p.error("tableau integrite accepter <module>")
                texte = accepter(s, a.nom)
            else:
                texte = integrite(s)
        elif a.commande == "sourdine":
            try:
                texte = s.sourdine(a.duree)
            except ValueError as e:
                print(f"Durée illisible : {e}", file=sys.stderr)
                return 2
        elif a.commande == "rapport":
            chemin = rapport_maintenant(s)
            if systeme.est_un_mac():
                systeme.executer(["open", str(chemin)], delai=10)
            texte = f"Rapport des 7 derniers jours : {chemin}".replace(str(s.chemins.maison), "~", 1)
        elif a.commande == "doctor":
            texte = doctor(s)
        else:
            texte = diagnostic(s, a.nom)
    finally:
        s.base.fermer()
    print(texte)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
